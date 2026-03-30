import json
import os
from typing import Annotated, Optional

import yaml

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "1-node-default-vpc")


@tool(tags=["eks"])
async def scale_node_group(
    node_group: Annotated[str, "The name of the node group to scale"],
    desired_size: Annotated[int, "The desired size of the node group"],
    min_size: Annotated[int, "The minimum size of the node group"],
    max_size: Annotated[int, "The maximum size of the node group"],
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """Scale a node group to a desired size."""
    scaling_args = []
    if desired_size is not None:
        scaling_args.append(f"desiredSize={desired_size}")
    if min_size is not None:
        scaling_args.append(f"minSize={min_size}")
    if max_size is not None:
        scaling_args.append(f"maxSize={max_size}")
    scaling_config = ",".join(scaling_args)

    return await run_cli_command(
        [
            "aws", "eks", "update-nodegroup-config",
            "--cluster-name", CLUSTER_NAME,
            "--nodegroup-name", node_group,
            "--scaling-config", scaling_config,
        ],
        env=env,
    )


@tool(tags=["eks"])
async def get_node_group_status(
    node_group: Annotated[str, "The name of the node group to get the status of"],
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """Get the status of a node group."""
    return await run_cli_command(
        ["aws", "eks", "describe-nodegroup", "--cluster-name", CLUSTER_NAME, "--nodegroup-name", node_group],
        env=env,
    )


@tool(tags=["eks"])
async def get_cluster_info(
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """Get information about the EKS cluster."""
    result = await run_cli_command(
        ["aws", "eks", "describe-cluster", "--name", CLUSTER_NAME],
        env=env,
    )
    data = yaml.dump(json.loads(result.result))
    return ToolResult(result=data, error=None)

EksReadTools = Tools(tools=[
    get_node_group_status,
    get_cluster_info,
])

EksWriteTools = Tools(tools=[
    scale_node_group,
])


if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_cluster_info()
        print(result.result)
    asyncio.run(main())
