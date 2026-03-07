import asyncio
import os
import shlex
from typing import Annotated, Optional

from agent.settings import SettingsManager
from agent.tooling.decorators import ToolResult, Tools, tool

MAX_OUTPUT_LENGTH = 4000


@tool(tags=["cli"])
async def bash(
    command: Annotated[
        str,
        "The CLI command to run as a string, e.g., 'ls -la' or 'npm run dev'. Each argument must be a separate string; do not concatenate into one string.",
    ],
    cwd: Annotated[Optional[str], "Working directory for command execution (default: {cwd})"] = None,
    env: Annotated[Optional[dict[str, str]], "Environment variables for the process (default: None)"] = None,
) -> ToolResult:
    """
    Run a CLI command using a list of arguments. Use for system operations or terminal commands related to the user's task.
    
    - Use only safe, clear commands.
    - Prefer relative paths for consistency.
    - Use `cwd` to specify a working directory if needed.
    - Avoid scripts when a single command does the job.

    **Usage:**  
    bash(command='your command args', cwd="optional/path")

    **Examples:**  
    bash(command='npm run dev')  
    bash(command='ls -la', cwd="/home/user/projects")
    """
    cwd = cwd or SettingsManager.get_instance().get("workspace.path") or os.getcwd()
    try:
        args = shlex.split(command.strip())
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await process.communicate()
        stdout_decoded = stdout.decode("utf-8")
        stderr_decoded = stderr.decode("utf-8")
        # Combine stdout and stderr if error
        error_msg = stderr_decoded if process.returncode != 0 else None

        # Trim logic
        total_length = len(stdout_decoded)
        trim_length = MAX_OUTPUT_LENGTH
        output_to_return = stdout_decoded
        if total_length > trim_length:
            # Show start and end, ellipsis in the middle
            head = stdout_decoded[:trim_length//2]
            tail = stdout_decoded[-trim_length//2:]
            output_to_return = (
                f"{head}\n...[trimmed {total_length - trim_length} characters]...\n{tail}"
            )

        # Optionally also trim error message
        if error_msg and len(error_msg) > 1000:
            error_msg = error_msg[:800] + f"\n...[trimmed {len(error_msg) - 800} characters of stderr]..."

        return ToolResult(result=output_to_return, error=error_msg)
    except Exception as e:
        return ToolResult(result=None, error=str(e))


CliTools = Tools(tools=[bash])
