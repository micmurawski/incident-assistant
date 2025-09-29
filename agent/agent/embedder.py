from dataclasses import dataclass
from typing import Any, Coroutine, Optional


class Usage:
    prompt_tokens: int
    total_tokens: int


@dataclass
class EmmbedderResponse:
    embeddings: list[list[float]]
    usage: Optional[Usage] = None


class Embedder:
    async def create_embeddings(self, texts: list[str]) -> Coroutine[Any, Any, dict[str, list[list[float]]]]:
        pass

    async def validate_configuration() -> Coroutine[Any, Any, (bool, str)]:
        pass

    def info(self) -> str:
        pass
