from typing import List

from google.genai import types

from agent.providers.base import AnthropicMessage


def _convert_anthropic_message(message: AnthropicMessage) -> types.Content:
    """Convert Anthropic message format to Gemini format."""
    role = message["role"]
    content = message["content"]
    # Map roles
    gemini_role = "model" if role == "assistant" else "user"
    # Convert content
    parts = []
    if isinstance(content, str):
        parts.append(types.Part(text=content))
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(types.Part(text=block.get("text", "")))
                elif block.get("type") == "image":
                    # Handle image content if needed
                    pass
    return types.Content(role=gemini_role, parts=parts)


def convert_to_gemini_messages(anthropic_messages: List[AnthropicMessage]) -> List[types.Content]:
    """Convert Anthropic message format to Gemini format."""
    return [_convert_anthropic_message(message) for message in anthropic_messages]
