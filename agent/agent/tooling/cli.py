import asyncio
import os
import shlex
from typing import Annotated, Optional

from agent.settings import SettingsManager
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool


@tool(tags=["cli"])
async def bash(
    cwd: Hidden[Optional[str]],
    env: Hidden[Optional[dict[str, str]]],
    command: Annotated[
        str,
        "The bash command to run as a string, e.g., 'ls -la' or 'npm run dev'. Each argument must be a separate string; do not concatenate into one string.",
    ],
) -> ToolResult:
    """
    Run a bash command using a list of arguments. Use for system operations or terminal commands related to the user's task.

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
    env = {**os.environ.copy(), **(env or {})}

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

        return ToolResult(result=stdout_decoded, error=error_msg)
    except Exception as e:
        return ToolResult(result=None, error=str(e))


CliTools = Tools(tools=[bash])
