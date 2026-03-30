import yaml

from agent.persistence.task_queries import Task, fetch_last_root_tasks


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


def get_reflections(messages: list[dict]) -> list[dict]:
    reflections = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if item.get("type") == "tool_use":
                if item.get("name") == "reflect":
                    reflections.append(item.get("input"))
    return reflections

def process_task(task: Task) -> dict:
    query = task.conversation[0]["content"]
    assessment = task.conversation[-1]["content"]
    trajectory = merge_tool_uses(task.messages_history[:-1])
    trajectory_yaml = yaml.dump(trajectory, indent=4, sort_keys=False)
    return {
        "query": query,
        "assessment": assessment,
        "trajectory": trajectory_yaml,
    }


def create_details_for_reflector(task: Task) -> str:
    data = process_task(task)

    res = "## Task\n\n"
    res += f"{data['query']}\n\n"
    res += "## Assessment\n\n"
    res += f"{data['assessment']}\n\n"
    res += "## Trajectory\n\n"
    res += f"{data['trajectory']}\n\n"
    return res


if __name__ == "__main__":
    tasks = fetch_last_root_tasks(last_n=1)
    for task in tasks:
        process_task(task)
