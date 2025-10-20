import asyncio
import logging
import math
from typing import Any, Coroutine

import aiohttp

from agent.code_index.models import EmbedderInfo, EmbedderResponse, IEmbedder, Usage
from agent.constants import MAX_ITEM_TOKENS, OLLAMA_EMBEDDING_TIMEOUT

from .models import get_model_dimension, get_model_query_prefix

DEFAULT_MODEL = "nomic-embed-text"


class OllamaEmbedder(IEmbedder):
    def __init__(self, model: str | None = None, **kwargs):
        self.base_url = kwargs.get("base_url", "http://localhost:11434")
        self.model = model or DEFAULT_MODEL

    async def create_embeddings(
        self, texts: list[str], model: str | None = None
    ) -> Coroutine[Any, Any, EmbedderResponse]:
        model_to_use = model or self.model
        url = f"{self.base_url}/api/embed"
        query_prefix = get_model_query_prefix("ollama", model_to_use)
        processed_text = []
        if query_prefix:
            for idx, text in enumerate(texts):
                if text.startswith(query_prefix):
                    processed_text.append(text)
                else:
                    prefixed_text = f"{query_prefix}{text}"
                    estimated_tokens = math.ceil(len(prefixed_text.split()) / 4)
                    if estimated_tokens > MAX_ITEM_TOKENS:
                        logging.error(
                            f"Estimated tokens {estimated_tokens} is greater than max item tokens {MAX_ITEM_TOKENS}"
                        )
                        processed_text.append(text)
                    processed_text.append(prefixed_text)
        else:
            processed_text = texts
        try:
            headers = {
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "input": processed_text,
            }
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        url, headers=headers, json=payload, timeout=OLLAMA_EMBEDDING_TIMEOUT
                    ) as response:
                        if not response.ok:
                            try:
                                error_body = await response.text()
                            except Exception:
                                pass
                            raise Exception(
                                "embeddings:ollama.requestFailed",
                                {
                                    "status": response.status,
                                    "statusText": response.reason,
                                    "errorBody": error_body,
                                },
                            )
                        data = await response.json()
                except asyncio.TimeoutError:
                    raise Exception("embeddings:ollama.requestTimeout")
            embeddings = data.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                raise Exception("embeddings:ollama.invalidResponse")

            return EmbedderResponse(
                embeddings=embeddings,
                usage=Usage(
                    prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                    total_tokens=data.get("usage", {}).get("total_tokens", 0),
                ),
            )
        except Exception as e:
            logging.error(f"Error creating embeddings: {e}")
            raise Exception(f"embeddings:ollama.requestFailed: {e}")

    async def validate_configuration(self) -> Coroutine[Any, Any, tuple[bool, str]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=OLLAMA_EMBEDDING_TIMEOUT) as response:
                    if not response.ok:
                        return False, response.reason
        except asyncio.TimeoutError:
            raise Exception("embeddings:ollama.requestTimeout")
        return True, "Configuration is valid"

    async def info(self) -> Coroutine[Any, Any, EmbedderInfo]:
        return EmbedderInfo(name="ollama", model=self.model, vector_size=get_model_dimension("ollama", self.model))
