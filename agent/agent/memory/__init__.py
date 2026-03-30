import os

from agent.memory.base import MemoryStore
from agent.memory.vector_store_memory import VectorStoreMemory
from agent.settings import SettingsManager
from agent.vector_store.client import VectorStoreClient
from agent.vector_store.models import EmbedderInfo


async def get_memory_store(collection_name: str = "memory") -> MemoryStore:
    """Factory function to get a MemoryStore instance."""
    settings_manager = SettingsManager.get_instance()

    # Reuse embedder settings from code_index as default
    embedder_settings = settings_manager.get_section("code_index.embedder")
    provider = embedder_settings.pop("provider")

    if provider == "gemini":
        from agent.code_index.embedders.gemini import GeminiEmbedder
        embedder = GeminiEmbedder(**embedder_settings)
    elif provider == "ollama":
        from agent.code_index.embedders.ollama import OllamaEmbedder
        embedder = OllamaEmbedder(**embedder_settings)
    elif provider == "openai_compatible":
        from agent.code_index.embedders.openai_compatible import \
            OpenAICompatibleEmbedder
        embedder = OpenAICompatibleEmbedder(**embedder_settings)
    else:
        raise ValueError(f"Unknown embedder provider: {provider}")

    await embedder.validate_configuration()
    embedder_info: EmbedderInfo = await embedder.info()

    workspace_path = settings_manager.get("workspace.path", os.getcwd())
    vector_store = VectorStoreClient(workspace_path, vector_size=embedder_info.vector_size)

    return VectorStoreMemory(vector_store, embedder, collection_name=collection_name)
