from typing import Annotated, Optional

from agent.file_ops import FileOpsManager, FileOpsResult
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool


@tool(tags=["codebase", "write"])
async def search_and_replace(
    cwd: Hidden[str],
    path: Annotated[str, "File path (relative to workspace directory {cwd})"],
    search: Annotated[str, "The search string to replace"],
    replace: Annotated[str, "The replacement string"],
    start_line: Annotated[Optional[int], "Start line number (1-based) for range reading (default: 1)"] = 1,
    end_line: Annotated[
        Optional[int], "End line number (1-based) for range reading (default: last line of file)"
    ] = None,
    use_regex: Annotated[Optional[bool], "Whether to use regex when searching"] = False,
    ignore_case: Annotated[Optional[bool], "Whether to ignore case when searching"] = False,
) -> ToolResult:
    """
    Request to search and replace a string in a file. Use this when you need to search and replace a string in a file.
    Notes:
    - When use_regex is true, the search parameter is treated as a regular expression pattern.
    - When ignore_case is true, the search is case-insensitive regardless of regex mode.

    Examples:
    1. Simple text replacement:
    search_and_replace(path="src/main.ts", search="console.log", replace="console.error")

    2. Case-insensitive regex pattern:
    search_and_replace(path="src/main.ts", search="console.log", replace="console.error", use_regex=True, ignore_case=True)
    """
    result: FileOpsResult = await FileOpsManager.get_instance(cwd).search_and_replace(
        path=path,
        search=search,
        replace=replace,
        ignore_case=bool(ignore_case),
        use_regex=bool(use_regex),
        start_line=start_line,
        end_line=end_line,
    )
    return ToolResult(result=result.diff, error=result.error)


@tool(tags=["write", "codebase"])
async def insert_content(
    cwd: Hidden[str],
    path: Annotated[str, "File path relative to workspace directory {cwd}"],
    content: Annotated[str, "The content to insert at the specified line"],
    line: Annotated[
        Optional[int],
        "Line number where content will be inserted (1-based). Use 0 to append at end of file. Use any positive number to insert before that line (default: None means append at end of file)",
    ] = 0,
) -> ToolResult:
    """
    Use this tool specifically for adding new lines of content into a file without modifying existing content.
    Specify the line number to insert before, or use line 0 to append to the end. Ideal for adding imports, functions, configuration blocks, log entries, or any multi-line text block.

    Example for inserting imports at start of file:
    insert_content(path="src/utils.ts", line=1, content="// Add imports at start of file\nimport { sum } from './math';")

    Example for appending to the end of file:
    insert_content(path="src/utils.ts", line=0, content="// This is the end of the file")
    """
    result: FileOpsResult = await FileOpsManager.get_instance(cwd).append_to_file(path, content, line)
    return ToolResult(result=result.diff, error=result.error)


@tool(tags=["write"])
async def write_to_file(
    cwd: Hidden[str],
    path: Annotated[str, "The path of the file to write to (relative to the current workspace directory {cwd})"],
    content: Annotated[
        str,
        "The content to write to the file. When performing a full rewrite of an existing file or creating a new one, ALWAYS provide the COMPLETE intended content of the file, without any truncation or omissions. You MUST include ALL parts of the file, even if they haven't been modified. Do NOT include the line numbers in the content though, just the actual content of the file.",
    ],
) -> ToolResult:
    """
    Request to write content to a file. This tool is primarily used for **creating new files** or for scenarios where a **complete rewrite of an existing file is intentionally required**. If the file exists, it will be overwritten. If it doesn't exist, it will be created. This tool will automatically create any directories needed to write the file.

    Usage:
    write_to_file(path=<file path>, content=<file content>)

    Example: Requesting to write content to a file
    write_to_file(path="src/main.ts", content="console.log('Hello, world!');")
    """
    result: FileOpsResult = await FileOpsManager.get_instance(cwd).write_to_file(path, content)
    return ToolResult(result=result.diff, error=result.error)


CodebaseWriteTools = Tools(tools=[search_and_replace, insert_content, write_to_file])
