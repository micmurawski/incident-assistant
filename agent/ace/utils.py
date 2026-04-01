import yaml
from ace.playbook_core import Playbook

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
    reflections = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if (
                item.get("type") == "tool_use"
                and item.get("name") == "reflect"
                and item.get("result", {}).get("is_error") is not True
            ):
                reflections.append(item.get("input"))
    return reflections


def create_details_for_reflector(task: Task, playbook: Playbook) -> str:
    query = task.messages_history[0]["content"]

    assessment_msg = task.messages_history[-1]
    assessment = ""
    if isinstance(assessment_msg["content"], str):
        assessment = assessment_msg["content"]
    else:
        for content in assessment_msg["content"]:
            if content.get("type") == "text":
                assessment = content.get("text")
                break

    trajectory_yaml = yaml.dump(merge_tool_uses(task.messages_history[1:-1]), indent=4, sort_keys=False)

    res = "## Task\n\n"
    res += f"{query}\n\n"
    res += "## Assessment\n\n"
    res += f"{assessment}\n\n"
    res += "## Trajectory\n\n"
    res += f"{trajectory_yaml}\n\n"
    res += "## Playbook\n\n"
    res += f"{playbook.to_markdown(without_points=True)}\n\n"
    return res


if __name__ == "__main__":
    pass
