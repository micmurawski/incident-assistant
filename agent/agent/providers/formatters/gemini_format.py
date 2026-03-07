import base64
from typing import Any, Dict, List, Optional

from google.genai import types

from agent.providers.base import AnthropicMessage


def _get_block_field(block: Any, key: str, default: Any = None) -> Any:
    """Get a field from a block that may be a dict, TypedDict, or Pydantic object."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _block_to_dict(block: Any) -> Any:
    """Convert a Pydantic model or iterator item to a plain dict."""
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return block


def _materialize_content(content: Any) -> list:
    """
    Materialize content to a plain list of dicts.

    Anthropic's MessageParam has content typed as Union[str, Iterable[ContentBlockParam]].
    When messages pass through Pydantic validation (e.g. via the @node decorator),
    list content gets wrapped in SerializationIterator/ValidatorIterator — one-shot
    iterators that are consumed on first iteration. Items may also be Pydantic model
    objects rather than plain dicts. This function materializes everything into a
    stable list of plain dicts.
    """
    if isinstance(content, str):
        return []
    if isinstance(content, list):
        return [_block_to_dict(b) for b in content]
    try:
        return [_block_to_dict(b) for b in content]
    except (TypeError, ValueError):
        return []


def _materialize_messages(messages: List[AnthropicMessage]) -> List[dict]:
    """
    Pre-process all messages, materializing one-shot iterators in content fields.

    This MUST be called once before any other processing to avoid consuming
    SerializationIterator/ValidatorIterator objects more than once.
    Returns plain dicts with stable list content.
    Drops messages whose content is metadata (e.g. usage dicts) rather than
    valid conversation content.
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
        if content is None or isinstance(content, str):
            result.append(msg)
            continue
        if isinstance(content, dict) and content.get("type") == "usage":
            continue
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


def _decode_thought_signature(thought_sig: Any) -> Optional[bytes]:
    """Decode thought_signature from block (bytes or base64 str) to bytes."""
    if thought_sig is None:
        return None
    return thought_sig if isinstance(thought_sig, bytes) else base64.b64decode(thought_sig)


def _convert_anthropic_message(
    message: dict,
    tool_use_map: Dict[str, str],
    last_thought_signature: Optional[Any] = None,
    include_thought_signatures: bool = False,
) -> types.Content:
    """Convert a materialized Anthropic message dict to Gemini format."""
    role = message.get("role", "user")
    content = message.get("content", "")
    # Map roles
    gemini_role = "model" if role == "assistant" else "user"
    # Convert content
    parts = []
    injected_sig: Optional[bytes] = None
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
                # Convert to Gemini FunctionCall; include thought_signature (required for Gemini 3+ tools)
                part_kw: dict = {
                    "function_call": types.FunctionCall(
                        name=_get_block_field(block, "name"),
                        args=_get_block_field(block, "input", {}),
                    )
                }
                thought_sig = _decode_thought_signature(_get_block_field(block, "thought_signature", None))
                if thought_sig is not None:
                    injected_sig = thought_sig
                    part_kw["thought_signature"] = thought_sig
                elif include_thought_signatures and last_thought_signature is not None:
                    # Inject handler-stored signature when block has none (Roo-Code pattern)
                    sig_bytes = _decode_thought_signature(last_thought_signature)
                    if sig_bytes is not None:
                        injected_sig = injected_sig or sig_bytes
                        part_kw["thought_signature"] = sig_bytes
                elif injected_sig is not None:
                    # Reuse first part's signature for parallel function calls
                    part_kw["thought_signature"] = injected_sig
                parts.append(types.Part(**part_kw))
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


def convert_to_gemini_messages(
    anthropic_messages: List[AnthropicMessage],
    last_thought_signature: Optional[Any] = None,
    include_thought_signatures: bool = False,
) -> List[types.Content]:
    """Convert Anthropic message format to Gemini format.

    Materializes all message content up-front so that one-shot iterators
    (SerializationIterator from Pydantic round-trips) are consumed exactly once.
    When include_thought_signatures is True, injects last_thought_signature into
    assistant tool_use parts that lack it (required for Gemini 3+ tool round-trip).
    """
    # Step 1: Materialize all content ONCE — this is critical for one-shot iterators
    materialized = _materialize_messages(anthropic_messages)
    # Step 2: Build tool_use_id -> name mapping from the materialized data
    tool_use_map = _build_tool_use_map(materialized)
    # Step 3: Convert each message using the already-materialized content
    return [
        _convert_anthropic_message(
            message,
            tool_use_map,
            last_thought_signature=last_thought_signature,
            include_thought_signatures=include_thought_signatures,
        )
        for message in materialized
    ]
