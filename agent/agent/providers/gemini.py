from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from google import genai
from google.genai import types

from agent.providers.base import AnthropicMessage, ApiHandler
from agent.providers.formatters.gemini_format import convert_to_gemini_messages
from agent.providers.models import GEMINI_DEFAULT_MODEL_ID, GEMINI_MODELS
from agent.providers.params import get_model_params
from agent.providers.settings import ModelInfo
from agent.types import (GroundingChunk, ReasoningChunk, StreamChunk,
                         TextChunk, ToolUse, UsageChunk)


class GeminiHandler(ApiHandler):
    provider: str = "gemini"
    """
    Handler for Google Gemini API with streaming support and advanced features.

    Supports both standard Gemini API and Vertex AI, with optional features
    like grounding (Google Search), URL context, and extended thinking.

    Example:
        # Standard API
        handler = GeminiHandler(
            api_key="your-api-key",
            model_id="gemini-2.0-flash-exp",
            enable_grounding=True
        )

        # Vertex AI with JSON credentials
        handler = GeminiHandler(
            use_vertex=True,
            vertex_project_id="my-project",
            vertex_region="us-central1",
            vertex_json_credentials='{"type": "service_account", ...}',
            model_id="gemini-1.5-pro"
        )

        async for chunk in handler.create_message(system_prompt, messages):
            if chunk.type == "text":
                print(chunk.text, end="")
    """

    def __init__(
        self,
        api_key: str,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        base_url: Optional[str] = None,
        enable_grounding: bool = False,
        enable_url_context: bool = False,
        enable_reasoning: bool = False,
        **kwargs,
    ):
        """
        Initialize the Gemini handler.

        Args:
            api_key: Gemini API key (for standard API)
            model_id: Model identifier
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            base_url: Optional custom base URL
            enable_grounding: Enable Google Search grounding
            enable_url_context: Enable URL context extraction
            enable_reasoning: Enable extended thinking
            **kwargs: Additional options
        """
        self.model_id = model_id or GEMINI_DEFAULT_MODEL_ID
        self.max_tokens = max_tokens
        self.temperature = temperature if temperature is not None else 0.0
        self.base_url = base_url
        self.enable_grounding = enable_grounding
        self.enable_url_context = enable_url_context
        self.enable_reasoning = enable_reasoning
        self.kwargs = kwargs

        if not api_key:
            raise ValueError("api_key is required for standard Gemini API")

        client_kwargs = {"api_key": api_key}

        if base_url:
            client_kwargs["http_options"] = {"api_endpoint": base_url}

        self.client = genai.Client(**client_kwargs, **kwargs)

    async def create_message(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Create a streaming message with the Gemini API.

        Args:
            system_instruction: System instruction for the conversation
            messages: List of message dictionaries with 'role' and 'content'
            metadata: Optional metadata for the request

        Yields:
            StreamChunk objects containing usage, text, reasoning, or grounding data
        """
        config = self.get_model()
        model_id = config["id"]
        # Convert messages to Gemini format
        contents = convert_to_gemini_messages(messages)
        #print("converted contents")
        #print(contents)

        # Prepare tools list
        tools_list = []
        function_declarations = kwargs.pop("tools", [])
        if function_declarations:
            tools_list.append(types.Tool(function_declarations=function_declarations))
        if self.enable_url_context:
            tools_list.append(types.Tool(url_context={}))
        if self.enable_grounding:
            tools_list.append(types.Tool(google_search={}))
        # Prepare generation config
        generation_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config["temperature"],
            max_output_tokens=config["max_tokens"],
            thinking_config=types.ThinkingConfig(**config["reasoning"]) if config["reasoning"] else None,
            tools=tools_list if tools_list else None,
        )

        try:
            # Generate content stream
            response = await self.client.aio.models.generate_content_stream(
                model=model_id,
                contents=contents,
                config=generation_config,
            )

            last_usage_metadata = None
            pending_grounding_metadata = None

            async for chunk in response:
                # Process candidates and their parts
                if chunk.candidates and len(chunk.candidates) > 0:
                    candidate = chunk.candidates[0]

                    # Store grounding metadata if present
                    if hasattr(candidate, "grounding_metadata"):
                        pending_grounding_metadata = candidate.grounding_metadata

                    # Process content parts
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            # Check if this is a thinking/reasoning part
                            if hasattr(part, "thought") and part.thought:
                                if part.text:
                                    yield ReasoningChunk(type="reasoning", text=part.text)
                            elif hasattr(part, "function_call") and part.function_call:
                                # Handle function/tool calls
                                func_call = part.function_call
                                yield ToolUse(
                                    type="tool_use",
                                    id=f"call_{uuid4().hex[:12]}",
                                    name=func_call.name,
                                    input=dict(func_call.args) if func_call.args else {},
                                )
                            else:
                                # Regular content
                                if part.text:
                                    yield TextChunk(type="text", text=part.text)

                # Fallback to text property
                elif hasattr(chunk, "text") and chunk.text:
                    yield TextChunk(type="text", text=chunk.text)

                # Store usage metadata
                if hasattr(chunk, "usage_metadata"):
                    last_usage_metadata = chunk.usage_metadata

            # Yield grounding sources if available
            if pending_grounding_metadata:
                sources = self._extract_grounding_sources(pending_grounding_metadata)
                if sources:
                    yield GroundingChunk(type="grounding", sources=sources)

            # Yield final usage information
            if last_usage_metadata:
                input_tokens = getattr(last_usage_metadata, "prompt_token_count", 0)
                output_tokens = getattr(last_usage_metadata, "candidates_token_count", 0)
                cache_read_tokens = getattr(last_usage_metadata, "cached_content_token_count", None)
                reasoning_tokens = getattr(last_usage_metadata, "thoughts_token_count", None)

                total_cost = self._calculate_cost(
                    config,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens or 0,
                )

                yield UsageChunk(
                    type="usage",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens,
                    reasoning_tokens=reasoning_tokens,
                    total_cost=total_cost,
                )
        except Exception as e:
            raise Exception(f"Gemini generate stream error: {str(e)}") from e
        finally:
            await self.client.aio.aclose()

    def _extract_grounding_sources(self, grounding_metadata: Any) -> List[dict]:
        """Extract grounding sources from metadata."""
        if not grounding_metadata:
            return []

        chunks = getattr(grounding_metadata, "grounding_chunks", None)
        if not chunks:
            return []

        sources = []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web:
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None) or uri or "Unknown Source"

                if uri:
                    sources.append(dict(title=title, url=uri))

        return sources

    def _extract_citations_only(self, grounding_metadata: Any) -> Optional[str]:
        """Extract citations as formatted string."""
        sources = self._extract_grounding_sources(grounding_metadata)

        if not sources:
            return None

        citation_links = [f"[{i + 1}]({source['url']})" for i, source in enumerate(sources)]

        return ", ".join(citation_links)

    async def complete_prompt(self, prompt: str) -> str:
        """
        Complete a simple prompt without streaming.

        Args:
            prompt: The prompt to complete

        Returns:
            The generated text response
        """
        try:
            config = self.get_model()

            # Prepare tools
            tools = []
            if self.enable_url_context:
                tools.append(types.Tool(url_context={}))

            if self.enable_grounding:
                tools.append(types.Tool(google_search={}))

            # Prepare generation config
            generation_config = types.GenerateContentConfig(
                temperature=config["temperature"],
            )

            if tools:
                generation_config.tools = tools

            # Generate content
            response = self.client.models.generate_content(
                model=config["id"],
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=generation_config,
            )

            text = response.text or ""

            # Add citations if available
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    citations = self._extract_citations_only(candidate.grounding_metadata)
                    if citations:
                        text += f"\n\nSources: {citations}"

            return text

        except Exception as e:
            raise Exception(f"Gemini complete prompt error: {str(e)}") from e

    async def count_tokens(self, content: List[AnthropicMessage]) -> int:
        """
        Count tokens for the given content using Gemini's API.

        Args:
            content: List of content blocks to count tokens for

        Returns:
            The number of tokens
        """
        try:
            config = self.get_model()

            gemini_content = convert_to_gemini_messages(content)

            response = await self.client.aio.models.count_tokens(
                model=config["id"],
                contents=gemini_content,
            )

            total_tokens = getattr(response, "total_tokens", None)

            if total_tokens is None:
                print("Gemini token counting returned None, using fallback")
                return self._fallback_count_tokens(content)

            return total_tokens

        except Exception as e:
            print(f"Gemini token counting failed: {e}")
            return self._fallback_count_tokens(content)

    def _fallback_count_tokens(self, content: List[Dict[str, Any]]) -> int:
        """Fallback token counting using rough estimation."""
        text = " ".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
        # Rough estimation: 4 characters ≈ 1 token
        return len(text) // 4

    def _calculate_cost(
        self,
        model_config: Dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
    ) -> Optional[float]:
        """
        Calculate API cost based on token usage.

        Args:
            model_config: Model configuration with pricing info
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_read_tokens: Number of cached tokens read

        Returns:
            Total cost in dollars, or None if pricing unavailable
        """
        input_price = model_config.get("input_price")
        output_price = model_config.get("output_price")
        cache_reads_price = model_config.get("cache_reads_price", 0)

        if input_price is None or output_price is None:
            return None

        # Check for tiered pricing
        tiers = model_config.get("tiers")
        if tiers:
            # Find appropriate tier based on input tokens
            tier: dict
            for tier in tiers:
                if input_tokens <= tier.get("context_window", float("inf")):
                    input_price = tier.get("input_price", input_price)
                    output_price = tier.get("output_price", output_price)
                    cache_reads_price = tier.get("cache_reads_price", cache_reads_price)
                    break

        # Calculate costs (prices are per million tokens)
        uncached_input_tokens = input_tokens - cache_read_tokens

        input_cost = input_price * (uncached_input_tokens / 1_000_000)
        output_cost = output_price * (output_tokens / 1_000_000)
        cache_cost = cache_reads_price * (cache_read_tokens / 1_000_000) if cache_read_tokens > 0 else 0

        total_cost = input_cost + output_cost + cache_cost

        return total_cost


    def get_model(self) -> ModelInfo:
        _id = self.model_id if self.model_id in GEMINI_MODELS else GEMINI_DEFAULT_MODEL_ID
        info = GEMINI_MODELS[_id]
        params = get_model_params(format="gemini", model_id=_id, model=info, settings=self.kwargs)
        is_thinking = _id.endswith(":thinking")
        data = {
            "id": _id.replace(":thinking", "") if is_thinking else _id,
            **info,
            **params,
        }
        if is_thinking:
            data["reasoning"].update({"include_thoughts": True})
        return ModelInfo(**data)


async def main():
    import os

    handler = GeminiHandler(
        api_key=os.getenv("GEMINI_API_KEY"),
        model_id="gemini-2.5-flash-preview-05-20:thinking",
        # config={"thinking_config": dict(thinking_budget_tokens=1024)},
    )
    response = await handler.complete_prompt("How many letters 'r' is in the strawberry?")
    print(response)
    msgs = [{"role": "user", "content": response}]
    response = await handler.count_tokens(msgs)
    print(response)
    print("-" * 100)
    response = handler.create_message(
        system_prompt="You are a helpful assistant.",
        messages=[{"role": "user", "content": "How many letters 'r' is in the strawberry?"}],
    )
    async for chunk in response:
        print(chunk)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
