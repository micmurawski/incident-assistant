import asyncio
from typing import Optional

from agent.tooling.decorators import ToolResult

MAX_OUTPUT_LENGTH = 8000


async def run_cli_command(
    cmd: list[str],
    stdin: Optional[str] = None,
    timeout: int = 30,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> ToolResult:
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

        total_length = len(stdout_decoded)
        output = stdout_decoded
        if total_length > MAX_OUTPUT_LENGTH:
            head = stdout_decoded[: MAX_OUTPUT_LENGTH // 2]
            tail = stdout_decoded[-MAX_OUTPUT_LENGTH // 2:]
            output = f"{head}\n...[trimmed {total_length - MAX_OUTPUT_LENGTH} characters]...\n{tail}"

        if error_msg and len(error_msg) > 2000:
            error_msg = error_msg[:1600] + f"\n...[trimmed {len(error_msg) - 1600} characters of stderr]..."

        return ToolResult(result=output, error=error_msg)
    except asyncio.TimeoutError:
        return ToolResult(result=None, error=f"kubectl command timed out after {timeout}s: {' '.join(cmd)}")
    except Exception as e:
        return ToolResult(result=None, error=str(e))
