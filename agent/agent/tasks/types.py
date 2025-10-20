from enum import Enum
from typing import Literal, TypedDict


class TextContent(TypedDict, total=False):
    type: Literal["text"] = "text"
    content: str
    partial: bool


class ToolUse(TypedDict, total=False):
    type: Literal["tool_use"] = "tool_use"
    tool_name: str
    params: str
    partial: bool


class UsageContent(TypedDict):
    type: Literal["usage"] = "usage"
    input_tokens: int
    output_tokens: int


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


AssistantMessageContent = TextContent | ToolUse
