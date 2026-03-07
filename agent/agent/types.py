from typing import Any, List, Literal, Optional, Required, TypedDict

from anthropic.types import MessageParam as AnthropicMessage

ApiProvider = Literal["anthropic", "openai", "google", "ollama"]


class ApiHandlerCreateMessageMetadata(TypedDict, total=False):
    model: Optional[str] = None
    task_id: str
    previous_task_id: str
    suppress_previous_response_id: Optional[bool] = None
    store: Optional[bool] = None


class ApiMessage(AnthropicMessage, total=False):
    """Represents a message in the conversation."""

    role: str
    content: Any  # Can be string or list of content blocks
    ts: int
    is_summary: bool


class UsageChunk(TypedDict, total=False):
    """Usage information chunk"""

    type: Required[str] = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    total_cost: Optional[float] = None


class TextChunk(TypedDict, total=False):
    """Text content chunk"""

    type: Required[str] = "text"
    text: str = ""


class ReasoningChunk(TypedDict, total=False):
    """Reasoning/thinking content chunk"""

    type: Required[str] = "reasoning"
    text: str = ""


class ToolUse(TypedDict, total=False):
    type: Required[str] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]
    # Gemini: opaque signature for thought; must be passed back when sending tool_use in history
    thought_signature: Optional[bytes]


class ToolResult(TypedDict, total=False):
    type: Required[str] = "tool_result"
    tool_use_id: str
    content: str | dict | list[dict]


class GroundingChunk(TypedDict, total=False):
    """Grounding content chunk"""

    type: Required[str] = "grounding"
    sources: List[dict]


StreamChunk = UsageChunk | TextChunk | ReasoningChunk | GroundingChunk | ToolUse


class TokenUsage(TypedDict, total=False):
    total_input_tokens: int
    total_output_tokens: int
    total_cache_writes: int | None = None
    total_cache_reads: int | None = None
    total_cost: float
    context_tokens: int
