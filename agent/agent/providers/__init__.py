from typing import Any

from agent.providers.base import ApiHandler
from agent.providers.settings import ApiProvider


def build_api_handler(*, provider: ApiProvider, **configuration: dict[str, Any]) -> ApiHandler:
    if provider == "anthropic":
        from agent.providers._anthropic import AnthropicHandler

        return AnthropicHandler(**configuration)
    elif provider == "gemini":
        from agent.providers.gemini import GeminiHandler

        return GeminiHandler(**configuration)
    elif provider == "ollama":
        from agent.providers.ollama import OllamaHandler

        return OllamaHandler(**configuration)
    elif provider == "minimax":
        from agent.providers.minimax import MiniMaxHandler
        
        return MiniMaxHandler(**configuration)
    elif provider == "groq":
        from agent.providers.groq import GroqHandler    
        return GroqHandler(**configuration)
    elif provider == "openai":
        from agent.providers.openai import OpenAIHandler
        return OpenAIHandler(**configuration)
    elif provider == "openai_responses":
        from agent.providers.openai_responses import OpenAIResponsesHandler

        return OpenAIResponsesHandler(**configuration)
    elif provider == "openrouter":
        from agent.providers.openrouter import OpenRouterHandler
        return OpenRouterHandler(**configuration)
    elif provider == "ovh":
        from agent.providers.ovh import OvhHandler
        return OvhHandler(**configuration)
    else:
        raise ValueError(f"Unknown provider: {provider}")
