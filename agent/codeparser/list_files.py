from fnmatch import fnmatch
from dataclasses import dataclass, field
import subprocess
from constants import DIRS_TO_IGNORE
from pathlib import Path
import os
import asyncio
from typing import Any, Coroutine, Optional
import sys


CRITICAL_IGNORE_PATTERNS = set(
    ["node_modules", ".git", "__pycache__", "venv", "env"]
)


@dataclass
class Ignore:
    patterns: list[str] = field(default_factory=list)

    def ignores(self, path: str) -> bool:
        return any(fnmatch(path, pattern) for pattern in self.patterns)


@dataclass
class ScanContext:
    is_target_dir_hidden: bool
    inside_explicit_hidden_target: bool
    base_path: str
    ignore_config: Ignore
    is_target_dir: Optional[bool] = True


def ensure_ripgrep_installed() -> str:
    # run cli command process.run(["rg", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process = subprocess.run(
        ["rg", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise Exception("ripgrep is not installed")
    return process.stdout.decode('utf-8')


def get_ripgrep_path() -> str:
    process = subprocess.run(
        ["which", "rg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise Exception("ripgrep is not installed")
    return process.stdout.decode('utf-8').strip()


def build_args(dir_path: str, recursive: bool) -> list[str]:
    args = ["--files", "--hidden", "--follow"]
    if recursive:
        return [*args, *build_recursive_args(dir_path), dir_path]
    return [*args, *build_non_recursive_args(), dir_path]


def build_recursive_args(dir_path: str) -> list[str]:
    args = []
    # Normalize the directory path using pathlib
    dir_path = str(Path(dir_path).resolve())
    path_parts = dir_path.split(os.sep)
    # raise Exception(path_parts)
    is_targeting_hidden_dir = any(
        filter(lambda x: x.startswith("."), path_parts))
    target_dir_name = os.path.basename(dir_path)
    is_target_in_ignore_list = target_dir_name in DIRS_TO_IGNORE
    if is_targeting_hidden_dir or is_target_in_ignore_list:
        args.append("--no-ignore-vcs")
        args.append("--no-ignore")
        # When targeting an ignored directory, we need to be careful with glob patterns
        # Add a pattern to explicitly include files at the root level
        args.extend(["-g", "*"])
        args.extend(["-g", "**/*"])
    for dir in DIRS_TO_IGNORE:
        if dir == ".*":
            if not is_targeting_hidden_dir:
                args.extend(["-g", "*"])
            continue
        if dir == target_dir_name and is_target_in_ignore_list:
            continue
        args.extend(["-g", f"**/{dir}/**"])
    return args


def build_non_recursive_args() -> list[str]:
    args = [
        "-g", "*",
        "--maxdepth", "1",
    ]
    for dir in DIRS_TO_IGNORE:
        if dir == ".*":
            continue
        args.extend(["-g", f"!{dir}", "-g", f"!{dir}/**"])
    return args


async def execute_ripgrep(ripgrep_path: str, args: list[str], limit: int) -> Coroutine[Any, Any, list[str]]:
    try:
        process = await asyncio.create_subprocess_exec(
            ripgrep_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Set a timeout for the process execution (e.g., 30 seconds)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        if process.returncode != 0:
            raise Exception(
                f"ripgrep execution failed: {stderr.decode('utf-8')}")
        return stdout.decode('utf-8').splitlines()[:limit]
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise Exception("ripgrep execution timed out")


async def list_files_with_ripgrep(ripgrep_path: str, dir_path: str, recursive: bool, limit: int) -> Coroutine[Any, Any, list[str]]:
    args = build_args(dir_path, recursive)
    files = await execute_ripgrep(ripgrep_path, args, limit)
    absolute_path = os.path.abspath(dir_path)
    return list(map(lambda file: os.path.relpath(file, absolute_path), files))


async def find_gitignore_files(start_path: str) -> list[str]:
    gitignore_files: list[str] = []
    current_path = os.path.abspath(start_path)

    # Walk up the directory tree looking for .gitignore files
    while current_path and current_path != os.path.dirname(current_path):
        gitignore_path = os.path.join(current_path, ".gitignore")
        try:
            # Use asyncio to check file existence asynchronously
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, os.access, gitignore_path, os.F_OK)
            gitignore_files.append(gitignore_path)
        except Exception:
            # .gitignore doesn't exist at this level, continue
            pass

        # Move up one directory
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:
            break  # Reached root
        current_path = parent_path

    # Return in reverse order (root .gitignore first, then more specific ones)
    return list(reversed(gitignore_files))


def format_and_combine_results(files: list[str], dirs: list[str], limit: int) -> tuple[list[str], bool]:
    all_paths = [*files, *dirs]
    unique_paths_set = set(all_paths)
    unique_paths = list(unique_paths_set)
    unique_paths.sort(key=lambda x: (not x.endswith("/"), x))
    trimmed_paths = unique_paths[:limit]
    return trimmed_paths, len(unique_paths_set) >= limit


def get_first_level_directories(dir_path: str, ignored_config: Ignore) -> list[str]:
    absolute_path = os.path.abspath(dir_path)
    dirs = []
    try:
        with os.scandir(absolute_path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                    full_dir_path = os.path.join(absolute_path, entry.name)
                    context = ScanContext(
                        is_target_dir=False,
                        inside_explicit_hidden_target=False,
                        base_path=dir_path,
                        ignore_config=ignored_config,
                    )
                    if should_include_dir(entry.name, full_dir_path, context):
                        formatted_path = full_dir_path if full_dir_path.endswith(
                            os.sep) else f"{full_dir_path}{os.sep}"
                        dirs.append(formatted_path)
    except Exception as err:
        print(f"Could not read directory {absolute_path}: {err}")
    return dirs


def ensure_firs_level_dirs_included(results: list[str], first_level_dirs: list[str], limit: int) -> tuple[list[str], bool]:
    existing_paths = set(results)
    missing_paths = filter(
        lambda path: path not in existing_paths, first_level_dirs)
    if len(missing_paths) == 0:
        return results, True

    items_to_remove = min(len(missing_paths), len(results))
    adjusted_results = results[:-items_to_remove]
    result_paths = map(lambda path: os.path.resolve(path), adjusted_results)
    base_path = os.sep.join(os.path.resolve(
        first_level_dirs[0]).split(os.sep)[:-1])

    first_level_results = []
    other_results = []
    for i in range(len(adjusted_results)):
        relative_path = os.path.relpath(result_paths[i], base_path)
        depth = len(relative_path.split(os.sep))
        if depth == 1:
            first_level_results.append(adjusted_results[i])
        else:
            other_results.append(adjusted_results[i])

    final_results = [*first_level_results, *
                     missing_paths, *other_results][:limit]
    return final_results, True


async def list_files(dir_path: str, recursive: bool, limit: int) -> Coroutine[Any, Any, tuple[list[str], bool]]:
    if limit == 0:
        return [], False
    special_result = await handle_special_dirs(dir_path)

    if special_result:
        return special_result

    ripgrep_path = get_ripgrep_path()
    if not recursive:
        files = await list_files_with_ripgrep(ripgrep_path, dir_path, False, limit)
        ignored_config = await get_ignored_config(dir_path)
        remaining_limit = max(0, limit - len(files))
        dirs = await list_filtered_dirs(dir_path, False, ignored_config, remaining_limit)
        return format_and_combine_results(files, dirs, limit)

    # For recursive mode, use the original approach but ensure first-level directories are included
    files = await list_files_with_ripgrep(ripgrep_path, dir_path, True, limit)
    ignored_config = await get_ignored_config(dir_path)
    remaining_limit = max(0, limit - len(files))
    dirs = await list_filtered_dirs(dir_path, True, ignored_config, remaining_limit)
    [results, limit_reached] = format_and_combine_results(files, dirs, limit)

    if limit_reached:
        first_level_dirs = await get_first_level_directories(dir_path, ignored_config)
        return ensure_firs_level_dirs_included(results, first_level_dirs, limit)
    return results, limit_reached


async def get_ignored_config(dir_path: str) -> Coroutine[Any, Any, Ignore]:
    ignore = Ignore()
    abs_path = os.path.abspath(dir_path)
    gitignore_files = await find_gitignore_files(abs_path)
    for gitignore_file in gitignore_files:
        try:
            content = open(gitignore_file, 'r').read().splitlines()
            ignore.patterns.extend(content)
        except Exception as e:
            print(f"Error reading {gitignore_file}: {e}")
    ignore.patterns.append(".gitignore")
    return ignore


def is_dir_explicitly_ignored(dir_name: str) -> bool:
    for pattern in DIRS_TO_IGNORE:
        if pattern == dir_name or fnmatch(dir_name, pattern):
            return True
        if pattern == ".*":
            continue

        if os.sep in pattern:
            if pattern.rsplit(os.sep, 1)[0] == dir_name:
                return True

    return False


async def scan_dir(current_path: str, context: ScanContext, dir_count: int, effective_limit: int, dirs: list[str], recursive: bool):
    if dir_count >= effective_limit:
        return True

    try:
        entries = [entry for entry in os.scandir(current_path)]

        for entry in entries:
            if dir_count >= effective_limit:
                return True
            if entry.is_dir() and not entry.is_symlink():
                dir_name = entry.name
                full_dir_path = os.path.join(current_path, dir_name)
                subdir_context = context.copy()
                subdir_context.is_target_dir = False

                if should_include_dir(dir_name, full_dir_path, subdir_context):
                    formatted_path = full_dir_path if full_dir_path.endswith(
                        os.sep) else full_dir_path + os.sep
                    dirs.append(formatted_path)
                    dir_count += 1

                    if dir_count >= effective_limit:
                        return True
                is_hidden_dir = dir_name.startswith(".")
                should_recurse_inside_dir = True
                if context.inside_explicit_hidden_target:
                    should_recurse_inside_dir = dir_name in CRITICAL_IGNORE_PATTERNS
                else:
                    should_recurse_inside_dir = not is_dir_explicitly_ignored(
                        dir_name)

                should_recurse = recursive and should_recurse_inside_dir
                if should_recurse:
                    new_inside_explicit_hidden_target = context.inside_explicit_hidden_target or (
                        is_hidden_dir and context.is_target_dir)
                    new_context = context.copy()
                    new_context.is_target_dir = False
                    new_context.inside_explicit_hidden_target = new_inside_explicit_hidden_target
                    limit_reached = await scan_dir(full_dir_path, new_context, dir_count, effective_limit, dirs, recursive)
                    if limit_reached:
                        return True

    except Exception as e:
        return False


def matches_ignore_pattern(dir_name: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern == dir_name or (os.sep in pattern and pattern.split(os.sep)[0] == dir_name):
            return True
    return False


def should_include_target_dir(dir_name: str) -> bool:
    non_hidden_ignore_patterns = filter(
        lambda pattern: pattern != ".*", DIRS_TO_IGNORE)
    return not matches_ignore_pattern(dir_name, non_hidden_ignore_patterns)


def is_ignored_by_gitignore(full_dir_path: str, base_path: str, ignore_config: Ignore) -> bool:
    rel_path = os.path.relpath(full_dir_path, base_path)
    normalized_rel_path = os.path.normpath(rel_path)
    return ignore_config.ignores(normalized_rel_path) or ignore_config.ignores(normalized_rel_path + os.sep)


def should_include_inside_explicit_hidden_target(dir_name: str, full_dir_path: str, context: ScanContext) -> bool:
    if dir_name in CRITICAL_IGNORE_PATTERNS:
        return False
    return not is_ignored_by_gitignore(full_dir_path, context.base_path, context.ignore_config)


def should_include_regular_dir(dir_name: str, full_dir_path: str, context: ScanContext) -> bool:
    non_hidden_ignore_patterns = filter(
        lambda pattern: pattern != ".*", DIRS_TO_IGNORE)
    if matches_ignore_pattern(dir_name, non_hidden_ignore_patterns):
        return False
    return not is_ignored_by_gitignore(full_dir_path, context.base_path, context.ignore_config)


def should_include_dir(dir_name: str, full_dir_path: str, context: ScanContext) -> bool:
    if context.is_target_dir:
        return should_include_target_dir(dir_name)

    if context.inside_explicit_hidden_target:
        return should_include_inside_explicit_hidden_target(dir_name, full_dir_path, context)

    return should_include_regular_dir(dir_name, full_dir_path, context)


async def list_filtered_dirs(dir_path: str, recursive: bool, ignored_config: Ignore, limit: int | None = None) -> Coroutine[Any, Any, list[str]]:
    absolute_path = os.path.abspath(dir_path)
    dirs = []
    dir_count = 0
    effective_limit = limit or sys.maxsize
    is_explicit_hidden_target = os.path.basename(dir_path).startswith(".")

    initial_context = ScanContext(
        is_target_dir_hidden=is_explicit_hidden_target,
        inside_explicit_hidden_target=is_explicit_hidden_target,
        base_path=dir_path,
        ignore_config=ignored_config
    )
    await scan_dir(absolute_path, initial_context, dir_count, effective_limit, dirs, recursive)
    return dirs


def are_same_path(path1: str, path2: str) -> bool:
    return os.path.normpath(path1) == os.path.normpath(path2)


async def handle_special_dirs(dir_path: str):
    abs_path = os.path.abspath(dir_path)
    if are_same_path(abs_path, os.path.abspath(os.sep)):
        return [abs_path, False]
    home = os.path.expanduser("~")
    if are_same_path(abs_path, home):
        return [abs_path, False]
    return

if __name__ == "__main__":
    result = asyncio.run(list_files_with_ripgrep(".", True, 20))
    for file in result:
        print(file)
