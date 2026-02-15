import os
from typing import Annotated, Optional, TypedDict

from agent.code_index.models import VectorStoreSearchResult
from agent.context import Context
from agent.file_ops import FileOpsResult
from agent.telemetry_service import get_telemetry_service

from .decorators import Hidden, Tools, tool

logging = get_telemetry_service()

@tool(tags=["read", "codebase"])
async def codebase_search(
    context: Hidden[Context],
    query: Annotated[
        str, "The search query. Reuse the user's exact wording/question format unless there's a clear reason not to."
    ],
    path: Annotated[
        Optional[str],
        "Limit search to specific subdirectory (relative to the current workspace directory {cwd}. Leave empty for entire workspace",
    ] = None,
) -> str:
    """Find files most relevant to the search query using semantic search.
    Searches based on meaning rather than exact text matches.
    By default searches entire workspace. Reuse the user's exact wording unless there's a clear reason not to - their phrasing often helps semantic search.
    Queries MUST be in English (translate if needed).

    Usage:
    codebase_search(query=<Your natural language query here>, path=<Optional subdirectory path>)

    Example:
    codebase_search(query="User login and password hashing", path="src/auth")
    """
    path = os.path.normpath(path) if path else None
        
    results: list[VectorStoreSearchResult] = await context.code_index_search_service.search_index(query, path)
    
    if results and len(results) > 0:
        return

    output_lines = [f"Query: {query}", "Results:"]
    for result in results:
        payload = result.payload or {}
        file_path = payload.get("file_path")
        if not file_path:
            continue
        code_chunk = str(payload.get("code_chunk", "")).strip()
        output_lines.append(f"File path: {os.path.relpath(result.payload.get('file_path'), context.cwd)}")
        output_lines.append(f"Score: {result.score}")
        output_lines.append(f"Lines: {payload.get('start_line')}-{payload.get('end_line')}")
        output_lines.append(f"Code Chunk: {code_chunk}")
        output_lines.append("")

    return "\n".join(output_lines)


@tool(tags=["read", "codebase"])
async def get_list_code_definitions_names_descriptions(
    context: Hidden[Context],
    path: Annotated[
        str,
        "The path of the file or directory (relative to the current working directory {cwd}) to analyze. When given a directory, it lists definitions from all top-level source files.",
    ],
) -> str:
    """Request to list definition names (classes, functions, methods, etc.) from source code. This tool can analyze either a single file or all files at the top level of a specified directory. It provides insights into the codebase structure and important constructs, encapsulating high-level concepts and relationships that are crucial for understanding the overall architecture

    Usage:
    get_list_code_definitions_names_descriptions(path="src/main.ts")

    Example: Requesting to list definitions in a specific directory
    get_list_code_definitions_names_descriptions(path="src")
    """
    res: FileOpsResult = await context.file_ops_manager.list_code_definitions_names_descriptions(path)
    return res.diff


@tool(tags=["codebase", "read"])
async def read_file(
    context: Hidden[Context],
    path: Annotated[str, "File path (relative to workspace directory {cwd})"],
    start_line: Annotated[Optional[int], "Start line number (1-based) for range reading (default: 1)"] = 1,
    end_line: Annotated[
        Optional[int], "End line number (1-based) for range reading (default: last line of file)"
    ] = None,
) -> str:
    """
    Request to read the contents of a file for easy reference when creating diffs or discussing code. Use line ranges to efficiently read specific portions of large files.
    Usage:
    read_file(path="src/main.ts", start_line=1, end_line=10)

    Example: Requesting to read the first 10 lines of a file
    read_file(path="src/main.ts", start_line=1, end_line=10)

    Example: Requesting to read the entire file
    read_file(path="src/main.ts")

    Example: Requesting to read the last 10 lines of a file
    read_file(path="src/main.ts", end_line=-10)
    """
    res: FileOpsResult = await context.file_ops_manager.read_file(path, start_line, end_line)
    return res.content


class FileContent(TypedDict):
    path: str
    start_line: Annotated[Optional[int], "Start line number (1-based) for range reading (default: 1)"] = 1
    end_line: Annotated[Optional[int], "End line number (1-based) for range reading (default: last line of file)"] = (
        None
    )


@tool(tags=["codebase", "read"])
async def read_multiple_files(
    context: Hidden[Context],
    files: Annotated[list[FileContent], "List of file properties to read (relative to workspace directory {cwd})"],
) -> str:
    """
    Request to read the contents of multiple files for easy reference when creating diffs or discussing code. Use this when you need to read the contents of multiple files at once.
    Usage:
    read_multiple_files(files=[{"path": "src/main.ts", "start_line": 1, "end_line": 10}, {"path": "src/utils.ts", "start_line": 1, "end_line": 10}])

    Example: Requesting to read the contents of multiple files
    read_multiple_files(files=[{"path": "src/main.ts", "start_line": 1, "end_line": 10}, {"path": "src/utils.ts", "start_line": 1, "end_line": 10}])
    """
    res: FileOpsResult = await context.file_ops_manager.read_multiple_files(files)
    return res.content


@tool(tags=["codebase", "read"])
async def search_file(
    context: Hidden[Context],
    path: Annotated[
        str,
        "The path of the directory to search in (relative to the current workspace directory {cwd}). This directory will be recursively searched.",
    ],
    regex: Annotated[str, "The regular expression pattern to search for. Uses Rust regex syntax."],
    file_pattern: Annotated[
        Optional[str],
        "Glob pattern to filter files (e.g., '*.ts' for TypeScript files). If not provided, it will search all files (*).",
    ] = None,
) -> str:
    """
    Request to perform a regex search across files in a specified directory, providing context-rich results. This tool searches for patterns or specific content across multiple files, displaying each match with encapsulating context.
    Usage:
    search_file(path=<directory path>, regex=<regex pattern>, file_pattern=<file pattern>)

    Example: Requesting to search for all .ts files in the current directory
    search_file(path=".", regex=".*", file_pattern="*.ts")
    """
    res: FileOpsResult = await context.file_ops_manager.search_file(path, regex, file_pattern)
    return res.content


@tool(tags=["codebase", "read"])
async def list_files(
    context: Hidden[Context],
    path: Annotated[
        str, " The path of the directory to list contents for (relative to the current workspace directory {cwd})"
    ],
    recursive: Optional[Annotated[
        bool, "Whether to list files recursively. Use true for recursive listing, false or omit for top-level only."
    ]] = False,
) -> str:
    """
    Request to list files and directories within the specified directory. If recursive is true, it will list all files and directories recursively. If recursive is false or not provided, it will only list the top-level contents. Do not use this tool to confirm the existence of files you may have created, as the user will let you know if the files were created successfully or not

    Usage:
    list_files(path=<directory path>, recursive=<true/false>)

    Example: Requesting to list the files in the current directory
    list_files(path=".", recursive=false)

    Example: Requesting to list the files in the current directory recursively
    list_files(path=".", recursive=true)
    """
    res: FileOpsResult = await context.file_ops_manager.list_files_tool(path, recursive)
    return res.content


CodebaseReadTools = Tools(
    tools=[
        codebase_search,
        get_list_code_definitions_names_descriptions,
        read_file,
        read_multiple_files,
        search_file,
        list_files,
    ]
)
