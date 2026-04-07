from typing import Annotated

from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

from .playbook_core import (BulletTag, Operation, Playbook,
                            PlaybookOperationError)


def _playbook_bullet_ids(playbook: Playbook) -> set[str]:
    bullet_ids: set[str] = set()
    for section in playbook.sections.values():
        for bullet in section.bullets:
            bullet_ids.add(bullet.id)
    return bullet_ids


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

    existing_bullet_ids = _playbook_bullet_ids(playbook)
    missing_bullet_ids: list[str] = []
    for bullet_tag in bullet_tags:
        bullet_id = bullet_tag["id"]
        if bullet_id not in existing_bullet_ids:
            missing_bullet_ids.append(bullet_id)
    if missing_bullet_ids:
        missing_ids = ", ".join(repr(bullet_id) for bullet_id in sorted(set(missing_bullet_ids)))
        return ToolResult(
            result=None,
            error=f"Unknown bullet ids: {missing_ids}. Please only tag bullets that exist in playbook.",
        )

    try:
        playbook.apply_bullet_tags(bullet_tags)
    except PlaybookOperationError as e:
        return ToolResult(result=None, error=str(e))
    return ToolResult(result="Playbook reflected and points updated")

ReflectorTools = Tools(tools=[reflect])
CuratorTools = Tools(tools=[update_playbook])
