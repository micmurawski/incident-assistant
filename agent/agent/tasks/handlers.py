from .formatting import parse_markdown_checklist
from .tasks import Task
from .types import TodoItem


def update_todo_list_handler(
    task: Task,
    raw_todo_list: str,
):
    todo_list: list[TodoItem] = parse_markdown_checklist(raw_todo_list)
    task.todo_list = todo_list
    task.persist()
