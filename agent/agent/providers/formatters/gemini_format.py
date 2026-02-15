from typing import Any, Dict, List

from google.genai import types

from agent.providers.base import AnthropicMessage


def _get_block_field(block: Any, key: str, default: Any = None) -> Any:
    """Get a field from a block that may be a dict, TypedDict, or Pydantic object."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _materialize_content(content: Any) -> list:
    """
    Materialize content to a plain list.

    Anthropic's MessageParam has content typed as Union[str, Iterable[ContentBlockParam]].
    When messages pass through Pydantic validation (e.g. via the @node decorator),
    list content gets wrapped in SerializationIterator/ValidatorIterator — one-shot
    iterators that are consumed on first iteration. This function materializes any
    iterable into a stable list so it can be iterated multiple times.
    """
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return []  # strings are handled separately by the caller
    try:
        return list(content)
    except (TypeError, ValueError):
        return []


def _materialize_messages(messages: List[AnthropicMessage]) -> List[dict]:
    """
    Pre-process all messages, materializing one-shot iterators in content fields.

    This MUST be called once before any other processing to avoid consuming
    SerializationIterator/ValidatorIterator objects more than once.
    Returns plain dicts with stable list content.
    """
    result = []
    for message in messages:
        if isinstance(message, dict):
            msg = dict(message)  # shallow copy
        else:
            msg = {
                "role": getattr(message, "role", "user"),
                "content": getattr(message, "content", ""),
            }
        content = msg.get("content")
        if content is not None and not isinstance(content, str):
            msg["content"] = _materialize_content(content)
        result.append(msg)
    return result


def _build_tool_use_map(messages: List[dict]) -> Dict[str, str]:
    """Build a mapping from tool_use_id to function name across all messages.

    Expects messages that have already been materialized by _materialize_messages.
    """
    mapping: Dict[str, str] = {}
    for message in messages:
        content = message.get("content")
        if content is None or isinstance(content, str):
            continue
        for block in content:
            block_type = _get_block_field(block, "type")
            if block_type == "tool_use":
                block_id = _get_block_field(block, "id")
                block_name = _get_block_field(block, "name")
                if block_id and block_name:
                    mapping[block_id] = block_name
    return mapping


def _convert_anthropic_message(
    message: dict,
    tool_use_map: Dict[str, str],
) -> types.Content:
    """Convert a materialized Anthropic message dict to Gemini format."""
    role = message.get("role", "user")
    content = message.get("content", "")
    # Map roles
    gemini_role = "model" if role == "assistant" else "user"
    # Convert content
    parts = []
    if isinstance(content, str):
        if content:
            parts.append(types.Part(text=content))
    else:
        # content is already a materialized list (from _materialize_messages)
        for block in content:
            block_type = _get_block_field(block, "type")
            if block_type == "text":
                text = _get_block_field(block, "text", "")
                if text:
                    parts.append(types.Part(text=text))
            elif block_type == "tool_use":
                # Convert to Gemini FunctionCall
                parts.append(types.Part(
                    function_call=types.FunctionCall(
                        name=_get_block_field(block, "name"),
                        args=_get_block_field(block, "input", {}),
                    )
                ))
            elif block_type == "tool_result":
                # Convert to Gemini FunctionResponse
                tool_use_id = _get_block_field(block, "tool_use_id", "")
                func_name = tool_use_map.get(tool_use_id, "unknown")
                response_content = _get_block_field(block, "content", "")
                if isinstance(response_content, str):
                    response_dict = {"result": response_content}
                elif isinstance(response_content, dict):
                    response_dict = response_content
                else:
                    response_dict = {"result": str(response_content)}
                parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=func_name,
                        response=response_dict,
                    )
                ))
            elif block_type == "image":
                # Handle image content if needed
                pass
    # Gemini requires at least one part per Content; add empty text if needed
    if not parts:
        parts.append(types.Part(text=""))
    return types.Content(role=gemini_role, parts=parts)


def convert_to_gemini_messages(anthropic_messages: List[AnthropicMessage]) -> List[types.Content]:
    """Convert Anthropic message format to Gemini format.

    Materializes all message content up-front so that one-shot iterators
    (SerializationIterator from Pydantic round-trips) are consumed exactly once.
    """
    # Step 1: Materialize all content ONCE — this is critical for one-shot iterators
    materialized = _materialize_messages(anthropic_messages)
    # Step 2: Build tool_use_id -> name mapping from the materialized data
    tool_use_map = _build_tool_use_map(materialized)
    # Step 3: Convert each message using the already-materialized content
    return [
        _convert_anthropic_message(message, tool_use_map)
        for message in materialized
    ]
