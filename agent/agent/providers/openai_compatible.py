import asyncio
import hashlib
import json
from typing import Any, Coroutine, Optional

from anthropic.types.message_param import MessageParam
from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message_param import \
    ChatCompletionMessageParam

from agent.providers.base import (ApiHandler, ApiHandlerCreateMessageMetadata,
                                  AsyncIterator)
from agent.providers.formatters.open_ai_format import \
    convert_to_openai_messages
from agent.providers.formatters.r1_format import convert_to_r1_format
from agent.providers.formatters.xml_matcher import XmlMatcher
from agent.providers.models import OPENAI_MODELS
from agent.providers.settings import ModelInfo
from agent.providers.utils.cost import calculate_api_cost_openai
from agent.providers.utils.error_handling import handle_open_ai_error
from agent.providers.utils.tiktoken import count_tokens
from agent.types import (ReasoningChunk, StreamChunk, TextChunk, ToolUse,
                         UsageChunk)


class OpenAICompatibleHandler(ApiHandler):
    provider: str = "openai"
    """
    Handler for Ollama API with streaming support and prompt caching.
    """

    def __init__(self, model_id: str | None = None, api_key: str | None = None, base_url: str | None = None, **kwargs):
        self.model_id = model_id
        self.base_url = base_url or "http://localhost:11434/v1"
        self.model = OPENAI_MODELS[model_id] #fetch_ollama_model(model_id)
        self.options = kwargs

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = AsyncOpenAI(api_key=api_key or "ollama", base_url=self.base_url, default_headers=headers)

    def get_model(self) -> ModelInfo:
        return self.model

    async def create_message(
        self,
        system_prompt: str,
        messages: list[MessageParam],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Create a streaming message with the Ollama API.
        """
        config = self.get_model()
        model_id = config["id"]
        use_r1_format = "deepseek-r1" in model_id.lower()
        # NOTE: R1 format flattens tool_use / tool_result blocks (only text/image survive),
        # which makes tool-calling models loop on the same call because the provider never
        # sees the call-and-result history. Use the tool-aware OpenAI formatter unless the
        # model actually needs the R1 shape.
        openai_messages: list[ChatCompletionMessageParam] = [
            dict(role="system", content=system_prompt),
            *(convert_to_r1_format(messages) if use_r1_format else convert_to_openai_messages(messages)),
        ]

        # Reasoning effort: resolved by get_model_params based on the model's
        # `supports_reasoning_effort` / default `reasoning_effort` flags. Forward it as a
        # top-level `reasoning_effort` field so OpenAI / OVH / Groq / OpenRouter can surface
        # chain-of-thought via `delta.reasoning`.
        reasoning_effort = kwargs.pop("reasoning_effort", config.get("reasoning_effort"))
        if reasoning_effort is None:
            reasoning_effort = config.get("reasoning_effort")
            if reasoning_effort is None:
                reasoning_cfg = config.get("reasoning") or {}
                if isinstance(reasoning_cfg, dict):
                    reasoning_effort = reasoning_cfg.get("reasoning_effort")
        if reasoning_effort in (None, "minimal"):
            reasoning_effort = None

        extra_create_kwargs: dict[str, Any] = {}
        if reasoning_effort:
            extra_create_kwargs["reasoning_effort"] = reasoning_effort

        try:
            stream = await self.client.chat.completions.create(
                model=model_id,
                messages=openai_messages,
                stream=True,
                temperature=self.options.get("temperature", 0.0),
                stream_options={"include_usage": True},
                **extra_create_kwargs,
                **kwargs,
            )
        except Exception as e:
            raise handle_open_ai_error(e, "openai") from e

        matcher = XmlMatcher(
            "think",
            transform=lambda chunk: dict(type="reasoning" if chunk["matched"] else "text", content=chunk["data"]),
        )

        last_usage: Any = None
        # Accumulate streaming tool-call deltas keyed by their `index`. OpenAI-compatible
        # providers (incl. Groq) split a single tool call across many chunks: the first
        # delta carries `id`/`name` and subsequent deltas append `arguments` fragments.
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        async for chunk in stream:
            # The final chunk from OpenAI-compatible providers (with
            # `stream_options={"include_usage": True}`) has no `choices` but carries `usage`.
            if getattr(chunk, "usage", None):
                last_usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tool_calls = delta.tool_calls
            if tool_calls:
                for tc in tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    buf = tool_call_buffers.setdefault(
                        idx, {"id": None, "name": None, "arguments": ""}
                    )
                    if tc.id:
                        buf["id"] = tc.id
                    if tc.function is not None:
                        if tc.function.name:
                            buf["name"] = tc.function.name
                        if tc.function.arguments:
                            buf["arguments"] += tc.function.arguments
            # OpenAI-compatible reasoning models (gpt-oss via OVH/Groq/OpenRouter, DeepSeek, etc.)
            # stream chain-of-thought separately from the final answer. Different providers
            # expose it under different delta fields; handle the common ones.
            reasoning_piece = getattr(delta, "reasoning", None) or getattr(
                delta, "reasoning_content", None
            )
            if reasoning_piece:
                yield ReasoningChunk(type="reasoning", text=str(reasoning_piece))
            if delta.content:
                for matcher_chunk in matcher.update(delta.content):
                    if matcher_chunk["type"] == "reasoning":
                        yield ReasoningChunk(type="reasoning", text=matcher_chunk["content"])
                    else:
                        yield TextChunk(type="text", text=matcher_chunk["content"])
        for matcher_chunk in matcher.final():
            if matcher_chunk["type"] == "reasoning":
                yield ReasoningChunk(type="reasoning", text=matcher_chunk["content"])
            else:
                yield TextChunk(type="text", text=matcher_chunk["content"])

        for idx in sorted(tool_call_buffers.keys()):
            buf = tool_call_buffers[idx]
            name = buf["name"]
            if not name:
                continue
            args_str = buf["arguments"] or "{}"
            try:
                parsed_args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                # Fall back to raw string so downstream can surface the parse issue instead
                # of silently swallowing a malformed tool call.
                parsed_args = {"_raw_arguments": args_str}
            tool_use_id = buf["id"] or hashlib.sha256(
                json.dumps({"name": name, "arguments": args_str}, sort_keys=True).encode()
            ).hexdigest()
            yield ToolUse(
                type="tool_use",
                id=tool_use_id,
                name=name,
                input=parsed_args if isinstance(parsed_args, dict) else {"value": parsed_args},
            )

        if last_usage is not None:
            prompt_tokens = getattr(last_usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(last_usage, "completion_tokens", 0) or 0
            # OpenAI-compatible providers expose cached-prompt and reasoning token
            # counts under nested *_details objects (see OpenAI chat-completions spec).
            # Not every backend returns them, so treat absence as zero.
            prompt_details = getattr(last_usage, "prompt_tokens_details", None)
            completion_details = getattr(last_usage, "completion_tokens_details", None)
            cache_read_tokens = 0
            reasoning_tokens = 0
            if prompt_details is not None:
                cache_read_tokens = (
                    getattr(prompt_details, "cached_tokens", None)
                    or (prompt_details.get("cached_tokens", 0) if isinstance(prompt_details, dict) else 0)
                    or 0
                )
            if completion_details is not None:
                reasoning_tokens = (
                    getattr(completion_details, "reasoning_tokens", None)
                    or (completion_details.get("reasoning_tokens", 0) if isinstance(completion_details, dict) else 0)
                    or 0
                )

            total_cost = calculate_api_cost_openai(
                config,
                prompt_tokens,
                completion_tokens,
                0,
                cache_read_tokens,
            )

            usage_chunk: UsageChunk = {
                "type": "usage",
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "cache_read_tokens": cache_read_tokens,
                "total_cost": total_cost,
            }
            if reasoning_tokens:
                usage_chunk["reasoning_tokens"] = reasoning_tokens
            yield usage_chunk

    async def complete_prompt(self, prompt: str) -> Coroutine[Any, Any, str]:
        try:
            model_id = self.get_model().id
            use_r1_format = "deepseek-r1" in model_id.lower()
            try:
                messages = [{"role": "user", "content": prompt}]
                response: ChatCompletion = await self.client.chat.completions.create(
                    model=model_id,
                    messages=convert_to_r1_format(messages) if use_r1_format else messages,
                    temperature=self.options.get("temperature", 0.0),
                    stream=False,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                raise handle_open_ai_error(e, "openai") from e
        except Exception as e:
            raise handle_open_ai_error(e, "openai") from e

    async def count_tokens(self, content: list[MessageParam], tools: list[dict] | None = None) -> int:
        # run count_tokens in async worker
        return await asyncio.to_thread(count_tokens, content, tools)


async def main():
    handler = OpenAICompatibleHandler(model_id="deepseek-r1:7b")
    response_str = await handler.complete_prompt("How many letters 'r' is in the strawberry?")
    print(response_str)
    msgs = [{"role": "user", "content": response_str}]
    response = await handler.count_tokens(msgs)
    print(response)

    # response = handler.create_message(
    #    system_prompt="You are a helpful assistant.",
    #    messages=[{"role": "user", "content": "How many letters 'r' is in the strawberry?"}],
    # )
    # chunk: TextChunk | ReasoningChunk | UsageChunk
    # async for chunk in response:
    #    print(chunk)


#
# response = await handler.count_tokens([{"role": "user", "content": "How many letters 'r' is in the strawberry?"}])
# print(response)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
