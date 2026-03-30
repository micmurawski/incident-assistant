from typing import Annotated

from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

from .playbook_core import (BulletTag, Operation, Playbook,
                            PlaybookOperationError)


@tool(tags=["ace", "curator"])
async def update_playbook(
    playbook: Hidden[Playbook],
    reasoning: Annotated[str, "Your chain of thought / reasoning / thinking process, detailed analysis and calculations here"],
    operations: Annotated[list[Operation], "The operations to perform on the playbook"],
) -> ToolResult:
    try:
        playbook.apply_operations(operations)
    except PlaybookOperationError as e:
        return ToolResult(result=None, error=str(e))
    return ToolResult(result="Playbook updated")


@tool(tags=["ace", "reflector"])
async def reflect(
    playbook: Hidden[Playbook],
    reasoning: Annotated[str, "Your chain of thought / reasoning / thinking process, detailed analysis and calculations"],
    error_identification: Annotated[str, "What specifically went wrong in the reasoning?"],
    root_cause_analysis: Annotated[str, "Why did this error occur? What concept was misunderstood?"],
    correct_approach: Annotated[str, "What should the model have done instead?"],
    key_insight: Annotated[str, "What strategy, formula, or principle should be remembered to avoid this error?"],
    bullet_tags: Annotated[list[BulletTag], "The tags for the bulletpoints"],
) -> ToolResult:
    return ToolResult(result="Playbook reflected")

ReflectorTools = Tools(tools=[reflect])
CuratorTools = Tools(tools=[update_playbook])
