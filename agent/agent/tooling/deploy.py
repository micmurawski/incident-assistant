from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import ToolResult, tool


@tool(tags=["deploy"])
async def deploy_app() -> ToolResult:
    """Deploy an application to a Kubernetes cluster."""
    return await run_cli_command(["./deploy.sh"])
