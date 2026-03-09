from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import Hidden, ToolResult, tool


@tool(tags=["deploy"])
async def deploy_app(
    cwd: Hidden[str],
    deploy_script_path: Hidden[str],
    env: Hidden[dict[str, str]],
) -> ToolResult:
    """Deploy an application to a Kubernetes cluster."""
    return await run_cli_command([f"./{cwd}/{deploy_script_path}"], cwd=cwd, env=env)
