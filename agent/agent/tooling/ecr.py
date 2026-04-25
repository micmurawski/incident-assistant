import json
from typing import Annotated, Literal, Optional

import yaml

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool


def _to_yaml_result(result: ToolResult) -> ToolResult:
    if result.error is not None or result.result is None:
        return result
    try:
        # Keep key order and block-style formatting for readable tool output.
        data = yaml.safe_dump(
            json.loads(result.result),
            sort_keys=False,
            default_flow_style=False,
            indent=2,
        )
        return ToolResult(result=data, error=None)
    except json.JSONDecodeError:
        # Preserve raw output if AWS CLI returns non-JSON content.
        return result


@tool(tags=["ecr"])
async def list_ecr_repositories(
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """List ECR repositories in the current AWS account and region."""
    result = await run_cli_command(
        ["aws", "ecr", "describe-repositories", "--output", "json"],
        env=env,
        trim_result=False,
    )
    return _to_yaml_result(result)


Repositories = Literal["robot-shop-mongodb", "robot-shop-mysql", "robot-shop-rabbitmq", "robot-shop-redis", "robot-shop-cart", "robot-shop-catalogue", "robot-shop-dispatch", "robot-shop-payment", "robot-shop-ratings", "robot-shop-shipping", "robot-shop-user", "robot-shop-web"]

@tool(tags=["ecr"])
async def list_ecr_repository_images(
    repository_name: Annotated[Repositories, "ECR repository name, e.g. 'robot-shop-cart'"],
    tag_status: Annotated[Literal["ANY", "TAGGED", "UNTAGGED"], "Filter image tags returned by ECR"] = "ANY",
    max_results: Annotated[int, "Maximum number of image details to return"] = 100,
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """List images for a specific ECR repository, including tags and pushed timestamps."""
    result = await run_cli_command(
        [
            "aws",
            "ecr",
            "describe-images",
            "--repository-name",
            repository_name,
            "--filter",
            f"tagStatus={tag_status}",
            "--max-results",
            str(max_results),
            "--output",
            "json",
        ],
        env=env,
        trim_result=False,
    )
    return _to_yaml_result(result)


EcrReadTools = Tools(tools=[
    list_ecr_repositories,
    list_ecr_repository_images,
])


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(list_ecr_repositories())
    print(result.result)
    #print(result.error)
    
    result = asyncio.run(list_ecr_repository_images(repository_name="robot-shop-cart"))
    print(result.result)
    #print(result.error)