import subprocess
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class CommandOpsResult:
    status: Literal["success", "error"] = field(default="success")
    return_code: int = field(default=0)
    error: Optional[Exception] = field(default=None)
    reason: Optional[str] = field(default=None)
    output: str
    error: str
    return_code: int


def execute_command(command: str, args: list[str], cwd: str = None) -> CommandOpsResult:
    process = subprocess.Popen(
        command,
        args=args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    return CommandOpsResult(
        status="success",
        return_code=process.returncode,
        output=stdout.decode('utf-8'),
        error=stderr.decode('utf-8'),
    )
