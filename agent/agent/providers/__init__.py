from typing import Any

from agent.providers.base import ApiHandler
from agent.providers.settings import ApiProvider


def build_api_handler(*, provider: ApiProvider, **configuration: dict[str, Any]) -> ApiHandler:
    # raise Exception(provider, configuration)
    if provider == "anthropic":
        from agent.providers._anthropic import AnthropicHandler

        return AnthropicHandler(**configuration)
    elif provider == "gemini":
        from agent.providers.gemini import GeminiHandler

        return GeminiHandler(**configuration)
    elif provider == "ollama":
        from agent.providers.ollama import OllamaHandler

        return OllamaHandler(**configuration)
    else:
        raise ValueError(f"Unknown provider: {provider}")
