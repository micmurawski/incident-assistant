# Create multiton pattern for CodeIndexManager
import asyncio
import hashlib
import os
from typing import Any, Coroutine

import httpx

from agent.code_index.cache_manager import CacheManager
from agent.code_index.code_index_search_service import CodeIndexSearchService
from agent.code_index.file_processor import CodeParser
from agent.code_index.models import EmbedderInfo, IEmbedder
from agent.code_index.scanner import DirectoryScanner
from agent.code_index.vector_store import VectorStoreClient, VectorStoreSearchResult
from agent.list_files import Ignore
from agent.settings import SettingsManager
from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()


class CodeIndexManager:
    workspace_path: str
    vector_store: VectorStoreClient
    directory_scanner: DirectoryScanner
    embedder: IEmbedder
    code_index_search_service: CodeIndexSearchService
    settings_manager: SettingsManager
    _instances: dict[str, "CodeIndexManager"] = {}

    def __init__(self, workspace_path: str) -> None:
        self.settings_manager = SettingsManager.get_instance()
        self.workspace_path: str = workspace_path
        workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()
        index_cache_path_prefix = self.settings_manager.get("code_index.cache.path")
        index_cache_path = os.path.join(index_cache_path_prefix, f"{workspace_hash}.json")
        self.cache_manager: CacheManager = CacheManager.get_instance(index_cache_path)

    @staticmethod
    def get_instance(workspace_path: str | None = None) -> "CodeIndexManager":
        if workspace_path is None:
            workspace_path = os.getcwd()
        if workspace_path not in CodeIndexManager._instances:
            CodeIndexManager._instances[workspace_path] = CodeIndexManager(workspace_path)
        return CodeIndexManager._instances[workspace_path]

    @classmethod
    def dispose_all(cls) -> None:
        for k in cls._instances:
            del cls._instances[k]

    def ensure_running_vector_store(self):
        settings = self.settings_manager.set("code_index.vector_store")
        if settings.get("provider") == "qdrant":
            url = f"{settings.get('host')}:{settings.get('port')}/health"
            response = httpx.get(url)
            if response.status_code / 100 != 2:
                from agent.code_index.qdrant import run_qdrant_container

                run_qdrant_container()

    async def create_services(self) -> Coroutine[Any, Any, tuple[IEmbedder, VectorStoreClient, DirectoryScanner]]:
        embedder_settings = self.settings_manager.get_section("code_index.embedder")
        provider = embedder_settings.pop("provider")
        if provider == "gemini":
            from agent.code_index.embedders.gemini import GeminiEmbedder

            embedder = GeminiEmbedder(**embedder_settings)
        elif provider == "ollama":
            from agent.code_index.embedders.ollama import OllamaEmbedder

            embedder = OllamaEmbedder(**embedder_settings)
        elif provider == "openai_compatible":
            from agent.code_index.embedders.openai_compatible import OpenAICompatibleEmbedder

            embedder = OpenAICompatibleEmbedder(**embedder_settings)
        else:
            raise ValueError(f"Unknown embedder provider: {provider}")
        await embedder.validate_configuration()

        embedder_info: EmbedderInfo = await embedder.info()
        code_parser = CodeParser()

        vector_store = VectorStoreClient(self.workspace_path, vector_size=embedder_info.vector_size)
        ignore = Ignore()

        directory_scanner = DirectoryScanner(
            embedder=embedder,
            vector_store_client=vector_store,
            code_parser=code_parser,
            cache_manager=self.cache_manager,
            ignore_config=ignore,
        )
        return embedder, vector_store, directory_scanner

    async def initialize(self) -> Coroutine[Any, Any, None]:
        embedder, vector_store, directory_scanner = await self.create_services()
        self.embedder = embedder
        self.vector_store = vector_store
        self.directory_scanner = directory_scanner
        self.code_index_search_service = CodeIndexSearchService(self.embedder, self.vector_store, self.settings_manager)
        self.ensure_running_vector_store()
        await self.vector_store.initialize()
        await self.directory_scanner.scan_directory(self.workspace_path)

    async def search_index(self, query: str, directory_prefix: str | None = None) -> list[VectorStoreSearchResult]:
        return self.code_index_search_service.search_index(query, directory_prefix)

    async def dispose(self) -> Coroutine[Any, Any, None]:
        logging.info("[CodeIndexManager] Disposing")
        logging.info("[CodeIndexManager] Disposing cache manager")
        logging.info("[CodeIndexManager] Disposing vector store")
        await self.vector_store.delete_collection()
        logging.info("[CodeIndexManager] Disposing cache manager")
        await self.cache_manager._clear_cache()


async def main():
    print(os.getcwd())
    code_index_manager = CodeIndexManager(os.getcwd())
    await code_index_manager.initialize()
    # await code_index_manager.dispose()


if __name__ == "__main__":
    asyncio.run(main())
