import locale
import os
import re
from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Literal, Optional

from agent.code_index.code_analysis import parse_source_code_definitions
from agent.list_files import Ignore, list_files, regex_search_files
from agent.settings import SettingsManager
from agent.utils.formatting import create_pretty_patch


@dataclass
class FileOpsResult:
    path: str
    content: str | None = field(default=None)
    diff: str | None = field(default=None)
    status: Literal["success", "error"] = field(default="success")
    error: Optional[Exception] = field(default=None)
    reason: Optional[str] = field(default=None)

    @property
    def changed(self) -> bool:
        return self.diff is not None

    def print_diff(self) -> None:
        if self.diff is None:
            return
        print(create_pretty_patch(self.path, self.diff))


def add_line_numbers(content: list[str], start_line: int = 1, separator: str = "| ") -> list[str]:
    digits = len(str(start_line + len(content)))
    padding = digits
    for i in range(len(content)):
        content[i] = f"{' ' * padding}{i + start_line}{separator}{content[i]}"
        if i + start_line + 2 > (10**digits):
            digits -= 1
            padding -= 1
    return content


class FileOpsManager:
    _instances = {}

    def __new__(cls, cwd: str):
        abs_cwd = os.path.abspath(cwd)
        if abs_cwd in cls._instances:
            return cls._instances[abs_cwd]
        instance = super().__new__(cls)
        cls._instances[abs_cwd] = instance
        return instance

    @classmethod
    def get_instance(cls, cwd: str | None = None) -> "FileOpsManager":
        cwd = cwd or SettingsManager.get_instance().get("workspace.path") or os.getcwd()
        abs_cwd = os.path.abspath(cwd)
        if abs_cwd not in cls._instances:
            cls._instances[abs_cwd] = FileOpsManager(cwd)
        return cls._instances[abs_cwd]

    def __init__(self, cwd: str):
        abs_cwd = os.path.abspath(cwd)
        # Avoid re-initialization for existing instance
        if hasattr(self, "_initialized") and self._initialized:
            return
        if not os.path.exists(abs_cwd):
            raise Exception(f"The path {abs_cwd} does not exist.")
        if not os.path.isdir(abs_cwd):
            raise Exception(f"The path {abs_cwd} is not a directory.")
        self.cwd = abs_cwd
        self.ignore = Ignore()
        self._initialized = True

    async def list_code_definitions_names_descriptions(self, path: str) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)
        content = await parse_source_code_definitions(full_path)
        return FileOpsResult(path=path, content=content)

    async def read_file(
        self,
        path: str,
        start_line: str | None = None,
        end_line: str | None = None,
        number_lines: bool = True,
    ) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)
        path_exists = os.path.exists(full_path)
        is_file = os.path.isfile(full_path)
        if not path_exists:
            raise Exception(f"The path: {path} does not exists.")
        if not is_file:
            raise Exception(f"The path {path} is not file.")

        lines = open(full_path).read().splitlines(keepends=True)
        start_line = start_line or 1
        end_line = end_line or len(lines)
        start = max(start_line - 1, 0)
        end = min(end_line - 1, len(lines) - 1)
        target_content = lines[start: end + 1]
        if number_lines:
            target_content = add_line_numbers(target_content, start_line)
        return FileOpsResult(
            path=path,
            content="".join(target_content),
        )

    async def read_multiple_files(self, files: list[dict]) -> FileOpsResult:
        content = ""
        for file in files:
            result = await self.read_file(file["path"], file.get("start_line"), file.get("end_line"))
            content += f"# {file['path']}\n {result.content}\n ----\n"

        return FileOpsResult(
            path=self.cwd,
            content=content,
        )

    async def list_files_tool(self, path: str, recursive: bool) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)
        if not os.path.exists(full_path):
            return FileOpsResult(
                path=path,
                content=f"The path {full_path} does not exist.",
                error=Exception(f"The path {full_path} does not exist."),
            )

        files, did_hit_limit = await list_files(full_path, recursive, 200)
        # files = list(filter(lambda f: self.ignore.ignores(f), files))

        result = self._format_files_list(full_path, files, did_hit_limit)
        return FileOpsResult(
            path=path,
            content=result,
        )

    @staticmethod
    def _format_files_list(absolute_path: str, files: list[str], did_hit_limit: bool) -> str:
        _files = []
        for file in files:
            # file is relative to absolute_path; relpath(path, start) = path relative to start
            rel_path = os.path.relpath(os.path.join(absolute_path, file), absolute_path)
            if file.endswith(os.sep):
                rel_path = rel_path + os.sep if not rel_path.endswith(os.sep) else rel_path
            _files.append(rel_path)

        def _sort(a: str, b: str):
            a_parts = a.split(os.sep)
            b_parts = b.split(os.sep)
            for i in range(min(len(a_parts), len(b_parts))):
                if a_parts[i] != b_parts[i]:
                    if i + 1 == len(a_parts) and i + 1 < len(b_parts):
                        return -1
                    if i + 1 == len(b_parts) and i + 1 < len(a_parts):
                        return 1
                    a_is_digit = a_parts[i].isdigit()
                    b_is_digit = b_parts[i].isdigit()
                    if a_is_digit and b_is_digit:
                        return int(a_parts[i]) - int(b_parts[i])
                    va = locale.strxfrm(a_parts[i]).lower()
                    vb = locale.strxfrm(b_parts[i]).lower()
                    return (va > vb) - (va < vb)
            return len(a_parts) - len(b_parts)

        res = "\n".join(sorted(_files, key=cmp_to_key(_sort)))
        if not res:
            return "No files found."
        if did_hit_limit:
            res += "\n\n File list truncated. Use list_files on specific subdirectory"
        return res

    async def search_and_replace(
        self,
        path: str,
        search: str,
        replace: str,
        ignore_case: bool,
        use_regex: bool,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)
        path_exists = os.path.exists(full_path)
        is_file = os.path.isfile(full_path)

        if not path_exists:
            raise Exception(f"The path: {path} does not exists.")

        if not is_file:
            raise Exception(f"The path {path} is not file.")

        # Build regex flags correctly as an integer bitmask
        flags = re.IGNORECASE if ignore_case else 0
        search_pattern = search if use_regex else escape_regex(search)

        # Read original content once so we can generate a proper diff later
        with open(full_path, "r") as f:
            original_content = f.read()

        new_content: str
        if start_line is not None or end_line is not None:
            # Work on a specific line range, preserving existing newlines.
            # IMPORTANT: The search pattern may span multiple lines, so we must
            # treat the selected range as a single string segment rather than
            # applying the replacement line‑by‑line (which would never match a
            # multi‑line pattern).
            lines = original_content.split("\n")
            start = max((start_line or 1) - 1, 0)
            end = min((end_line or len(lines)) - 1, len(lines) - 1)

            before_lines = lines[0:start]
            after_lines = lines[end + 1:]

            target_lines = lines[start : end + 1]
            segment = "\n".join(target_lines)
            modified_segment = re.sub(search_pattern, replace, segment, flags=flags)
            modified_lines = modified_segment.split("\n")
            new_content = "\n".join([*before_lines, *modified_lines, *after_lines])
        else:
            new_content = re.sub(search_pattern, replace, original_content, flags=flags)
        with open(full_path, "w") as file:
            file.write(new_content)

        return FileOpsResult(
            path=path,
            diff=_generate_diff(original_content, new_content),
        )

    async def write_to_file(
        self,
        path: str,
        new_content: str,
        create_if_not_exists: bool = True,
    ) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)

        if new_content.startswith("```"):
            new_content = "\n".join(new_content.split("\n")[1:])

        if new_content.endswith("```"):
            new_content = "\n".join(new_content.split("\n")[:-1])

        # if not "claude" in context.model:
        #    new_content = unescape_html_entities(new_content)

        if create_if_not_exists:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w") as file:
            file.write(new_content)

        return FileOpsResult(
            path=path,
            diff=_generate_diff(open(full_path).read(), new_content),
        )

    @staticmethod
    def _insert_content(content: list[str], insert_groups: list[dict]) -> list[str]:
        sorted_insert_groups = sorted(insert_groups, key=lambda x: x["index"])
        last_offset = 0
        for insert_group in sorted_insert_groups:
            idx = insert_group["index"] + last_offset
            content = [*content[:idx], *insert_group["content"], *content[idx:]]
            last_offset += len(insert_group["content"])
        return content

    async def append_to_file(
        self,
        path: str,
        content: str,
        line: int,
    ) -> FileOpsResult:
        full_path = os.path.join(self.cwd, path)
        path_exists = os.path.exists(full_path)
        is_file = os.path.isfile(full_path)
        if not path_exists:
            raise Exception(f"The path: {path} does not exist.")
        if not is_file:
            raise Exception(f"The path {path} is not file.")

        # Read the original content once so we can both
        # (a) preserve the existing newline structure and
        # (b) generate an accurate diff afterwards.
        original_content = open(full_path).read()

        # Work with logical lines *without* embedded newline characters.
        # This avoids doubling newlines when we later join with "\n".
        lines = original_content.splitlines()

        # Convert the 1-based line number (or None) to a safe insertion index.
        # If `line` is None, append to the end of the file.
        if line is None:
            insert_at = len(lines)
        else:
            # Clamp to [0, len(lines)] to avoid index errors.
            insert_at = max(0, min(line - 1, len(lines)))

        insert_content_lines = content.splitlines()
        new_lines = self._insert_content(
            lines, [{"index": insert_at, "content": insert_content_lines}]
        )

        # Reconstruct the file content with a single newline separator between
        # logical lines. This prevents the extra blank lines that previously
        # appeared due to mixing keepends=True with an additional join.
        res = "\n".join(new_lines)
        with open(full_path, "w") as file:
            file.write(res)

        return FileOpsResult(
            path=path,
            diff=_generate_diff(original_content, res),
        )

    async def search_file(self, path: str, regex: str, file_pattern: str | None = None) -> FileOpsResult:
        result = await regex_search_files(self.cwd, path, regex, file_pattern)
        return FileOpsResult(
            path=path,
            content=result,
        )


