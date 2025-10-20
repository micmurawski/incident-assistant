import difflib
import os

LOCK_TEXT_SYMBOL = "🔒"


def format_files_list(
    absolute_path: str,
    files: list[str],
    did_hit_limit: bool,
) -> str:
    """
    Formats a list of files for display, marking ignored and protected files.
    Paths in `files` should be relative to `absolute_path` (NOT absolute!).

    Args:
        absolute_path: The directory against which file paths are relative.
        files: List of files (should be relative paths, directories should end with "/").
        did_hit_limit: Whether the file list was truncated due to a result limit.

    Returns:
        str: A formatted string representing the files.
    """

    def sort_key(path: str):
        parts = path.rstrip("/").split("/")
        return [(part, 1 if (i == len(parts) - 1 and not path.endswith("/")) else 0) for i, part in enumerate(parts)]

    # Use forward slashes for sorting and output (posix)
    rel_files = []
    for file in files:
        rel_path = os.path.relpath(file, absolute_path) if os.path.isabs(file) else file
        rel_path = rel_path.replace(os.sep, "/")
        rel_path = rel_path + "/" if file.endswith("/") and not rel_path.endswith("/") else rel_path
        rel_files.append(rel_path)

    # Sort so directory hierarchy is clear
    rel_files_sorted = sorted(rel_files, key=sort_key)

    if did_hit_limit:
        return (
            "\n".join(rel_files_sorted)
            + "\n\n(File list truncated. Use list_files on specific subdirectories if you need to explore further.)"
        )
    elif not rel_files_sorted or (len(rel_files_sorted) == 1 and rel_files_sorted[0] == ""):
        return "No files found."
    else:
        return "\n".join(rel_files_sorted)


def create_pretty_patch(filename: str, old_str: str | None = None, new_str: str | None = None) -> str:
    """
    Create a unified diff (pretty patch) between two strings, omitting header lines.

    Args:
        filename (str): The file name for the diff.
        old_str (str | None): The original content.
        new_str (str | None): The modified content.

    Returns:
        str: The 'pretty patch' as a string with header lines removed.
    """

    # Defensive: strings must not be None for difflib, so use "" if they're None
    old_str = old_str if old_str is not None else ""
    new_str = new_str if new_str is not None else ""
    old_lines = old_str.splitlines(keepends=True)
    new_lines = new_str.splitlines(keepends=True)

    # difflib.unified_diff can take filenames for labeling
    patch_lines = list(difflib.unified_diff(old_lines, new_lines, fromfile=filename, tofile=filename, lineterm=""))
    # Skip the first 4 lines (headers: ---/+++ and @@ chunk indicator)
    pretty_patch_lines = patch_lines[4:]
    return "\n".join(pretty_patch_lines)
