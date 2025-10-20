from typing import Any, AsyncIterator, Coroutine, Dict, List, Optional

from agent.types import AnthropicMessage, ApiHandlerCreateMessageMetadata


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
