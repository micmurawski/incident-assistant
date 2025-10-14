# Create multiton pattern for CodeIndexManager
import asyncio
import hashlib
import os
from typing import Any, Coroutine

from agent.code_index.cache_manager import CacheManager
from agent.code_index.file_processor import CodeParser
from agent.code_index.list_files import Ignore
from agent.code_index.models import EmbedderInfo, IEmbedder
from agent.code_index.scanner import DirectoryScanner
from agent.code_index.vector_store import VectorStoreClient
from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()


class CodeIndexManager:
    _instances: dict[str, "CodeIndexManager"] = {}
    vector_store: VectorStoreClient
    directory_scanner: DirectoryScanner
    embedder: IEmbedder

    def __init__(self, workspace_path: str) -> None:
        self.workspace_path: str = workspace_path
        workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()
        index_cache_path = f".code_index_cache/{workspace_hash}.json"
        self.cache_manager: CacheManager = CacheManager.get_instance(
            index_cache_path)
        self.config: dict = {
            "embedder.provider": "ollama",
            # "embedder.api_key": "AIzaSyAyD6Nns1i6lRK2S0OqJrf-YcA_nBQ5_3s",
            "embedder.model": None,
        }

    @staticmethod
    def get_instance(context: Any, workspace_path: str | None = None) -> "CodeIndexManager":
        if workspace_path is None:
            workspace_path = os.getcwd()
        if workspace_path not in CodeIndexManager._instances:
            CodeIndexManager._instances[workspace_path] = CodeIndexManager(
                context,
                workspace_path
            )
        return CodeIndexManager._instances[workspace_path]

    @classmethod
    def dispose_all(cls) -> None:
        for k in cls._instances:
            del cls._instances[k]

    async def create_services(self) -> Coroutine[Any, Any, tuple[IEmbedder, VectorStoreClient, DirectoryScanner]]:
        if self.config["embedder.provider"] == "gemini":
            from agent.code_index.embedders.gemini import GeminiEmbedder
            embedder = GeminiEmbedder(api_key=self.config["embedder.api_key"])
        elif self.config["embedder.provider"] == "ollama":
            from agent.code_index.embedders.ollama import OllamaEmbedder
            embedder = OllamaEmbedder(model=self.config["embedder.model"])
        elif self.config["embedder.provider"] == "openai_compatible":
            from agent.code_index.embedders.openai_compatible import \
                OpenAICompatibleEmbedder
            embedder = OpenAICompatibleEmbedder(
                base_url=self.config["embedder.base_url"],
                api_key=self.config["embedder.api_key"],
                model=self.config["embedder.model"]
            )
        await embedder.validate_configuration()
        embedder_info: EmbedderInfo = await embedder.info()
        code_parser = CodeParser()
        vector_store = VectorStoreClient(
            self.workspace_path, vector_size=embedder_info.vector_size)
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
        await self.vector_store.initialize()
        await self.directory_scanner.scan_directory(self.workspace_path)

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
