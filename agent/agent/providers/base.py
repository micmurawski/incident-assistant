from dataclasses import dataclass
from typing import Any, AsyncIterator, Coroutine, Dict, List, Literal, Optional, TypedDict, Required

from anthropic.types import MessageParam as AnthropicMessage

ApiProvider = Literal["anthropic", "openai", "google", "ollama"]


class ApiHandlerCreateMessageMetadata(TypedDict, total=False):
    model: Optional[str] = None
    task_id: str
    previous_task_id: str
    suppress_previous_response_id: Optional[bool] = None
    store: Optional[bool] = None


class ApiHandler:
    """
    Base class for API handlers.
    This should be implemented based on your specific API integration.
    """

    def create_message(
        self,
        system_prompt: str,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Creates a streaming message.
        Should yield chunks with 'type' field indicating 'text' or 'usage'.
        """
        raise NotImplementedError

    def get_model(self) -> dict:
        """Returns the model configuration for the API handler."""
        raise NotImplementedError

    async def count_tokens(self, content_blocks: List[Dict[str, Any]]) -> Coroutine[Any, Any, int]:
        """Counts tokens in the given content blocks."""
        raise NotImplementedError


class ApiMessage(TypedDict, total=False):
    """Represents a message in the conversation."""

    role: str
    content: Any  # Can be string or list of content blocks
    ts: int
    isSummary: bool


@dataclass
class ServiceTier:
    context_window: int
    name: Optional[str] = None  # Service tier name (flex, priority, etc.)
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_writes_price: Optional[float] = None
    cache_reads_price: Optional[float] = None


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


class GroundingChunk(TypedDict, total=False):
    """Grounding content chunk"""

    type: Required[str] = "grounding"
    sources: List[dict]


StreamChunk = UsageChunk | TextChunk | ReasoningChunk | GroundingChunk
