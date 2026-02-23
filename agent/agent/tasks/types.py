from enum import Enum
from typing import Literal, TypedDict


class TaskStatus(str, Enum):
    AWAITING_INPUT = "AWAITING_INPUT"
    AWAITING_FEEDBACK = "AWAITING_FEEDBACK"
    DONE = "DONE"
    DISCARDED = "DISCARDED"


class TodoItem(TypedDict):
    id: str
    content: str
    status: Literal["completed", "in_progress", "pending"]


class ToolUsage(TypedDict, total=False):
    name: str
    input: dict
