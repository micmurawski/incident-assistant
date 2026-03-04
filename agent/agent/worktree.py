import asyncio
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Worktree:
    path: str
    is_current: bool
    is_bare: bool = False
    is_detached: bool = False
    is_locked: bool = False
    branch: Optional[str] = None
    commit_hash: Optional[str] = None
    lock_reason: Optional[str] = None


@dataclass
class WorktreeResult:
    success: bool
    message: str
    worktree: Optional[Worktree] = None


@dataclass
class BranchInfo:
    local_branches: List[str]
    remote_branches: List[str]
    current_branch: str

# --- Service Implementation ---


class WorkTreeService:
    """
    Service for managing git worktrees.
    All methods are platform-agnostic.
    """

    def __init__(self):
        self.git_installed = asyncio.run(self.check_git_installed())
        if not self.git_installed:
            raise RuntimeError("Git is not installed on the system")

    async def _exec(self, args: List[str], cwd: Optional[str] = None) -> str:
        """
        Internal helper to execute git commands asynchronously.
        Matches execFileAsync behavior.
        """
        try:
            # If cwd is provided, ensure it exists
            if cwd and not os.path.exists(cwd):
                raise FileNotFoundError(f"Directory not found: {cwd}")

            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # Decode stderr for the error message
                error_msg = stderr.decode('utf-8').strip()
                raise Exception(error_msg or f"Command failed with code {process.returncode}")

            return stdout.decode('utf-8')
        except Exception as e:
            logger.error(f"Error executing git command: {e}")
            return ""

    async def check_git_installed(self) -> bool:
        """Check if git is installed on the system."""
        try:
            await self._exec(["git", "--version"])
            return True
        except Exception as e:
            logger.error(f"Error checking git installation: {e}")
            return False

    async def check_git_repo(self, cwd: str) -> bool:
        """Check if a directory is a git repository."""
        try:
            await self._exec(["git", "rev-parse", "--git-dir"], cwd=cwd)
            return True
        except Exception as e:
            logger.error(f"Error checking git repository: {e}")
            return False

    async def get_git_root_path(self, cwd: str) -> Optional[str]:
        """Get the git repository root path."""
        try:
            output = await self._exec(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
            return output.strip()
        except Exception as e:
            logger.error(f"Error getting git repository root path: {e}")
            return None

    async def get_current_worktree_path(self, cwd: str) -> Optional[str]:
        """Get the current worktree path."""
        # Logic matches getGitRootPath in original code
        return await self.get_git_root_path(cwd)

    async def get_current_branch(self, cwd: str) -> Optional[str]:
        """Get the current branch name."""
        try:
            output = await self._exec(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
            branch = output.strip()
            return None if branch == "HEAD" else branch
        except Exception as e:
            logger.error(f"Error getting current branch: {e}")
            return None

    async def list_worktrees(self, cwd: str) -> List[Worktree]:
        """List all worktrees in the repository."""
        try:
            output = await self._exec(["git", "worktree", "list", "--porcelain"], cwd=cwd)
            return self._parse_worktree_output(output, cwd)
        except Exception as e:
            logger.error(f"Error listing worktrees: {e}")
            return []

    async def create_worktree(self, cwd: str, path: str, branch: Optional[str] = None, base_branch: Optional[str] = None, create_new_branch: bool = False) -> WorktreeResult:
        """Create a new worktree."""
        try:
            # Build arguments
            args = ["git", "worktree", "add"]

            if create_new_branch and branch:
                # Create new branch: git worktree add -b <branch> <path> [<base>]
                args.extend(["-b", branch, path])
                if base_branch:
                    args.append(base_branch)
            elif branch:
                # Checkout existing branch: git worktree add <path> <branch>
                args.extend([path, branch])
            else:
                # Detached HEAD
                args.extend(["--detach", path])

            await self._exec(args, cwd=cwd)

            # Get the created worktree info
            worktrees = await self.list_worktrees(cwd)

            # Find the match using normalized paths
            normalized_target = self._normalize_path(path)
            created_worktree = next(
                (wt for wt in worktrees if self._normalize_path(wt.path) == normalized_target),
                None
            )

            return WorktreeResult(
                success=True,
                message=f"Worktree created at {path}",
                worktree=created_worktree
            )

        except Exception as error:
            return WorktreeResult(
                success=False,
                message=f"Failed to create worktree: {str(error)}"
            )

    async def delete_worktree(self, cwd: str, worktree_path: str, force: bool = False) -> WorktreeResult:
        """Delete a worktree."""
        try:
            # Get worktree info BEFORE deletion to capture the branch name
            worktrees = await self.list_worktrees(cwd)
            normalized_target = self._normalize_path(worktree_path)
            worktree_to_delete = next(
                (wt for wt in worktrees if self._normalize_path(wt.path) == normalized_target),
                None
            )

            args = ["git", "worktree", "remove"]
            if force:
                args.append("--force")
            args.append(worktree_path)

            await self._exec(args, cwd=cwd)

            # Also try to delete the branch if it exists
            if worktree_to_delete and worktree_to_delete.branch:
                try:
                    await self._exec(["git", "branch", "-d", worktree_to_delete.branch], cwd=cwd)
                except Exception as e:
                    logger.error(f"Error deleting branch: {e}")
                    # Branch deletion is best-effort
                    pass

            return WorktreeResult(
                success=True,
                message=f"Worktree removed from {worktree_path}"
            )

        except Exception as error:
            return WorktreeResult(
                success=False,
                message=f"Failed to delete worktree: {str(error)}"
            )

    async def get_available_branches(self, cwd: str, include_worktree_branches: bool = False) -> BranchInfo:
        """
        Get available branches.

        Args:
            cwd: Current working directory
            include_worktree_branches: If true, include branches already checked out in worktrees
        """
        try:
            # Run all git commands in parallel (equivalent to Promise.all)
            results = await asyncio.gather(
                self.list_worktrees(cwd),
                self._exec(["git", "branch", "--format=%(refname:short)"], cwd=cwd),
                self._exec(["git", "branch", "-r", "--format=%(refname:short)"], cwd=cwd),
                self.get_current_branch(cwd),
                return_exceptions=True  # Prevent one failure from crashing all
            )

            # Unpack results, handling potential exceptions
            worktrees = results[0] if not isinstance(results[0], Exception) else []
            local_out = results[1] if not isinstance(results[1], Exception) else ""
            remote_out = results[2] if not isinstance(results[2], Exception) else ""
            current_branch = results[3] if not isinstance(results[3], Exception) else ""

            branches_in_worktrees = {wt.branch for wt in worktrees if wt.branch}

            # Filter local branches
            local_lines = local_out.strip().split('\n')
            local_branches = [
                b for b in local_lines
                if b and (include_worktree_branches or b not in branches_in_worktrees)
            ]

            # Filter remote branches
            remote_lines = remote_out.strip().split('\n')
            remote_branches = []
            for b in remote_lines:
                if not b or "HEAD" in b:
                    continue

                # Check normalized name (removing origin/ prefix for comparison)
                clean_name = b.replace("origin/", "", 1) if b.startswith("origin/") else b

                if include_worktree_branches or clean_name not in branches_in_worktrees:
                    remote_branches.append(b)

            return BranchInfo(
                local_branches=local_branches,
                remote_branches=remote_branches,
                current_branch=current_branch or ""
            )

        except Exception as e:
            logger.error(f"Error getting available branches: {e}")
            return BranchInfo(
                local_branches=[],
                remote_branches=[],
                current_branch=""
            )

    async def checkout_branch(self, cwd: str, branch: str) -> WorktreeResult:
        """Checkout a branch in the current worktree."""
        try:
            await self._exec(["git", "checkout", branch], cwd=cwd)
            return WorktreeResult(
                success=True,
                message=f"Checked out branch {branch}"
            )
        except Exception as error:
            logger.error(f"Error checking out branch: {error}")
            return WorktreeResult(
                success=False,
                message=f"Failed to checkout branch: {str(error)}"
            )

    def _parse_worktree_output(self, output: str, current_cwd: str) -> List[Worktree]:
        """Parse git worktree list --porcelain output."""
        worktrees: List[Worktree] = []
        entries = output.strip().split("\n\n")

        for entry in entries:
            if not entry.strip():
                continue

            lines = entry.strip().split("\n")
            wt_data = {
                "path": "",
                "branch": None,
                "commit_hash": None,
                "is_bare": False,
                "is_detached": False,
                "is_locked": False,
                "lock_reason": None
            }

            for line in lines:
                if line.startswith("worktree "):
                    wt_data["path"] = line[9:].strip()
                elif line.startswith("HEAD "):
                    wt_data["commit_hash"] = line[5:].strip()
                elif line.startswith("branch "):
                    branch_ref = line[7:].strip()
                    wt_data["branch"] = branch_ref.replace("refs/heads/", "")
                elif line == "bare":
                    wt_data["is_bare"] = True
                elif line == "detached":
                    wt_data["is_detached"] = True
                elif line == "locked":
                    wt_data["is_locked"] = True
                elif line.startswith("locked "):
                    wt_data["is_locked"] = True
                    wt_data["lock_reason"] = line[7:].strip()

            if wt_data["path"]:
                is_current = self._normalize_path(wt_data["path"]) == self._normalize_path(current_cwd)

                worktrees.append(Worktree(
                    path=wt_data["path"],
                    is_current=is_current,
                    is_bare=wt_data["is_bare"],
                    is_detached=wt_data["is_detached"],
                    is_locked=wt_data["is_locked"],
                    branch=wt_data["branch"],
                    commit_hash=wt_data["commit_hash"],
                    lock_reason=wt_data["lock_reason"]
                ))

        return worktrees

    def _normalize_path(self, p: str) -> str:
        """
        Normalize a path for comparison.
        Resolves .. segments and standardizes separators.
        Mimics logic: removes trailing slash except for root.
        """
        normalized = os.path.normpath(p)

        # os.path.normpath in Python usually removes trailing slashes automatically.
        # But to be safe and match the TypeScript logic specifically:

        # Check if it's a root path (e.g. "/" or "C:\") which shouldn't be stripped
        is_root = False
        if os.name == 'nt':
            # Windows root check (e.g. C:\)
            if len(normalized) <= 3 and normalized.endswith(':\\'):
                is_root = True
        else:
            if normalized == '/':
                is_root = True

        if not is_root and len(normalized) > 1 and (normalized.endswith('/') or normalized.endswith('\\')):
            normalized = normalized[:-1]

        return normalized
