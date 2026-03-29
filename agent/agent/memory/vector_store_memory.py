from typing import Any

from agent.code_index.embedders.gemini import GeminiEmbedder
from agent.memory.base import MemoryStore
from agent.vector_store.client import VectorStoreClient
from agent.vector_store.models import (EmbedderResponse, IEmbedder,
                                       IVectorStoreClient, MemoPayload,
                                       PointStruct, VectorStoreSearchResult)


class VectorStoreMemory(MemoryStore):
    def __init__(
        self,
        vector_store: IVectorStoreClient,
        embedder: IEmbedder,
        collection_name: str = "memory",
        namespace: str | None = None
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.collection_name = collection_name
        self._initialized = False

    async def _ensure_initialized(self):
        if not self._initialized:
            await self.vector_store.initialize(self.collection_name)
            self._initialized = True

    async def get(self, key: str, namespace: str | None = None) -> Any:
        await self._ensure_initialized()
        full_key = f"{namespace}:{key}" if namespace else key
        results = await self.vector_store.retrieve([full_key], collection_name=self.collection_name)
        if results:
            return results[0].payload.get("value")
        return None

    async def set(self, key: str, value: Any, namespace: str | None = None):
        await self._ensure_initialized()
        full_key = f"{namespace}:{key}" if namespace else key
        text_to_embed = str(value)
        embeddings_res: EmbedderResponse = await self.embedder.create_embeddings([text_to_embed])
        vector: list[float] = embeddings_res.embeddings[0]

        payload = MemoPayload(id=full_key, value=value)
        point = PointStruct(id=full_key, vector=vector, payload=payload)
        await self.vector_store.upsert_points([point], collection_name=self.collection_name)

    async def query(self, query_text: str, namespace: str | None = None, limit: int = 5) -> list[Any]:
        await self._ensure_initialized()
        embeddings_res: EmbedderResponse = await self.embedder.create_embeddings([query_text])
        query_vector: list[float] = embeddings_res.embeddings[0]

        # NOTE: Currently we don't have a specific filter for namespace in VectorStoreClient.search
        # but we could add it if needed. For now, we search globally in the memory collection.
        results: list[VectorStoreSearchResult] = await self.vector_store.search(
            query_vector,
            collection_name=self.collection_name,
            max_results=limit
        )
        res = []
        result: VectorStoreSearchResult
        for result in results:
            if result.payload.get("namespace") == namespace:
                res.append(result.payload.get("value"))
        return res


if __name__ == "__main__":
    import asyncio

    async def main():
        vector_store = VectorStoreClient(workspace_path=".")
        embedder = GeminiEmbedder(api_key="", model="")
        memory = VectorStoreMemory(vector_store, embedder, collection_name="memory")
        await memory.set("test", "test")
        print(await memory.get("test"))
        print(await memory.query("test"))
    asyncio.run(main())
