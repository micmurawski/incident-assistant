import asyncio
from typing import Annotated, Optional

from agent.context import Context
from agent.tooling.decorators import Hidden, tool


@tool(tags=["cli"])
async def execute_command(
    context: Hidden[Context],
    command: Annotated[
        str,
        "The CLI command to execute. This should be valid for the current operating system. Ensure the command is properly formatted and does not contain any harmful instructions.",
    ],
    cwd: Annotated[Optional[str], "The working directory to execute the command in (default: {cwd})"] = None,
) -> str:
    """
    Request to execute a CLI command on the system. Use this when you need to perform system operations or run specific commands to accomplish any step in the user's task.
    You must tailor your command to the user's system and provide a clear explanation of what the command does.
    For command chaining, use the appropriate chaining syntax for the user's shell.
    Prefer to execute complex CLI commands over creating executable scripts, as they are more flexible and easier to run.
    Prefer relative commands and paths that avoid location sensitivity for terminal consistency, e.g: \`touch ./testdata/example.file\`, \`dir ./examples/model1/data/yaml\`, or \`go test ./cmd/front --config ./cmd/front/config.yml\`.
    If directed by the user, you may open a terminal in a different directory by using the \`cwd\` parameter.
    Usage:
    execute_command_tool(command=<Your CLI command here>, cwd=<Optional working directory path>)

    Example: Requesting to execute npm run dev
    execute_command_tool(command="npm run dev")

    Example: Requesting to execute ls in a specific directory if directed
    execute_command_tool(command="ls -la", cwd="/home/user/projects")
    """
    if cwd is None:
        cwd = context.cwd
    result = await asyncio.create_subprocess_exec(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd)
    return result.stdout.decode("utf-8")
