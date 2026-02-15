import json
from dataclasses import dataclass, field
from typing import Callable, ClassVar, TypeVar
from uuid import uuid4

from anthropic.types.text_block_param import \
    TextBlockParam as AnthropicTextBlockParam

from agent.message_queue_service import MessageQueueService
from agent.persistence.model import Task as TaskModel
from agent.types import ApiMessage, TokenUsage

from .types import AssistantMessageContent, TaskStatus, TodoItem, ToolUsage


def todo_item_to_txt(todo_item: TodoItem, level: int = 0) -> str:
    return f"{'\t' * level}{todo_item['id']} | {todo_item['content']} | {todo_item['status']}"


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
    last_message_ts: int | None = None

    consecutive_mistakes_count: int = field(default=0)
    consecutive_mistakes_limit: int = field(default=3)
    tool_usage: list[ToolUsage] = field(default_factory=list)

    message_queue: ClassVar[MessageQueueService] = MessageQueueService.get_instance()
    _message_queue_state_change_handler: ClassVar[Callable[[MessageQueueService], None]] = lambda: None

    is_waiting_for_first_chunk: bool = field(default=False)
    is_streaming: bool = field(default=False)
    current_streaming_content_index: int = field(default=0)
    current_streaming_did_checkpoint: bool = field(default=False)
    assistant_message_content: list[AssistantMessageContent] = field(default_factory=list)

    present_assistant_message_locked: bool = field(default=False)
    present_assistant_message_has_pending_updates: bool = field(default=False)
    user_message_content: list[AnthropicTextBlockParam] = field(default_factory=list)
    user_message_content_ready: bool = field(default=False)

    did_reject_tool: bool = field(default=False)
    did_already_use_tool: bool = field(default=False)
    did_complete_reading_stream: bool = field(default=False)

    assistant_message_parser: ClassVar[None] = None
    _last_used_instruction: str | None = None
    skip_prev_response_id_once: bool = field(default=False)

    _token_usage_snapshot: TokenUsage | None = None
    _token_usage_snapshot_ts: int | None = None

    def __post_init__(self):
        if self.root is None:
            self.root = self

    def persist(self, session_id: str):
        root = self.root or self

        # dfs and persist all tasks
        def dfs(task: Task):
            print(f"Persisting task {task.id}")
            TaskModel.create_or_update(
                session=session_id,
                id=task.id,
                children=[child.id for child in task.children],
                status=task.status.value,
                todo_list=json.dumps(task.todo_list),
                parent=task.parent.id if task.parent else None,
                root=task.root.id if task.root else None,
                assignee=task.assignee,
                assigner=task.assigner,
            )
            for child in task.children:
                dfs(child)

        dfs(root)

    def create_child_task(self, **kwargs) -> "Task":
        child_task = Task(
            parent=self,
            root=self.root,
            **kwargs,
        )
        self.children.append(child_task)
        return child_task

    def is_done(self) -> bool:
        return self.status == TaskStatus.DONE

    def is_discarded(self) -> bool:
        return self.status == TaskStatus.DISCARDED

    def is_awaiting_input(self) -> bool:
        return self.status == TaskStatus.AWAITING_INPUT

    def is_awaiting_review(self) -> bool:
        return self.status == TaskStatus.AWAITING_REVIEW

    def _move_to_done(self, raise_if_not_done: bool = True) -> bool:
        if all(task.is_done() for task in self.children if not task.is_discarded()):
            self.status = TaskStatus.DONE
            return True
        if raise_if_not_done:
            raise ValueError("Task is not done. It still has dependencies that are not done.")
        return False

    def add_input(self, message: ApiMessage):
        if self.status != TaskStatus.AWAITING_INPUT:
            raise ValueError("Task is not awaiting input")
        self.status = TaskStatus.AWAITING_FEEDBACK
        self.conversation.append(message)

    def add_feedback(self, message: ApiMessage, approve: bool = False, discard: bool = False):
        if self.status != TaskStatus.AWAITING_FEEDBACK:
            raise ValueError("Task is not awaiting feedback")

        self.conversation.append(message)
        if approve:
            self._move_to_done()
            return

        if discard:
            self.status = TaskStatus.DISCARDED
            return

    def remove_all_discarded(self):
        root = [self.root] if self.root else [self]
        while root:
            task = root.pop()
            task.children = [child for child in task.children if not child.is_discarded()]
            root.extend(task.children)

    def print_todo_list(self, level: int = 0) -> str:
        result = f"{'\t' * level}Todo List:\n"
        for todo in self.todo_list:
            result += todo_item_to_txt(todo, level) + "\n"
        result += "\n"
        for child in self.children:
            result += child.print_todo_list(level + 1)
        return result

    def get_list(self) -> list[T]:
        result: list[T] = []

        roots: list[T] = [self.root]
        while roots:
            root = roots.pop()
            result.append(root)
            roots.extend(root.children)
        return result


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
