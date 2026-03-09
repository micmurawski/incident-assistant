import asyncio
import hashlib
import json
import os
from typing import Any, Optional

import ollama
from anthropic.types.message_param import MessageParam

from agent.providers.base import (ApiHandler, ApiHandlerCreateMessageMetadata,
                                  AsyncIterator)
from agent.providers.fetcher import fetch_ollama_model
from agent.providers.formatters.open_ai_format import \
    convert_to_openai_messages
from agent.providers.formatters.r1_format import convert_to_r1_format
from agent.providers.formatters.xml_matcher import XmlMatcher
from agent.providers.settings import ModelInfo
from agent.providers.utils.error_handling import handle_open_ai_error
from agent.providers.utils.tiktoken import count_tokens
from agent.types import (ReasoningChunk, StreamChunk, TextChunk, ToolUse,
                         UsageChunk)


def __debug_ollama_stream__() -> bool:
    return os.environ.get("DEBUG_OLLAMA_STREAM", "").lower() in ("1", "true", "yes")


def _debug_print_raw_ollama(chunk: Any) -> None:
    """Print raw Ollama stream chunk for debugging (stderr to avoid breaking pipes)."""
    import sys
    text = getattr(getattr(chunk, "message", None), "content", None) or ""
    sys.stderr.write(f"\033[33m[raw ollama] content={repr(text)}\033[0m\n")


def _debug_print_parsed(ctype: str, text: str) -> None:
    """Print parsed chunk type and content for debugging."""
    import sys
    color = "\033[90m" if ctype == "reasoning" else "\033[0m"
    sys.stderr.write(f"{color}[parsed {ctype}] {repr(text)}\033[0m\n")


def _content_to_string(content: Any) -> str:
    """Normalize message content to string for Ollama API (expects content: str)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for pt in content:
            if isinstance(pt, str):
                parts.append(pt)
            elif isinstance(pt, dict):
                if pt.get("type") == "text":
                    t = pt.get("text")
                    parts.append("" if t is None else str(t))
                elif pt.get("type") == "tool_result":
                    c = pt.get("content")
                    parts.append("" if c is None else str(c))
            else:
                parts.append(str(pt))
        return "\n".join(parts)
    return str(content)


class OllamaHandler(ApiHandler):
    provider: str = "ollama"
    """
    Handler for Ollama API with streaming support and prompt caching.
    """

    def __init__(self, model_id: str | None = None, api_key: str | None = None, base_url: str | None = None, **kwargs):
        self.model_id = model_id
        self.base_url = base_url or "http://localhost:11434"
        self.model = fetch_ollama_model(model_id)
        self.options = kwargs
        
        # Initialize Ollama async client
        self.client = ollama.AsyncClient(host=self.base_url)

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
        debug_raw = kwargs.pop("debug_raw_stream", False) or __debug_ollama_stream__()
        config = self.get_model()
        model_id = config["id"]
        use_r1_format = "deepseek-r1" in model_id.lower()
        # Convert messages to Ollama format
        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})
        
        # Convert and add user/assistant messages
        if use_r1_format:
            converted_messages = convert_to_openai_messages(messages)
        else:
            converted_messages = convert_to_r1_format(messages)
        
        for msg in converted_messages:
            content = _content_to_string(msg.get("content", ""))
            ollama_messages.append({"role": msg.get("role", "user"), "content": content})
        try:
            # Ollama streaming API call
            stream = await self.client.chat(
                model=model_id,
                messages=ollama_messages,
                stream=True,
                options={
                    "temperature": self.options.get("temperature", 0.0),
                    **{k: v for k, v in kwargs.items() if k not in ["stream", "model", "messages"]}
                },
                tools=kwargs.get("tools"),
            )
        except Exception as e:
            raise handle_open_ai_error(e, "ollama") from e

        matcher = XmlMatcher(
            "think",
            transform=lambda chunk: dict(type="reasoning" if chunk["matched"] else "text", content=chunk["data"]),
        )

        last_usage = None
        content = []
        async for chunk in stream:
            if debug_raw:
                _debug_print_raw_ollama(chunk)
            # Ollama returns chunks with message content directly
            for tool_call in chunk.message.tool_calls or []:
                tool_use_id = hashlib.sha256(json.dumps(dict(name=tool_call.function.name, arguments=tool_call.function.arguments)).encode()).hexdigest()
                yield ToolUse(type="tool_use", id=tool_use_id, name=tool_call.function.name, input=tool_call.function.arguments)
            if hasattr(chunk, "message") and hasattr(chunk.message, "content"):
                chunk_content = chunk.message.content or ""
                content.append(chunk_content)
                
                if chunk_content:
                    for matcher_chunk in matcher.update(chunk_content):
                        out_type = matcher_chunk["type"]
                        out_text = matcher_chunk["content"]
                        if debug_raw:
                            _debug_print_parsed(out_type, out_text)
                        if out_type == "reasoning":
                            yield ReasoningChunk(type="reasoning", text=out_text)
                        else:
                            yield TextChunk(type="text", text=out_text)
            
            # Extract usage info if available
            if hasattr(chunk, "prompt_eval_count") or hasattr(chunk, "eval_count"):
                last_usage = {
                    "prompt_tokens": getattr(chunk, "prompt_eval_count", 0),
                    "completion_tokens": getattr(chunk, "eval_count", 0),
                }
        for chunk in matcher.final():
            out_type = chunk["type"]
            out_text = chunk["content"]
            if debug_raw:
                _debug_print_parsed(out_type, out_text)
            if out_type == "reasoning":
                yield ReasoningChunk(type="reasoning", text=out_text)
            else:
                yield TextChunk(type="text", text=out_text)
        if last_usage:
            yield UsageChunk(
                type="usage",
                input_tokens=last_usage.get("prompt_tokens", 0),
                output_tokens=last_usage.get("completion_tokens", 0),
            )

    async def complete_prompt(self, prompt: str) -> str:
        try:
            model_id = self.get_model().id
            use_r1_format = "deepseek-r1" in model_id.lower()
            try:
                messages = [{"role": "user", "content": prompt}]
                
                # Convert messages if needed
                if use_r1_format:
                    converted_messages = convert_to_r1_format(messages)
                else:
                    converted_messages = messages
                
                # Ollama API call
                response = await self.client.chat(
                    model=model_id,
                    messages=converted_messages,
                    stream=False,
                    options={"temperature": self.options.get("temperature", 0.0)}
                )
                return response.message.content or ""
            except Exception as e:
                raise handle_open_ai_error(e, "ollama") from e
        except Exception as e:
            raise handle_open_ai_error(e, "ollama") from e

    async def count_tokens(self, content: list[MessageParam], tools: list[dict] | None = None) -> int:
        # run count_tokens in async worker
        return await asyncio.to_thread(count_tokens, content, tools)



async def main():
    handler = OllamaHandler(model_id="deepseek-r1:7b")
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
