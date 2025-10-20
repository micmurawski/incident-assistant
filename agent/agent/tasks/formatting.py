import hashlib
import re

from .types import TodoItem


def parse_markdown_checklist(markdown_checklist: str) -> list[TodoItem]:
    if not isinstance(markdown_checklist, str):
        return []
    lines = [line.strip() for line in markdown_checklist.splitlines() if line.strip()]
    todos: list[TodoItem] = []
    for line in lines:
        match = re.match(r"^\[\s*([ xX\-~])\s*\]\s+(.+)$", line)
        if not match:
            continue
        status: str = "pending"
        if match.group(1) in ("x", "X"):
            status = "completed"
        elif match.group(1) in ("-", "~"):
            status = "in_progress"
        # Generate id as md5 hash of content + status
        id_bytes = (match.group(2) + status).encode("utf-8")
        id = hashlib.md5(id_bytes).hexdigest()
        todos.append({"id": id, "content": match.group(2), "status": status})
    return todos


def normalize_status(status: str) -> str:
    if status in ("completed", "in_progress"):
        return status
    return "pending"


def todo_list_to_markdown_checklist(todo_list: list[TodoItem]) -> str:
    todos = []
    todo: TodoItem
    for todo in todo_list:
        box = "[ ]"
        if todo["status"] == "completed":
            box = "[x]"
        elif todo["status"] == "in_progress":
            box = "[-]"
    todos.append(f"{box} {todo['content']}")
    return "\n".join(todos)