def escape_regex(reg: str) -> str:
    """
    Escape a literal string so it can be safely used as a regular expression.

    Python's stdlib provides `re.escape` for this purpose, which correctly
    handles all regex metacharacters. The previous implementation attempted to
    mimic a JavaScript-style replace with a character class pattern but used
    `str.replace` instead of a regex replacement, which produced invalid
    patterns and could raise `re.error` at compile time.
    """
    return re.escape(reg)


def _generate_diff(old_content: str, new_content: str) -> str:
    original_lines = old_content.split("\n")
    modified_lines = new_content.split("\n")
    diff: list[str] = []

    i = 0
    j = 0

    while i < len(original_lines) or j < len(modified_lines):
        if i >= len(original_lines):
            diff.append(f"+ {modified_lines[j]}")
            j += 1
        elif j >= len(modified_lines):
            diff.append(f"- {original_lines[i]}")
            i += 1
        elif original_lines[i] == modified_lines[j]:
            diff.append(f"  {original_lines[i]}")
            i += 1
            j += 1
        else:
            diff.append(f"- {original_lines[i]}")
            diff.append(f"+ {modified_lines[j]}")
            i += 1
            j += 1
    return "\n".join(diff)


def _generate_diff(old_content: str, new_content: str, use_ansi_color: bool = False) -> str:
    # ANSI color codes
    RED = "\033[91m-" if use_ansi_color else "-"
    GREEN = "\033[92m+" if use_ansi_color else "+"
    RESET = "\033[0m" if use_ansi_color else ""

    original_lines = old_content.split("\n")
    modified_lines = new_content.split("\n")
    diff: list[str] = []

    i = 0
    j = 0

    while i < len(original_lines) or j < len(modified_lines):
        if i >= len(original_lines):
            diff.append(f"{GREEN} {modified_lines[j]}{RESET}")
            j += 1
        elif j >= len(modified_lines):
            diff.append(f"{RED} {original_lines[i]}{RESET}")
            i += 1
        elif original_lines[i] == modified_lines[j]:
            diff.append(f"  {original_lines[i]}")
            i += 1
            j += 1
        else:
            diff.append(f"{RED} {original_lines[i]}{RESET}")
            diff.append(f"{GREEN} {modified_lines[j]}{RESET}")
            i += 1
            j += 1
    return "\n".join(diff)
