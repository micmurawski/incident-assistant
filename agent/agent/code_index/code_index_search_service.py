import os

from agent.settings import SettingsManager
from agent.telemetry_service import get_telemetry_service
from agent.vector_store.models import (EmbedderResponse, IEmbedder,
                                       IVectorStoreClient,
                                       VectorStoreSearchResult)

logging = get_telemetry_service()


class CodeIndexSearchService:
    def __init__(self, embedder: IEmbedder, vector_store: IVectorStoreClient, settings_manager: SettingsManager):
        self.embedder = embedder
        self.vector_store = vector_store
        self.settings_manager = settings_manager

    async def search_index(self, query: str, directory_prefix: str | None = None) -> list[VectorStoreSearchResult]:
        try:
            min_score = self.settings_manager.get("code_index.search.min_score")
            max_results = self.settings_manager.get("code_index.search.max_results")

            embeddings: EmbedderResponse = await self.embedder.create_embeddings([query])

            if embeddings.embeddings is None or len(embeddings.embeddings) == 0:
                raise Exception("No embeddings returned from embedder")

            vector: list[float] = embeddings.embeddings[0]
            normalized_prefix: str | None = None
            if directory_prefix:
                normalized_prefix = os.path.normpath(directory_prefix)
            results: list[VectorStoreSearchResult] = await self.vector_store.search(
                vector, normalized_prefix, min_score, max_results
            )
            return results
        except Exception as e:
            logging.error(f"[CodeIndexSearchService] Error searching index: {e}")
            raise e
