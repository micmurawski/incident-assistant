from typing import Any, Coroutine, Optional

from anthropic.types.message_param import MessageParam
from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from agent.providers.base import ApiHandler, ApiHandlerCreateMessageMetadata, AsyncIterator
from agent.providers.fetcher import fetch_ollama_model
from agent.providers.formatters.open_ai_format import convert_to_openai_messages
from agent.providers.formatters.r1_format import convert_to_r1_format
from agent.providers.formatters.xml_matcher import XmlMatcher
from agent.providers.settings import ModelInfo
from agent.providers.utils.error_handling import handle_open_ai_error
from agent.providers.utils.tiktoken import count_tokens
from agent.types import ReasoningChunk, StreamChunk, TextChunk, UsageChunk


class OllamaHandler(ApiHandler):
    """
    Handler for Ollama API with streaming support and prompt caching.
    """

    def __init__(self, model_id: str | None = None, api_key: str | None = None, base_url: str | None = None, **kwargs):
        self.model_id = model_id
        self.base_url = base_url or "http://localhost:11434/v1"
        self.model = fetch_ollama_model(model_id)
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
    ) -> AsyncIterator[StreamChunk]:
        """
        Create a streaming message with the Ollama API.
        """
        config = self.get_model()
        model_id = config.id
        use_r1_format = "deepseek-r1" in model_id.lower()
        openai_messages: list[ChatCompletionMessageParam] = [
            dict(role="system", content=system_prompt),
            *(convert_to_openai_messages(messages) if use_r1_format else convert_to_r1_format(messages)),
        ]
        try:
            stream = await self.client.chat.completions.create(
                model=model_id,
                messages=openai_messages,
                stream=True,
                temperature=self.options.get("temperature", 0.0),
                stream_options={"include_usage": True},
            )
        except Exception as e:
            raise handle_open_ai_error(e, "ollama") from e

        matcher = XmlMatcher(
            "think",
            transform=lambda chunk: dict(type="reasoning" if chunk["matched"] else "text", content=chunk["data"]),
        )

        last_usage: ChatCompletionChunk.usage = None
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                for matcher_chunk in matcher.update(delta.content):
                    yield ReasoningChunk(type="reasoning", text=matcher_chunk["content"])
            if "usage" in delta:
                last_usage = delta.usage
        for chunk in matcher.final():
            yield TextChunk(type="text", text=chunk["content"])
        if last_usage:
            yield UsageChunk(
                type="usage",
                input_tokens=last_usage.get("prompt_tokens", 0),
                output_tokens=last_usage.get("completion_tokens", 0),
            )

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
                raise handle_open_ai_error(e, "ollama") from e
        except Exception as e:
            raise handle_open_ai_error(e, "ollama") from e

    async def count_tokens(self, content: list[MessageParam]) -> int:
        # run count_tokens in async worker
        return await asyncio.to_thread(count_tokens, content)


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
