import asyncio
import base64
import logging
import math
import struct
from time import time
from typing import Any, Coroutine

import aiohttp
import openai

from agent.constants import (INITIAL_RETRY_DELAY_MS, MAX_BATCH_RETRIES,
                             MAX_ITEM_TOKENS)
from agent.vector_store.models import (EmbedderInfo, EmbedderResponse,
                                       IEmbedder, Usage)

from .models import get_model_query_prefix


class OpenAICompatibleEmbedder(IEmbedder):
    _rate_limit_state = {
        "is_rate_limited": False,
        "last_rate_limit_reset_time": 0,
        "consecutive_rate_limit_failures": 0,
        "mutex": asyncio.Lock(),
    }

    def __init__(self, base_url: str, api_key: str, model: str | None = None, max_item_tokens: int = 1000):
        self.base_url = base_url
        self.api_key = api_key
        self.embeddings_client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self.model = model or "text-embedding-3-small"
        self.max_item_tokens = max_item_tokens or MAX_ITEM_TOKENS

    async def create_embeddings(self, texts: list[str], model: str | None = None) -> EmbedderResponse:
        query_prefix = get_model_query_prefix("openai-compatible", model or self.model)
        processed_texts = []
        if query_prefix:
            for idx, text in enumerate(texts):
                if text.startswith(query_prefix):
                    processed_texts.append(text)
                else:
                    prefixed_text = f"{query_prefix}{text}"
                    estimated_tokens = math.ceil(len(prefixed_text.split()) / 4)
                    if estimated_tokens > MAX_ITEM_TOKENS:
                        logging.error(
                            f"Estimated tokens {estimated_tokens} is greater than max item tokens {MAX_ITEM_TOKENS}"
                        )
                        processed_texts.append(text)
                    processed_texts.append(prefixed_text)
        else:
            processed_texts = texts

        all_embeddings = []
        usage = Usage(prompt_tokens=0, total_tokens=0)
        remaining_texts = processed_texts
        while remaining_texts:
            current_batch = []
            current_batch_tokens = 0
            processed_indices = []
            for i in range(len(remaining_texts)):
                txt = remaining_texts[i]
                item_tokens = math.ceil(len(txt) / 4)
                if item_tokens > self.max_item_tokens:
                    logging.warning(f"Text {txt} is too long to embed. Skipping.")
                    processed_indices.append(i)
                    continue
                if current_batch_tokens + item_tokens <= self.max_item_tokens:
                    current_batch.append(txt)
                    current_batch_tokens += item_tokens
                    processed_indices.append(i)
                else:
                    break

            for idx in reversed(processed_indices):
                del remaining_texts[idx]

            if len(current_batch) > 0:
                batch_result = await self._embed_batch_with_retries(current_batch, model or self.model)
                all_embeddings.extend(batch_result["embeddings"])
                usage["promptTokens"] += batch_result["usage"]["promptTokens"]
                usage["totalTokens"] += batch_result["usage"]["totalTokens"]

        return EmbedderResponse(embeddings=all_embeddings, usage=usage)

    async def _wait_for_global_rate_limit(self) -> None:
        async with self._rate_limit_state["mutex"]:
            state = self._rate_limit_state
            if state["is_rate_limited"] and state["last_rate_limit_reset_time"] > time.time():
                wait_time = state["last_rate_limit_reset_time"] - time.time()
                await asyncio.sleep(wait_time)
                return

            if state["is_rate_limited"] and state["last_rate_limit_reset_time"] <= time.time():
                state["is_rate_limited"] = False
                state["consecutive_rate_limit_failures"] = 0

    async def _make_direct_embedding_request(self, url: str, batch_texts: list[str], model: str) -> dict[str, Any]:
        response = await aiohttp.ClientSession().post(
            url,
            headers={
                "Content-Type": "application/json",
                "api-key": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
            },
            json={"model": model, "input": batch_texts, "encoding_format": "base64"},
        )
        if not response.ok:
            raise Exception(f"embeddings:openai-compatible.requestFailed: {response.status} {response.reason}")

        return await response.json()

    async def get_global_rate_limit_delay(self) -> int:
        async with self._rate_limit_state["mutex"]:
            state = self._rate_limit_state
            if state["is_rate_limited"] and state["last_rate_limit_reset_time"] > time.time():
                return state["last_rate_limit_reset_time"] - time.time()
            return 0

    async def info(self) -> Coroutine[Any, Any, EmbedderInfo]:
        return EmbedderInfo(name="openai-compatible", model=self.model)

    async def _embed_batch_with_retries(
        self, batch_texts: list[str], model: str | None = None
    ) -> Coroutine[Any, Any, dict[str, list[list[float]]]]:
        model_to_use = model or self.model
        for attempt in range(MAX_BATCH_RETRIES):
            await self._wait_for_global_rate_limit()
            try:
                if self.base_url:
                    response = await self._make_direct_embedding_request(self.base_url, batch_texts, model_to_use)
                else:
                    response = await self.embeddings_client.embeddings.create(input=batch_texts, model=model_to_use)

                processed_embeddings = []
                for item in response.get("data", []):
                    if isinstance(item.get("embedding"), str):
                        buffer = base64.b64decode(item["embedding"])
                        float_count = len(buffer) // 4
                        float32_list = list(struct.unpack("<" + "f" * float_count, buffer))
                        new_item = dict(item)
                        new_item["embedding"] = float32_list
                        processed_embeddings.append(new_item)
                    else:
                        processed_embeddings.append(item)
                return {"embeddings": processed_embeddings, "usage": response["usage"]}
            except Exception as e:
                logging.error(f"Error creating embeddings: {e}")
                has_more_attempts = attempt < MAX_BATCH_RETRIES - 1
                if has_more_attempts:
                    base_delay = INITIAL_RETRY_DELAY_MS * (2**attempt)
                    global_delay = await self.get_global_rate_limit_delay()
                    delay = max(base_delay, global_delay)
                    logging.warning(
                        f"Error creating embeddings: {e}. Retrying in {delay}ms, attempt {attempt + 1} of {MAX_BATCH_RETRIES}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception(
                        f"OpenAI Compatible Embedder: Failed to create embeddings after {MAX_BATCH_RETRIES} attempts"
                    ) from e
