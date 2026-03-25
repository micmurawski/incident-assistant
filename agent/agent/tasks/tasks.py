import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar
from uuid import uuid4

from agent.persistence.model import TaskModel
from agent.tasks.formatting import parse_markdown_checklist
from agent.tasks.types import TaskStatus, TodoItem, ToolUsage
from agent.types import ApiMessage

T = TypeVar("T", bound="Task")


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = field(default=TaskStatus.AWAITING_INPUT)
    todo_list: list[TodoItem] = field(default_factory=list)
    children: list[T] = field(default_factory=list)
    parent: T | None = None
    root: T | None = None
    assignee: str | None = None
    assigner: str | None = None

    conversation: list[ApiMessage] = field(default_factory=list)

    consecutive_mistakes_count: int = field(default=0)
    consecutive_mistakes_limit: int = field(default=3)
    tool_usage: list[ToolUsage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now())
    resolved_at: datetime | None = None

    def __repr__(self):
        todos = []
        for todo in self.todo_list:
            todos.append({
                "content": todo["content"],
                "status": todo["status"],
            })
        data = {
            "id": self.id,
            "status": self.status.value,
            "assignee": self.assignee,
            "assigner": self.assigner,
            "todos": todos,
        }
        return json.dumps(data)

    def __post_init__(self):
        if self.root is None:
            self.root = self

    def create_child_task(self, **kwargs) -> "Task":
        todo_list = kwargs.pop("todo_list", None)
        todo_list = todo_list or parse_markdown_checklist(kwargs.pop("todo_list_str", None))
        child_task = Task(
            parent=self,
            root=self.root,
            todo_list=todo_list,
            **kwargs,
        )
        self.children.append(child_task)
        return child_task

    def attempt_complete(self, raise_if_not_done: bool = True) -> bool:
        not_discarded_children = [
            task for task in self.children if not task.status == TaskStatus.DISCARDED
        ]
        if all(task.status == TaskStatus.DONE for task in not_discarded_children):
            self.status = TaskStatus.DONE
            self.resolved_at = datetime.now()
            return True
        if raise_if_not_done:
            raise ValueError("Task is not done. It still has dependencies that are not done.")
        return False

    def add_feedback(self, feedback: str):
        if self.status != TaskStatus.AWAITING_FEEDBACK:
            raise ValueError("Task is not awaiting feedback")
        self.conversation.append({"role": "user", "content": feedback})

    def remove_all_discarded(self):
        root = [self.root] if self.root else [self]
        while root:
            task = root.pop()
            task.children = [child for child in task.children if not child.status == TaskStatus.DISCARDED]
            root.extend(task.children)

    def get_todo_str(self) -> str:
        lines = []
        for todo in self.todo_list:
            if todo["status"] == "in_progress":
                lines.append(f"- [-] {todo['content']}")
            elif todo["status"] == "completed":
                lines.append(f"- [x] {todo['content']}")
            elif todo["status"] == "pending":
                lines.append(f"- [ ] {todo['content']}")
        return "\n".join(lines)

    def get_deepest_actionable_tasks(self, status: TaskStatus) -> list["Task"]:
        """BFS from root, returning AWAITING_INPUT/AWAITING_FEEDBACK tasks at the deepest level."""
        root = self.root or self

        deepest: list[Task] = []
        deepest_level = -1
        queue: list[tuple[Task, int]] = [(root, 0)]

        while queue:
            task, level = queue.pop(0)
            if task.status in status:
                if level > deepest_level:
                    deepest = [task]
                    deepest_level = level
                elif level == deepest_level:
                    deepest.append(task)
            queue.extend((child, level + 1) for child in task.children)

        return deepest
    
    def save(self, key: tuple[str, str] | None = None):
        conv = json.dumps(self.conversation)
        row = {
            "root_id": key[0] if key else self.root.id,
            "id": self.id,
            "status": self.status.value,
            "todo_list": json.dumps(self.todo_list),
            "children": json.dumps([child.id for child in self.children]),
            "parent": self.parent.id if self.parent else "",
            "root": self.root.id if self.root else "",
            "assignee": self.assignee or "",
            "assigner": self.assigner or "",
            "tool_usage": json.dumps(self.tool_usage),
            "conversation": conv,
            "last_message_ts": 0,
        }
        TaskModel.insert(row).on_conflict(
            conflict_target=[TaskModel.root_id, TaskModel.id],
            update={**row, "updated_at": datetime.now()},
        ).execute()
        for child in self.children:
            child.save(key=key or (self.root.id, self.id))

    def get_conversation_with_swapped_roles(self) -> list[dict]:
        # Deep copy so get_conversation_text_messages never mutates stored conversation
        # (shallow list copy would share message dicts; stripping text-only would remove
        # tool_use blocks and leave orphan tool_results → Anthropic 400 invalid params).
        return swap_roles_in_conversation(
            get_conversation_text_messages(copy.deepcopy(self.conversation))
        )


def swap_roles_in_conversation(conversation: list[dict]) -> list[dict]:
    """
    Swaps roles 'assistant' <-> 'user' in the given conversation list of messages.

    Args:
        conversation: List of message dicts, each containing a "role" key.

    Returns:
        New list of message dicts with roles swapped.
    """
    swapped = []
    for msg in conversation:
        msg_copy = msg.copy()
        if msg_copy.get("role") == "assistant":
            msg_copy["role"] = "user"
        elif msg_copy.get("role") == "user":
            msg_copy["role"] = "assistant"
        # Otherwise leave unchanged
        swapped.append(msg_copy)
    return swapped


def get_conversation_text_messages(conversation: list[dict]) -> list[dict]:
    """Return a text-only view of user/assistant messages for feedback. Does not mutate input."""
    selected_messages = []
    for msg in filter(lambda msg: msg.get("role") in ("user", "assistant"), conversation):
        content = msg.get("content")
        if isinstance(content, str):
            selected_messages.append(dict(msg))
        elif isinstance(content, list):
            selected_content = []
            for item in content:
                if item.get("type") == "text":
                    selected_content.append(item)
            if selected_content:
                selected_messages.append({**msg, "content": selected_content})
    return selected_messages


if __name__ == "__main__":
    task = Task(
        id="x123",
        todo_list=[TodoItem(id="1", content="Create a blog post", status="in_progress")],
    )
    task.create_child_task(id="x56", todo_list=[TodoItem(id="2", content="Write a blog post", status="in_progress")])
    # init_db()
    print(task.print_todo_list())
    task.persist("x123")
    print([t.id for t in task.get_list()])
