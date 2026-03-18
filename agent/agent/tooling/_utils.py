import asyncio
import os
from typing import Optional

from agent.tooling.decorators import ToolResult


async def run_cli_command(
    cmd: list[str],
    stdin: Optional[str] = None,
    timeout: int = 30,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> ToolResult:
    if cwd is None or (isinstance(cwd, str) and cwd.strip() == ""):
        cwd = os.getcwd()
    env = {**os.environ.copy(), **(env or {})}
    try:
        if stdin is not None:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=stdin.encode("utf-8")), timeout=timeout
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        stdout_decoded = stdout.decode("utf-8")
        stderr_decoded = stderr.decode("utf-8")
        error_msg = stderr_decoded if process.returncode != 0 else None

        return ToolResult(result=stdout_decoded, error=error_msg)
    except asyncio.TimeoutError:
        return ToolResult(result=None, error=f"kubectl command timed out after {timeout}s: {' '.join(cmd)}")
    except Exception as e:
        return ToolResult(result=None, error=str(e))
