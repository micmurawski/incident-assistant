import math
from typing import List

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
        for tool in tools:
            for parameter in tool["parameters"]:
                total_tokens += len(encoder.encode(parameter))
            for property in tool["properties"]:
                total_tokens += len(encoder.encode(property))
            for example in tool["examples"]:
                total_tokens += len(encoder.encode(example))
            for required in tool["required"]:
                total_tokens += len(encoder.encode(required))

    # Process each content block
    for block in content:
        # Handle both object and dict formats
        block_type = block.type if hasattr(block, "type") else block.get("type")

        if block_type == "text" or isinstance(block["content"], str):
            # Extract text content
            text = block.text if hasattr(block, "text") else block.get("text") or block.get("content", "")

            if text:
                tokens = encoder.encode(text)
                total_tokens += len(tokens)

        elif block_type == "image":
            # Extract image source
            source = block.source if hasattr(block, "source") else block.get("source")

            if source and isinstance(source, dict) and "data" in source:
                base64_data = source["data"]
                total_tokens += math.ceil(math.sqrt(len(base64_data)))
            else:
                total_tokens += 300  # Conservative estimate for unknown images

    return math.ceil(total_tokens * TOKEN_FUDGE_FACTOR)
