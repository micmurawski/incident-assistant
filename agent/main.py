import asyncio

from agent.cache_manager import CacheManager
from agent.scanner import (CodeParser, DirectoryScanner, Embedder, Ignore,
                           VectorStoreClient)


async def main():
    embedder = Embedder()
    vector_store_client = VectorStoreClient()
    code_parser = CodeParser()
    cache_manager = CacheManager()
    ignore_config = Ignore()
    scanner = DirectoryScanner(
        embedder,
        vector_store_client,
        code_parser,
        cache_manager,
        ignore_config,
    )
    result = await scanner.scan_directory("/Users/micmur/GITHUB/o8s/agent/agent")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
