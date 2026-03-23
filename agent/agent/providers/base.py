from typing import Any, AsyncIterator, Coroutine, Dict, List, Optional

from agent.types import AnthropicMessage, ApiHandlerCreateMessageMetadata


class ApiHandler:
    """
    Base class for API handlers.
    This should be implemented based on your specific API integration.
    """

    @property
    def provider(self) -> str:
        """Returns the provider of the API handler."""
        raise NotImplementedError

    def create_message(
        self,
        system_prompt: str,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Creates a streaming message.
        Should yield chunks with 'type' field indicating 'text' or 'usage'.
        """
        raise NotImplementedError

    def get_model(self) -> dict:
        """Returns the model configuration for the API handler."""
        raise NotImplementedError

    async def count_tokens(self, messages: List[Dict[str, Any]], tools: List[dict] | None = None) -> Coroutine[Any, Any, int]:
        """Counts tokens in a list of chat messages."""
        raise NotImplementedError
