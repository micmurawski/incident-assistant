import asyncio
import os
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from dataclasses import dataclass, field

from agent.constants import DIRS_TO_IGNORE

CRITICAL_IGNORE_PATTERNS = {"node_modules", ".git", "__pycache__", "venv", "env"}


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


async def execute_ripgrep(ripgrep_path: str, args: list[str], limit: int) -> list[str]:
    # raise Exception(ripgrep_path, args)
    try:
        proc = await asyncio.create_subprocess_exec(
            ripgrep_path, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"ripgrep failed: {stderr.decode()}")
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


def ensure_first_level_dirs_included(
    results: list[str], first_level_dirs: list[str], limit: int
) -> tuple[list[str], bool]:
    missing = [d for d in first_level_dirs if d not in results]
    if not missing:
        return results, True
    # Remove as many as needed to fit the new ones
    adjusted = results[: -len(missing)] if len(missing) < len(results) else []
    # Guarantee first-level dirs are in front
    return (missing + adjusted)[:limit], True


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
                        dirs.append(entry.path if entry.path.endswith(os.sep) else entry.path + os.sep)
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


if __name__ == "__main__":
    out, limit_reached = asyncio.run(list_files(".", True, 30))
    for i,f in enumerate(out):
        print(i, f)


# rg --files --hidden --follow -g '**/node_modules/**' -g '!**/__pycache__/**' -g '!**/env/**' -g '!**/venv/**' -g '!**/target/dependency/**' -g '!**/build/dependencies/**' -g '!**/dist/**' -g '!**/out/**' -g '!**/bundle/**' -g '!**/vendor/**' -g '!**/tmp/**' -g '!**/temp/**' -g '!**/deps/**' -g '!**/pkg/**' -g '!**/Pods/**' -g '!**/.git/**' -g '*' .