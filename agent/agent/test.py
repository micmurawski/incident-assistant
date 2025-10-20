import asyncio
import os

import docker

from agent.code_index.code_index_manager import CodeIndexManager
from agent.context import Context
from agent.file_ops import FileOpsManager
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools


async def main():
    cwd = os.getcwd()
    context = Context()
    await context.code_index_manager.initialize()


if __name__ == "__main__":
    asyncio.run(main())
