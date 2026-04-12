from collections.abc import Sequence

from ace.playbook_core import Playbook
from ace.yaml_dump import dump_yaml_multiline
from agent.persistence.task_queries import Task

MAX_TOOL_RESULT_LENGTH = 1000


def collect_data_on_task(root: Task, data: dict):
    if root.assignee not in data:
        data[root.assignee] = []

    data[root.assignee].append(
        {
            "conversation": root.conversation,
            "trajectory": parse_trajectory(root.messages_history),
        }
    )
    for child_task in root.children:
        collect_data_on_task(child_task, data)


def trim_content(content: str) -> str:
    if len(content) > MAX_TOOL_RESULT_LENGTH:
        head = content[:MAX_TOOL_RESULT_LENGTH // 2]
        tail = content[-MAX_TOOL_RESULT_LENGTH // 2:]
        return f"{head}...[trimmed {len(content) - MAX_TOOL_RESULT_LENGTH} characters]...{tail}"
    return content


def merge_tool_uses(messages: list[dict]) -> list[dict]:
    """Attach each tool_result onto its tool_use as ``result``, then drop tool_result blocks."""
    tool_use_by_id: dict[str, dict] = {}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") == "tool_use":
                tool_use_by_id[item["id"]] = item

    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") != "tool_result":
                continue
            tu_id = item.get("tool_use_id")
            if tu_id in tool_use_by_id:
                tool_use_by_id[tu_id]["result"] = {
                    "content": item.get("content"),
                    "is_error": item.get("is_error", False),
                }

    merged: list[dict] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            merged.append(message)
            continue
        new_content = []
        for b in content:
            if b.get("type") == "tool_result":
                continue
            if b.get("type") == "tool_use":
                b = {k: v for k, v in b.items() if k != "id"}
            new_content.append(b)
        if not new_content:
            continue
        merged.append({**message, "content": new_content})
    return merged


def trim_trajectory(messages: list[dict]) -> list[dict]:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") == "tool_use":
                if item.get("name") == "assign_task":
                    continue
                else:
                    # trim result.content
                    content_length = len(item["result"]["content"])
                    if content_length > MAX_TOOL_RESULT_LENGTH:
                        item["result"]["content"] = trim_content(
                            item["result"]["content"]
                        )
    return messages


def parse_trajectory(messages: list[dict]) -> list[dict]:
    merged = merge_tool_uses(messages)
    return merged


def get_reflections(messages: list[dict]) -> list[dict]:
    """Collect inputs from successful ``reflect`` tool calls only.

    Raw transcripts keep ``tool_result`` on separate user messages; without
    :func:`merge_tool_uses`, assistant ``tool_use`` blocks have no ``result``,
    so ``is_error`` is missing and failed reflects were wrongly included.
    """
    merged = merge_tool_uses(messages)
    reflections: list[dict] = []
    for message in merged:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") != "tool_use" or item.get("name") != "reflect":
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            if result.get("is_error") is True:
                continue
            inp = item.get("input")
            if inp is not None:
                reflections.append(inp)
    return reflections


def _reflector_task_section(task: Task) -> str:
    """Query, assessment, and trajectory for one task (no playbook)."""
    query = task.conversation[0]["content"]

    assessment_msg = task.messages_history[-1]
    assessment = ""
    if isinstance(assessment_msg["content"], str):
        assessment = assessment_msg["content"]
    else:
        for content in assessment_msg["content"]:
            if content.get("type") == "text":
                assessment = content.get("text")
                break

    trajectory_yaml = dump_yaml_multiline(
        merge_tool_uses(task.messages_history[1:-1])
    )

    res = f"## Task: {task.id}\n\n"
    res += f"{query}\n\n"

    if assessment != "":
        res += "### Assessment\n\n"
        res += f"{assessment}\n\n"

    res += "### Trajectory\n\n"
    res += f"{trajectory_yaml}\n\n"
    return res


def _playbook_appendix(playbook: Playbook) -> str:
    return f"## Playbook\n\n{playbook.to_markdown(without_points=True)}\n\n"


def format_reflector_details_for_task(task: Task, playbook: Playbook) -> str:
    """Build reflector prompt text: one task trajectory plus the playbook."""
    return _reflector_task_section(task) + _playbook_appendix(playbook)


def format_reflector_details_for_tasks(tasks: Sequence[Task], playbook: Playbook) -> str:
    """Build reflector prompt text: multiple task trajectories, then the playbook once."""
    sections = [_reflector_task_section(t) for t in tasks]
    body = "\n".join(sections) if sections else ""
    return body + _playbook_appendix(playbook)


def format_reflector_task_data_for_task(task: Task) -> str:
    """Task trace and assessment only (for V2 prompts where playbook is a separate block)."""
    return _reflector_task_section(task)


def format_reflector_task_data_for_tasks(tasks: Sequence[Task]) -> str:
    """Multiple task traces only (for V2 prompts where playbook is a separate block)."""
    sections = [_reflector_task_section(t) for t in tasks]
    return "\n".join(sections) if sections else ""


if __name__ == "__main__":
    pass
