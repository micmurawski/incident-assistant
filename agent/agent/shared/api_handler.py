from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict, Coroutine, Literal

ApiProvider = Literal["anthropic", "openai", "google", "ollama"]


class ApiHandler:
    """
    Base class for API handlers.
    This should be implemented based on your specific API integration.
    """

    def create_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
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


def build_api_handler(api_provider: ApiProvider, **configuration: Dict[str, Any]) -> ApiHandler:
    api_provider: ApiProvider = configuration.get("api_provider")

    if api_provider == "anthropic":
        return AnthropicApiHandler(configuration)
    elif api_provider == "openai":
        return OpenAiApiHandler(configuration)
    elif api_provider == "google":
        return GoogleApiHandler(configuration)
    elif api_provider == "ollama":
        return OllamaApiHandler(configuration)
