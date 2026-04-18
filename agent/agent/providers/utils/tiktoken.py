import json
import math
from typing import Any, List

import tiktoken
from anthropic.types.message_param import MessageParam as AnthropicMessageParam

TOKEN_FUDGE_FACTOR = 1.5

# Global cache for the encoder
_encoder = None


def get_tiktoken_encoder():
    """Lazily create and cache the encoder."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("o200k_base")
    return _encoder


def count_tokens(content: List[AnthropicMessageParam], tools: List[dict] | None = None) -> int:
    """
    Count tokens in Anthropic message content blocks.

    Args:
        content: List of content blocks (text, image, etc.)
        tools: List of tools to count tokens for
        If tools are provided, the total token count will be the sum of the tokens in the content and tools.
    Returns:
        Estimated token count with fudge factor applied
    """
    if not content:
        return 0

    total_tokens = 0
    encoder = get_tiktoken_encoder()

    if tools:
        # Tool definitions come in at least three incompatible shapes:
        #   - OpenAI/Groq/OpenRouter: {"type": "function", "function": {"name", "description", "parameters": {...}}}
        #   - Anthropic/MiniMax:      {"name", "description", "input_schema": {...}}
        #   - Ollama / raw:           {"name", "description", "parameters": {...}}
        # Rather than special-casing each, serialize the whole definition and count tokens
        # of the JSON representation -- close enough to what the provider actually wires.
        for tool in tools:
            try:
                serialized = json.dumps(tool, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                serialized = str(tool)
            total_tokens += len(encoder.encode(serialized))

    def _encode(text: str) -> int:
        if not text:
            return 0
        return len(encoder.encode(text))

    def _count_block(block: Any) -> int:
        # Messages can be full Anthropic TypedDicts, pydantic-like objects, or plain
        # dicts whose `content` is either a string or a list of sub-blocks.
        if isinstance(block, str):
            return _encode(block)
        if not isinstance(block, dict):
            # pydantic/attrs-style object: try attribute access, fall back to str().
            for attr in ("text", "content"):
                val = getattr(block, attr, None)
                if isinstance(val, str):
                    return _encode(val)
            return _encode(str(block))

        block_type = block.get("type")

        if block_type == "text":
            return _encode(block.get("text") or block.get("content") or "")

        if block_type == "tool_use":
            name = block.get("name") or ""
            try:
                input_str = json.dumps(block.get("input") or {}, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                input_str = str(block.get("input") or "")
            return _encode(name) + _encode(input_str)

        if block_type == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list):
                return sum(_count_block(b) for b in inner)
            if isinstance(inner, str):
                return _encode(inner)
            try:
                return _encode(json.dumps(inner, default=str, ensure_ascii=False))
            except (TypeError, ValueError):
                return _encode(str(inner or ""))

        if block_type == "image":
            source = block.get("source")
            if isinstance(source, dict) and "data" in source:
                return math.ceil(math.sqrt(len(source["data"])))
            return 300  # Conservative estimate for unknown images

        # Generic fallback: top-level message dict ({"role", "content": str | list})
        inner = block.get("content")
        if isinstance(inner, list):
            return sum(_count_block(b) for b in inner)
        if isinstance(inner, str):
            return _encode(inner)
        text = block.get("text")
        if isinstance(text, str):
            return _encode(text)
        return 0

    for block in content:
        total_tokens += _count_block(block)

    return math.ceil(total_tokens * TOKEN_FUDGE_FACTOR)
