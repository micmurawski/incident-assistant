"""Runs inside the Docker sandbox: persistent Python globals + HTTP POST /run."""

import contextlib
import io
import traceback

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

_globals: dict = {"__builtins__": __builtins__}


def _run_code(code: str) -> str:
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            exec(compile(code, "<sandbox>", "exec"), _globals)
    except Exception:
        buf_err.write(traceback.format_exc())
    return buf_out.getvalue() + buf_err.getvalue()


async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def run_code(request: Request) -> PlainTextResponse:
    body = await request.body()
    code = body.decode("utf-8", errors="replace")
    out = _run_code(code)
    return PlainTextResponse(out)


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/run", run_code, methods=["POST"]),
    ]
)
