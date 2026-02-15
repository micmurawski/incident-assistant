import asyncio
import logging
import time

from google import genai

from agent.code_index.embedders.models import get_model_dimension
from agent.code_index.models import (EmbedderInfo, EmbedderResponse, IEmbedder,
                                     Usage)
from agent.constants import INITIAL_RETRY_DELAY_MS, MAX_BATCH_RETRIES

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiEmbedder(IEmbedder):
    _rate_limit_state = {
        "is_rate_limited": False,
        "last_rate_limit_reset_time": 0,
        "consecutive_rate_limit_failures": 0,
        "mutex": asyncio.Lock(),
    }

    async def get_global_rate_limit_delay(self) -> int:
        async with self._rate_limit_state["mutex"]:
            state = self._rate_limit_state
            if state["is_rate_limited"] and state["last_rate_limit_reset_time"] > time.time():
                return state["last_rate_limit_reset_time"] - time.time()
            return 0

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

    def __init__(self, api_key: str, model: str | None = DEFAULT_MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def create_embeddings(self, texts: list[str]) -> EmbedderResponse:
        print("creating embeddings...")
        for attempt in range(MAX_BATCH_RETRIES):
            await self._wait_for_global_rate_limit()
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=texts,
                )
                return EmbedderResponse(
                    embeddings=response.text,
                    usage=Usage(
                        prompt_tokens=response.usage_metadata.prompt_token_count,
                        total_tokens=response.usage_metadata.total_token_count,
                    ),
                )
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

    async def validate_configuration(self) -> (bool, str):
        return True, "Configuration is valid"

    def info(self) -> EmbedderInfo:
        return EmbedderInfo(name="gemini", model=self.model, vector_size=get_model_dimension("gemini", self.model))
