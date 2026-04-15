from typing import Annotated, Optional

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
    playbooks: Hidden[dict[str, Playbook]],
    reflector_assignee: Hidden[str],
    reasoning: Annotated[str, "Your chain of thought / reasoning / thinking process, detailed analysis and calculations"],
    error_identification: Annotated[str, "What specifically went wrong in the reasoning?"],
    root_cause_analysis: Annotated[str, "Why did this error occur? What concept was misunderstood?"],
    correct_approach: Annotated[str, "What should the model have done instead?"],
    key_insight: Annotated[str, "What strategy, formula, or principle should be remembered to avoid this error?"],
    bullet_tags: Annotated[list[BulletTag], "The tags for the bulletpoints"],
    useful_facts: Annotated[
        Optional[list[str]],
        "A list of verified, reusable facts about the app's architecture/config discovered in this trace",
    ] = None,
    playbook_amendment: Annotated[
        Optional[str],
        "One NEW heuristic bullet that would have prevented this failure (for curator synthesis)",
    ] = None,
) -> ToolResult:
    playbook = playbooks.get(reflector_assignee)
    if playbook is None:
        available = ", ".join(sorted(playbooks.keys()))
        return ToolResult(
            result=None,
            error=(
                f"Unknown assignee: {reflector_assignee!r}. "
                f"Available assignees: {available}."
            ),
        )

    existing_bullet_ids = _playbook_bullet_ids(playbook)
    missing_bullet_ids: list[str] = []
    for bullet_tag in bullet_tags:
        bullet_id = bullet_tag["id"]
        if bullet_id not in existing_bullet_ids:
            missing_bullet_ids.append(bullet_id)
    if missing_bullet_ids:
        missing_ids = ", ".join(repr(bullet_id) for bullet_id in sorted(set(missing_bullet_ids)))
        available_ids = ", ".join(repr(bullet_id) for bullet_id in sorted(existing_bullet_ids))
        return ToolResult(
            result=None,
            error=(
                f"Unknown bullet ids: {missing_ids}. "
                f"Please only tag bullets that exist in playbook. "
                f"Available bullet ids: {available_ids}."
            ),
        )

    try:
        playbook.apply_bullet_tags(bullet_tags)
    except PlaybookOperationError as e:
        return ToolResult(result=None, error=str(e))
    return ToolResult(result="Playbook reflected and points updated")


@tool(tags=["ace", "reflector"])
async def reflect_on_assignment(
    playbooks: Hidden[dict[str, Playbook]],
    reflector_assignee: Hidden[str],
    assignee: Annotated[
        str,
        "Delegated assignee whose curator should receive this reflection.",
    ],
    reasoning: Annotated[str, "Your chain of thought / reasoning / thinking process, detailed analysis and calculations"],
    error_identification: Annotated[str, "What specifically went wrong in the reasoning?"],
    root_cause_analysis: Annotated[str, "Why did this error occur? What concept was misunderstood?"],
    correct_approach: Annotated[str, "What should the model have done instead?"],
    key_insight: Annotated[str, "What strategy, formula, or principle should be remembered to avoid this error?"],
    useful_facts: Annotated[
        Optional[list[str]],
        "A list of verified, reusable facts about the app's architecture/config discovered in this trace",
    ] = None,
) -> ToolResult:
    if assignee not in playbooks:
        available = ", ".join(sorted(playbooks.keys()))
        return ToolResult(
            result=None,
            error=(
                f"Unknown delegated assignee: {assignee!r}. "
                f"Available assignees: {available}."
            ),
        )

    source_playbook = playbooks.get(reflector_assignee)
    if source_playbook is None:
        available = ", ".join(sorted(playbooks.keys()))
        return ToolResult(
            result=None,
            error=(
                f"Unknown reflector_assignee: {reflector_assignee!r}. "
                f"Available assignees: {available}."
            ),
        )
    return ToolResult(result="Reflection on assignment captured")


ReflectorTools = Tools(tools=[reflect, reflect_on_assignment])
CuratorTools = Tools(tools=[update_playbook])
