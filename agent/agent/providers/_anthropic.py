import json
from typing import Any, AsyncIterator, Dict, List, Optional

from anthropic import Anthropic, AsyncAnthropic
from anthropic.types.message_param import MessageParam as AnthropicMessageParam

from agent.providers.base import ApiHandler
from agent.providers.models import ANTHROPIC_DEFAULT_MODEL_ID, ANTHROPIC_MODELS
from agent.providers.params import get_model_params
from agent.providers.settings import AnthropicSettings, ModelInfo
from agent.providers.utils.cost import calculate_api_cost_anthropic
from agent.types import (ReasoningChunk, StreamChunk, TextChunk, ToolUse,
                         UsageChunk)


class AnthropicHandler(ApiHandler):
    provider: str = "anthropic"
    """
    Handler for Anthropic API with streaming support and prompt caching.

    Example:
        handler = AnthropicHandler(
            api_key="your-api-key",
            model_id="claude-sonnet-4-20250514",
            temperature=0.7
        )

        async for chunk in handler.create_message(system_prompt, messages):
            if chunk.type == "text":
                print(chunk.text, end="")
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        use_auth_token: bool = False,
        enable_1m_context: bool = False,
        enable_reasoning: bool = False,
        **kwargs,
    ):
        """
        Initialize the Anthropic handler.

        Args:
            api_key: Anthropic API key or auth token
            base_url: Optional custom base URL
            model_id: Model identifier (defaults to claude-sonnet-4-20250514)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            use_auth_token: Use auth token instead of API key
            enable_1m_context: Enable 1M context window for Sonnet 4
            enable_reasoning: Enable extended thinking for supported models
            **kwargs: Additional options
        """
        self.model_id = model_id or ANTHROPIC_DEFAULT_MODEL_ID
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_1m_context = enable_1m_context
        self.enable_reasoning = enable_reasoning
        self.kwargs = kwargs

        # Initialize client with appropriate authentication
        client_kwargs = {}
        if base_url:
            client_kwargs["base_url"] = base_url

        if base_url and use_auth_token:
            client_kwargs["auth_token"] = api_key
        else:
            client_kwargs["api_key"] = api_key

        self.client = AsyncAnthropic(**client_kwargs)
        self.sync_client = Anthropic(**client_kwargs)

    def _add_cache_control(
        self,
        messages: List[AnthropicMessageParam],
    ) -> List[AnthropicMessageParam]:
        """
        Add cache control to appropriate messages for prompt caching.

        Caches the last two user messages to enable reuse across requests.
        """
        # Find all user message indices
        user_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "user"]

        if len(user_indices) < 1:
            return messages

        last_user_idx = user_indices[-1]
        second_last_idx = user_indices[-2] if len(user_indices) >= 2 else -1

        cached_messages = []
        cache_control = {"type": "ephemeral"}

        for i, message in enumerate(messages):
            if i not in (last_user_idx, second_last_idx):
                cached_messages.append(message)
                continue

            # Add cache control to this message's content
            content = message.get("content")

            if isinstance(content, str):
                cached_messages.append(
                    {
                        **message,
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": cache_control,
                            }
                        ],
                    }
                )
            elif isinstance(content, list):
                # Add cache control to the last content block
                new_content = content[:-1] + [{**content[-1], "cache_control": cache_control}]
                cached_messages.append(
                    {
                        **message,
                        "content": new_content,
                    }
                )
            else:
                cached_messages.append(message)

        return cached_messages

    async def create_message(
        self,
        system_prompt: str,
        messages: List[AnthropicMessageParam],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Create a streaming message with the Anthropic API.

        Args:
            system_prompt: System prompt for the conversation
            messages: List of message dictionaries with 'role' and 'content'
            metadata: Optional metadata for the request

        Yields:
            StreamChunk objects containing usage, text, or reasoning data
        """
        config = self.get_model()
        model_id = config["id"]
        cache_control = {"type": "ephemeral"}

        # Prepare system prompt with cache control
        cache_control = {"type": "ephemeral"}
        system = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": cache_control,
            }
        ]

        # Prepare messages with cache control if supported

        messages = self._add_cache_control(messages)

        # Prepare request parameters
        request_params = {
            "model": model_id,
            "max_tokens": config["max_tokens"],
            "system": system,
            "messages": messages,
            "stream": True,
            "tools": kwargs.pop("tools", []),
            "thinking": config.pop("reasoning", None),
        }

        if config.get("temperature") is not None:
            request_params["temperature"] = config["temperature"]

        #if config.get("reasoning_budget") is not None:
        #    request_params["thinking"] = {"type": "enabled", "budget_tokens": config["reasoning_budget"]}
        
        # Add beta headers if needed
        extra_headers = {}
        # Create streaming response
        stream = await self.client.messages.create(
            **request_params,
            extra_headers=extra_headers if extra_headers else None,
            **kwargs,
        )

        # Track token usage
        input_tokens = 0
        output_tokens = 0
        cache_write_tokens = 0
        cache_read_tokens = 0

        # Track in-progress tool use blocks
        current_tool_use_id: Optional[str] = None
        current_tool_use_name: Optional[str] = None
        current_tool_use_json: str = ""

        # Process stream chunks
        async for chunk in stream:
            if chunk.type == "message_start":
                # Extract usage information
                usage = chunk.message.usage

                input_tokens += usage.input_tokens
                output_tokens += usage.output_tokens
                cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0)
                cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0)

                yield UsageChunk(
                    type="usage",
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
                )

            elif chunk.type == "message_delta":
                # Output token updates
                if chunk.usage.output_tokens:
                    yield UsageChunk(
                        type="usage",
                        input_tokens=0,
                        output_tokens=chunk.usage.output_tokens,
                    )

            elif chunk.type == "content_block_start":
                block = chunk.content_block

                if block.type == "tool_use":
                    # Start accumulating a tool use block
                    current_tool_use_id = block.id
                    current_tool_use_name = block.name
                    current_tool_use_json = ""
                else:
                    # Add line break between multiple blocks
                    if chunk.index > 0:
                        if block.type == "thinking":
                            yield ReasoningChunk(type="reasoning", text="\n")
                        elif block.type == "text":
                            yield TextChunk(type="text", text="\n")

                    # Yield initial content
                    if block.type == "thinking":
                        yield ReasoningChunk(type="reasoning", text=block.thinking)
                    elif block.type == "text":
                        yield TextChunk(type="text", text=block.text)

            elif chunk.type == "content_block_delta":
                delta = chunk.delta

                if delta.type == "thinking_delta":
                    yield ReasoningChunk(type="reasoning", text=delta.thinking)
                elif delta.type == "text_delta":
                    yield TextChunk(type="text", text=delta.text)
                elif delta.type == "input_json_delta":
                    # Accumulate partial JSON for tool use input
                    current_tool_use_json += delta.partial_json

            elif chunk.type == "content_block_stop":
                # If we were accumulating a tool use block, emit it now
                if current_tool_use_id is not None:
                    try:
                        tool_input = json.loads(current_tool_use_json) if current_tool_use_json else {}
                    except json.JSONDecodeError:
                        tool_input = {}

                    yield ToolUse(
                        type="tool_use",
                        id=current_tool_use_id,
                        name=current_tool_use_name,
                        input=tool_input,
                    )

                    # Reset tool use tracking
                    current_tool_use_id = None
                    current_tool_use_name = None
                    current_tool_use_json = ""

        # Calculate and yield final cost if tokens were used
        if any([input_tokens, output_tokens, cache_write_tokens, cache_read_tokens]):
            total_cost = calculate_api_cost_anthropic(
                config,
                input_tokens,
                output_tokens,
                cache_write_tokens,
                cache_read_tokens,
            )

            yield UsageChunk(
                type="usage",
                input_tokens=0,
                output_tokens=0,
                total_cost=total_cost,
            )

    async def complete_prompt(self, prompt: str) -> str:
        """
        Complete a simple prompt without streaming.

        Args:
            prompt: The prompt to complete

        Returns:
            The generated text response
        """
        config = self.get_model()

        response = await self.client.messages.create(
            model=config["id"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content
        for block in response.content:
            if block.type == "text":
                return block.text

        return ""

    async def count_tokens(self, content: List[AnthropicMessageParam]) -> int:
        """
        Count tokens for the given content using Anthropic's API.

        Args:
            content: List of content blocks to count tokens for

        Returns:
            The number of input tokens
        """
        try:
            config = self.get_model()

            response = await self.client.messages.count_tokens(
                model=config["id"],
                messages=[{"role": "user", "content": content}],
            )

            return response.input_tokens

        except Exception as e:
            print(f"Anthropic token counting failed: {e}")
            # Fallback to rough estimation (4 chars ≈ 1 token)
            text = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
            )
            return len(text) // 4

    def get_model(self) -> ModelInfo:
        is_thinking = self.model_id.endswith(":thinking")
        _model_id = self.model_id.replace(":thinking", "") if is_thinking else self.model_id
        model_id = _model_id if _model_id in ANTHROPIC_MODELS else ANTHROPIC_DEFAULT_MODEL_ID
        info = ANTHROPIC_MODELS[model_id]
        params: AnthropicSettings = get_model_params(
            format="anthropic", model_id=model_id, model=info, settings=self.kwargs
        )
        if is_thinking and info.get("supports_reasoning_budget"):
            params["reasoning"] = {"type": "enabled", "budget_tokens": self.kwargs.pop("reasoning_budget", 1024)}
        data = {
            "id": model_id.replace(":thinking", "") if model_id.endswith(":thinking") else model_id,
            **info,
            **params,
        }
        return ModelInfo(**data)


async def main():
    import os

    handler = AnthropicHandler(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model_id="claude-sonnet-4-20250514",
    )
    response = handler.create_message(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "How many letters 'r' is in the strawberry?"}],
    )
    async for chunk in response:
        print(chunk)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
