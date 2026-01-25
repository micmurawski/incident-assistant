import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from agent.constants import DIRS_TO_IGNORE
from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()

CRITICAL_IGNORE_PATTERNS = {"node_modules", ".git", "__pycache__", "venv", "env"}

MAX_LINE_LENGTH = 500
MAX_RESULTS = 300


@dataclass
class Ignore:
    patterns: list[str] = field(default_factory=list)

    def load_from_file(self, file: str):
        with open(file, "r") as f:
            lines = list(filter(lambda line: not line.startswith("#") and line.strip() != "", f.read().splitlines()))
            self.patterns.extend(lines)

    def ignores(self, path: str) -> bool:
        return any(fnmatch(path, pattern) for pattern in self.patterns)


@dataclass
class ScanContext:
    is_target_dir_hidden: bool
    inside_explicit_hidden_target: bool
    base_path: str
    ignore_config: Ignore
    is_target_dir: bool = True


def get_ripgrep_path() -> str:
    process = subprocess.run(["which", "rg"], stdout=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError("ripgrep is not installed")
    return process.stdout.decode().strip()


def build_args(dir_path: str, recursive: bool) -> list[str]:
    args = ["--files", "--hidden", "--follow"]
    if recursive:
        dir_path_abs = str(Path(dir_path).resolve())
        is_hidden = any(part.startswith(".") for part in dir_path_abs.split(os.sep))
        target_dir_name = os.path.basename(dir_path_abs)
        is_ignored_target = target_dir_name in DIRS_TO_IGNORE
        if is_hidden or is_ignored_target:
            args += ["--no-ignore-vcs", "--no-ignore", "-g", "*", "-g", "**/*"]
        for d in DIRS_TO_IGNORE:
            if d == ".*":
                # if not is_hidden:
                #    pass
                # args += ["-g", "*"]
                continue
            if d == target_dir_name and is_ignored_target:
                continue
            # The outer single quotes were causing the pattern to not work as expected.
            # Remove the single quotes so ripgrep correctly interprets the glob pattern.
            args += ["-g", f"!**/{d}/**"]
    else:
        args += ["-g", "*", "--maxdepth", "1"]
        for d in DIRS_TO_IGNORE:
            if d != ".*":
                args += ["-g", f"!{d}", "-g", f"{d}/**"]
    args.append(dir_path)
    return args


async def execute_ripgrep(ripgrep_path: str, args: list[str], limit: int, cwd: str | None = None) -> list[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            ripgrep_path, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ripgrep failed: stderr: {stderr.decode()}, stdout: {stdout.decode()} command: {ripgrep_path + ' ' + ' '.join(args)}"
            )
        return stdout.decode().splitlines()[:limit]
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("ripgrep execution timed out")


async def list_files_with_ripgrep(ripgrep_path: str, dir_path: str, recursive: bool, limit: int) -> list[str]:
    args = build_args(dir_path, recursive)
    files = await execute_ripgrep(ripgrep_path, args, limit)
    base = os.path.abspath(dir_path)
    return [os.path.relpath(f, base) for f in files]


async def find_gitignore_files(start_path: str) -> list[str]:
    result = []
    current = os.path.abspath(start_path)
    while current and current != os.path.dirname(current):
        path = os.path.join(current, ".gitignore")
        if os.path.isfile(path):
            result.append(path)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return result[::-1]


def format_and_combine_results(files: list[str], dirs: list[str], limit: int) -> tuple[list[str], bool]:
    unique = list(set(files + dirs))
    unique.sort(key=lambda x: (not x.endswith(os.sep), x))
    trimmed = unique[:limit]
    return trimmed, len(unique) >= limit


def get_first_level_directories(dir_path: str, ignored_config: Ignore) -> list[str]:
    abs_path = os.path.abspath(dir_path)
    dirs = []
    try:
        for entry in os.scandir(abs_path):
            if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                context = ScanContext(
                    is_target_dir_hidden=False,
                    is_target_dir=False,
                    inside_explicit_hidden_target=False,
                    base_path=dir_path,
                    ignore_config=ignored_config,
                )
                if should_include_dir(entry.name, entry.path, context):
                    entry_path = os.path.relpath(entry.path, dir_path)
                    dirs.append(entry_path if entry_path.endswith(os.sep) else entry_path + os.sep)
    except Exception as err:
        print(f"Could not read directory {abs_path}: {err}")
    return dirs


def sort_key(path):
    # Split the path into parts
    parts = path.rstrip("/").split("/")

    # Create a sort key that groups directories with their contents
    # For each part, create a tuple: (part_name, 0 if directory, 1 if file)
    result = []
    for i, part in enumerate(parts):
        # If this is the last part and doesn't end with '/', it's a file
        is_file = (i == len(parts) - 1) and not path.endswith("/")
        result.append((part, 1 if is_file else 0))

    return result


def ensure_first_level_dirs_included(
    results: list[str], first_level_dirs: list[str], limit: int
) -> tuple[list[str], bool]:
    missing = [d for d in first_level_dirs if d not in results]
    if not missing:
        return results, True
    # Remove as many as needed to fit the new ones
    adjusted = results[: -len(missing)] if len(missing) < len(results) else []
    # Guarantee first-level dirs are in front
    combined = (missing + adjusted)[:limit]
    # return combined, True
    sorted_combined = sorted(combined, key=sort_key)
    return sorted_combined, True


async def list_files(dir_path: str, recursive: bool, limit: int) -> tuple[list[str], bool]:
    if limit == 0:
        return [], False
    special = await handle_special_dirs(dir_path)
    if special:
        return special
    rg_path = get_ripgrep_path()
    files = await list_files_with_ripgrep(rg_path, dir_path, recursive, limit)
    ignored = await get_ignored_config(dir_path)
    remain = max(0, limit - len(files))
    # limit_reached = remain == 0
    dirs = await list_filtered_dirs(dir_path, recursive, ignored, remain)
    # dirs = []
    results, limit_reached = format_and_combine_results(files, dirs, limit)
    if recursive and limit_reached:
        first_level_dirs = get_first_level_directories(dir_path, ignored)
        return ensure_first_level_dirs_included(results, first_level_dirs, limit)
    return results, limit_reached


async def get_ignored_config(dir_path: str) -> Ignore:
    ignore = Ignore()
    abs_path = os.path.abspath(dir_path)
    gitignore_files = await find_gitignore_files(abs_path)
    for file in gitignore_files:
        try:
            ignore.load_from_file(file)
        except Exception as e:
            print(f"Error reading {file}: {e}")
    ignore.patterns.append(".gitignore")
    return ignore


def is_dir_explicitly_ignored(dir_name: str) -> bool:
    for pattern in DIRS_TO_IGNORE:
        if pattern == dir_name or fnmatch(dir_name, pattern):
            return True
    return False


def should_include_dir(dir_name: str, full_dir_path: str, context: ScanContext) -> bool:
    # Target dir: skip dirs in ignore
    if context.is_target_dir:
        return not any(dir_name == p or (p != ".*" and fnmatch(dir_name, p)) for p in DIRS_TO_IGNORE)
    # Hidden: skip critical ignored, otherwise check .gitignore
    if context.inside_explicit_hidden_target:
        if dir_name in CRITICAL_IGNORE_PATTERNS:
            return False
        rel = os.path.relpath(full_dir_path, context.base_path)
        return not context.ignore_config.ignores(os.path.normpath(rel)) and not context.ignore_config.ignores(
            os.path.normpath(rel) + os.sep
        )
    # Regular dir: skip ignore list, then .gitignore
    if any(dir_name == p or (p != ".*" and fnmatch(dir_name, p)) for p in DIRS_TO_IGNORE if p != ".*"):
        return False
    rel = os.path.relpath(full_dir_path, context.base_path)
    return not context.ignore_config.ignores(os.path.normpath(rel)) and not context.ignore_config.ignores(
        os.path.normpath(rel) + os.sep
    )


async def list_filtered_dirs(
    dir_path: str, recursive: bool, ignored_config: Ignore, limit: int | None = None
) -> list[str]:
    abs_path = os.path.abspath(dir_path)
    dirs = []
    effective_limit = limit or sys.maxsize

    async def walk(path: str, context: ScanContext, remain: int) -> int:
        if remain <= 0:
            return 0
        try:
            for entry in os.scandir(path):
                if remain <= 0:
                    break
                if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                    subcontext = ScanContext(
                        is_target_dir_hidden=context.is_target_dir_hidden,
                        is_target_dir=False,
                        inside_explicit_hidden_target=context.inside_explicit_hidden_target
                        or (entry.name.startswith(".") and context.is_target_dir),
                        base_path=context.base_path,
                        ignore_config=context.ignore_config,
                    )
                    if should_include_dir(entry.name, entry.path, subcontext):
                        rel = os.path.relpath(entry.path, dir_path)
                        dirs.append(rel if rel.endswith(os.sep) else rel + os.sep)
                        remain -= 1
                    if recursive and remain > 0:
                        remain -= await walk(entry.path, subcontext, remain)
        except Exception:
            pass
        return 0

    is_hidden = os.path.basename(dir_path).startswith(".")
    context = ScanContext(
        is_target_dir_hidden=is_hidden,
        inside_explicit_hidden_target=is_hidden,
        base_path=dir_path,
        ignore_config=ignored_config,
    )
    await walk(abs_path, context, effective_limit)
    return dirs


def are_same_path(a: str, b: str) -> bool:
    return os.path.normpath(a) == os.path.normpath(b)


async def handle_special_dirs(dir_path: str):
    abs_path = os.path.abspath(dir_path)
    if any(are_same_path(abs_path, d) for d in [os.path.abspath(os.sep), os.path.expanduser("~")]):
        return [abs_path, False]
    return None


def truncate_line(line: str, max_length: int = MAX_LINE_LENGTH) -> str:
    return line[:max_length] + "..." if len(line) > max_length else line


def format_results(file_results: list[dict], cwd: str) -> str:
    grouped_results: dict[str, list[dict]] = {}

    total_results = sum(len(file.get("search_results", [])) for file in file_results)
    output = ""
    max_results = MAX_RESULTS  # Assumes MAX_RESULTS is defined elsewhere

    if total_results >= max_results:
        output += f"Showing first {max_results} of {max_results}+ results. Use a more specific search if necessary.\n\n"
    else:
        output += f"Found {total_results if total_results == 1 else f'{total_results:,} results'}.\n\n"

    # Group results by file name
    for file in file_results[:max_results]:
        file_path = file.get("file")
        relative_file_path = os.path.relpath(file_path, cwd)
        # Normalize to posix style
        posix_file_path = relative_file_path.replace(os.sep, "/")
        if posix_file_path not in grouped_results:
            grouped_results[posix_file_path] = []
            grouped_results[posix_file_path].extend(file.get("search_results", []))

    for file_path, results in grouped_results.items():
        output += f"# {file_path}\n"
        for result in results:
            # Only show results with at least one line
            lines = result.get("lines", [])
            if len(lines) > 0:
                for line in lines:
                    line_number = str(line.get("line")).rjust(3, " ")
                    output += f"{line_number} | {line.get('text', '').rstrip()}\n"
                output += "----\n"
        output += "\n"

    return output.strip()


async def regex_search_files(
    cwd: str,
    directory_path: str,
    regex: str,
    file_pattern: str | None = None,
) -> str:
    """
    Search files in a directory using ripgrep with the given regex and file pattern, returning formatted results.
    roo_ignore_controller, if passed, should implement a validateAccess(file:str) method that returns bool.
    """

    # ripgrep expects -e to be a valid regex (not a glob!)
    # If the regex is empty, use a regex that matches everything; otherwise, use what was passed.
    # For the --glob argument, if file_pattern is None, use "*", otherwise use file_pattern as-is

    args = [
        "--json",
        "-e",
        f"`{regex}`",
        "--glob",
        file_pattern or "*",
        "--context",
        "1",
        "--no-messages",
        directory_path,
    ]

    output = await execute_ripgrep(get_ripgrep_path(), args, MAX_RESULTS, cwd=cwd)

    results: list[dict] = []
    current_file: dict | None = None
    line: str | None = None
    for line in output:
        if line is None:
            continue

        if not line.strip():
            continue

        try:
            parsed = json.loads(line)
            ptype = parsed.get("type")
            if ptype == "begin":
                current_file = dict(file=parsed["data"]["path"]["text"], search_results=[])
            elif ptype == "end":
                if current_file is not None:
                    results.append(current_file)
                    current_file = None
            elif (ptype == "match" or ptype == "context") and current_file is not None:
                line_entry = dict(
                    line=parsed["data"]["line_number"],
                    text=truncate_line(parsed["data"]["lines"]["text"]),
                    is_match=ptype == "match",
                )
                if ptype == "match":
                    line_entry["column"] = parsed["data"].get("absolute_offset")
                # Add the result to the last 'searchResults' or start a new one as needed
                last_result = current_file["search_results"][-1] if current_file["search_results"] else None
                if last_result and last_result.get("lines"):
                    last_line = last_result["lines"][-1]
                    if parsed["data"]["line_number"] <= last_line["line"] + 1:
                        last_result["lines"].append(line_entry)
                    else:
                        current_file["search_results"].append({"lines": [line_entry]})
                else:
                    current_file["search_results"].append({"lines": [line_entry]})
        except Exception as error:
            print(f"Error parsing ripgrep output: {error}")

    return format_results(results, cwd)


async def main(rel_path, recursive):
    os.path.abspath(".")
    result = await regex_search_files(
        cwd=None,
        directory_path=rel_path,
        regex="*",
        file_pattern="*",
    )
    print(result)


if __name__ == "__main__":
    abs_path = os.path.abspath(".")
    print(abs_path)
    out = asyncio.run(main(".", True))
    print(out)
