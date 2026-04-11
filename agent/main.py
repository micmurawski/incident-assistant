import asyncio
import os

from agent.file_ops import FileOpsManager
from agent.repo_paths import get_repo_root


async def main():
    worktree = os.environ.get("FILE_OPS_WORKTREE")
    if not worktree:
        worktree = str(
            get_repo_root()
            / "services"
            / "robot-shop-worktrees"
            / "fault-web-4-e44494a0-3799-4b62-9983-c87b45c50d93"
        )
    file_ops_manager = FileOpsManager.get_instance(worktree)
    result = await file_ops_manager.list_files_tool(".", False)
    for line in result.content.split("\n"):
        print(line)


if __name__ == "__main__":
    asyncio.run(main())
