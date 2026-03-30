from typing import Optional

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import Hidden, ToolResult, tool


@tool(tags=["deploy"])
async def deploy_app(
    deploy_script_path: Hidden[str],
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """Deploy an application to a Kubernetes cluster."""
    cwd, script = deploy_script_path.rsplit("/", 1)
    result = await run_cli_command(cmd=["bash", script], cwd=cwd, env=env, timeout=None, stream=True, tail_lines=15)
    if result.error is None:
        return ToolResult(result="Deployment successful", error=None)
    else:
        return result


if __name__ == "__main__":
    import asyncio

    async def main():
        result = await deploy_app(deploy_script_path="/Users/micmur/GITHUB/o8s/services/robot-shop/k8s/deploy.sh")
        print(result.result)
        print(result.error)
    asyncio.run(main())
