from openai import OpenAIError


def handle_open_ai_error(error: OpenAIError, provider_name: str) -> Exception:
    return Exception(f"{provider_name}: {error}")
