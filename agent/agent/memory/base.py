from abc import ABC, abstractmethod
from typing import Any


class MemoryStore(ABC):
    @abstractmethod
    async def get(self, key: str, namespace: str | None = None) -> Any:
        """Retrieve a memory by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, namespace: str | None = None):
        """Store a memory with a key and optional namespace."""
        pass

    @abstractmethod
    async def query(self, query_text: str, namespace: str | None = None, limit: int = 5) -> list[Any]:
        """Query relevant memories using natural language."""
        pass
