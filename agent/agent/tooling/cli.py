from typing import Annotated, Optional

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool


@tool(tags=["cli"])
async def bash(
    cwd: Hidden[Optional[str]],
    env: Hidden[Optional[dict[str, str]]],
    command: Annotated[
        str,
        "The bash command to run as a string, e.g., 'ls -la' or 'npm run dev'. Each argument must be a separate string; do not concatenate into one string.",
    ],
    timeout: Annotated[Optional[int], "Command timeout in seconds (default 120s)"] = 120,
) -> ToolResult:
    """
    Run a bash command using a list of arguments. Use for system operations or terminal commands related to the user's task.

    - Use only safe, clear commands.
    - Prefer relative paths for consistency.
    - Use `cwd` to specify a working directory if needed.
    - Avoid scripts when a single command does the job.

    **Usage:**  
    bash(command='your command args')

    **Examples:**  
    bash(command='npm run dev')  
    """
    cmd = command.strip()
    if not cmd:
        return await run_cli_command(cmd=["bash", "-c", ":"], cwd=cwd, env=env, timeout=300)
    return await run_cli_command(
        cmd=["bash", "-c", cmd],
        cwd=cwd,
        env=env,
        timeout=timeout,  # Increased default timeout for potentially streamed long commands
    )


CliTools = Tools(tools=[bash])
