import asyncio
import os
import sys
from collections import deque
from typing import Optional

from agent.tooling.decorators import ToolResult


async def run_cli_command(
    cmd: list[str],
    stdin: Optional[str] = None,
    timeout: int = 30,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
    stream: bool = False,
    tail_lines: int = 5,
) -> ToolResult:
    if cwd is None or (isinstance(cwd, str) and cwd.strip() == ""):
        cwd = os.getcwd()
    env = {**os.environ.copy(), **(env or {})}
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if stream else asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )

        if stdin is not None:
            process.stdin.write(stdin.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

        if stream:
            print("Running command: ", " ".join(cmd),  "...")
            lines_buffer = deque(maxlen=tail_lines)
            lines_printed = 0
            full_output = []

            try:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    
                    decoded_line = line.decode("utf-8")
                    full_output.append(decoded_line)
                    
                    # Real-time display logic
                    display_line = decoded_line.strip()
                    lines_buffer.append(display_line)
                    
                    if lines_printed > 0:
                        # Move cursor up by the number of lines previously printed
                        sys.stdout.write(f"\033[{lines_printed}A")
                    
                    for l in lines_buffer:
                        # Clear line then print
                        sys.stdout.write(f"\r\033[K{l}\n")
                    
                    sys.stdout.flush()
                    lines_printed = len(lines_buffer)
                
                await process.wait()
            except Exception as e:
                if process.returncode is None:
                    process.terminate()
                return ToolResult(result=None, error=f"Streaming interrupted: {str(e)}")

            stdout_decoded = "".join(full_output)
            error_msg = None if process.returncode == 0 else f"Process exited with code {process.returncode}"
            return ToolResult(result=stdout_decoded, error=error_msg)
        else:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            stdout_decoded = stdout.decode("utf-8")
            stderr_decoded = stderr.decode("utf-8")
            error_msg = stderr_decoded if process.returncode != 0 else None

            return ToolResult(result=stdout_decoded, error=error_msg)

    except asyncio.TimeoutError:
        return ToolResult(result=None, error=f"Command timed out after {timeout}s: {' '.join(cmd)}")
    except Exception as e:
        return ToolResult(result=None, error=str(e))
