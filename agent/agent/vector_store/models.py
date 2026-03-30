from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Coroutine, Literal, Optional

from qdrant_client.models import CollectionInfo


@dataclass(frozen=True)
class EmbedderInfo:
    name: str
    model: str
    vector_size: int


class AbstractPayload(ABC):
    
    @property
    @abstractmethod
    def payload_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "AbstractPayload":
        raise NotImplementedError

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


class MemoPayload(AbstractPayload):
    id: str
    value: Any

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoPayload":
        return cls(id=data["id"], value=data["value"])

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "value": self.value}


@dataclass
class CodebasePayload(AbstractPayload):
    @property
    def payload_type(self) -> str:
        return "codebase"

    file_path: str
    code_chunk: str
    start_line: int
    end_line: int
    segment_hash: str
    type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodebasePayload":
        return cls(
            file_path=data["file_path"],
            code_chunk=data["code_chunk"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            segment_hash=data["segment_hash"],
            type=data["type"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "code_chunk": self.code_chunk,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "segment_hash": self.segment_hash,
            "type": self.type,
        }


@dataclass
class PointStruct:
    id: str
    vector: list[float]
    payload: AbstractPayload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PointStruct":
        # Detect which payload subclass to use from the dict keys
        payload_data = data["payload"]
        if "file_path" in payload_data and "code_chunk" in payload_data:
            payload = CodebasePayload.from_dict(payload_data)
        elif "id" in payload_data and "value" in payload_data:
            payload = MemoPayload.from_dict(payload_data)
        else:
            # fallback, could raise an exception or use AbstractPayload
            payload = AbstractPayload()
        return cls(id=data["id"], vector=data["vector"], payload=payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "vector": self.vector,
            "payload": self.payload.to_dict(),
        }


@dataclass(frozen=True)
class VectorStoreSearchResult:
    id: str
    score: float
    payload: dict[str, Any]


class IVectorStoreClient(ABC):
    @abstractmethod
    def parse_url(self, url: str) -> tuple[str, int, bool]:
        pass

    @abstractmethod
    async def get_collection_info(self) -> Coroutine[Any, Any, CollectionInfo]:
        pass

    @abstractmethod
    async def initialize(self) -> Coroutine[Any, Any, bool]:
        pass

    @abstractmethod
    async def delete_points_by_file_path(self, file_path: str) -> Coroutine[Any, Any, None]:
        pass

    @abstractmethod
    async def delete_points_by_multiple_file_paths(self, file_paths: list[str]) -> Coroutine[Any, Any, None]:
        pass

    @abstractmethod
    async def upsert_points(self, points: list[PointStruct], collection_name: str | None = None) -> Coroutine[Any, Any, None]:
        pass

    @abstractmethod
    async def retrieve(self, ids: list[str], collection_name: str | None = None) -> list[VectorStoreSearchResult]:
        pass

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        directory_prefix: Optional[str] = None,
        min_score: Optional[float] = None,
        max_results: Optional[int] = None,
    ) -> list[VectorStoreSearchResult]:
        pass

    @abstractmethod
    async def clear_collection(self) -> Coroutine[Any, Any, None]:
        pass

    @abstractmethod
    async def delete_collection(self) -> Coroutine[Any, Any, None]:
        pass


@dataclass
class Usage:
    prompt_tokens: int
    total_tokens: int


@dataclass
class EmbedderResponse:
    embeddings: list[list[float]]
    usage: Optional[Usage] = None


class IEmbedder(ABC):
    @abstractmethod
    async def create_embeddings(
        self, texts: list[str], model: str | None = None
    ) -> Coroutine[Any, Any, EmbedderResponse]:
        pass

    @abstractmethod
    async def validate_configuration() -> Coroutine[Any, Any, tuple[bool, str]]:
        pass

    @abstractmethod
    async def info(self) -> Coroutine[Any, Any, EmbedderInfo]:
        pass


@dataclass
class FileProcessingResult:
    path: str
    status: Literal["success", "skipped", "error", "processed_for_batching", "local_error"]
    error: Optional[Exception]
    reason: Optional[str]
    new_hash: Optional[str]
    points_to_upsert: list[PointStruct]


class IFileWatcher(ABC):
    @abstractmethod
    async def process_file(self, file_path: str) -> Coroutine[Any, Any, FileProcessingResult]:
        pass


class IConfigurationManager(ABC):
    current_search_results: int
    current_search_min_score: float
