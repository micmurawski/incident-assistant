import asyncio

from agent.file_ops import FileOpsManager


async def main():
    file_ops_manager = FileOpsManager.get_instance(
        "/Users/micmur/GITHUB/o8s/services/robot-shop-worktrees/fault-web-4-e44494a0-3799-4b62-9983-c87b45c50d93"
    )
    result = await file_ops_manager.list_files_tool(".", False)
    for line in result.content.split("\n"):
        print(line)


if __name__ == "__main__":
    asyncio.run(main())
