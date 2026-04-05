"""Runs inside the Docker sandbox: persistent Python globals + HTTP POST /run."""

import asyncio
import contextlib
import html
import io
import traceback
from typing import List

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

_globals: dict = {"__builtins__": __builtins__}

# Mirrors host-side ContainerRLMSandbox.history shape: {"action", "content"}.
_history: List[dict[str, str]] = []
_history_lock = asyncio.Lock()
_MAX_HISTORY_ENTRIES = 2000


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
    async with _history_lock:
        _history.append({"action": "CODE_INPUT", "content": code})
        _history.append({"action": "CODE_OUTPUT", "content": out})
        overflow = len(_history) - _MAX_HISTORY_ENTRIES
        if overflow > 0:
            del _history[:overflow]
    return PlainTextResponse(out)


async def get_history(_: Request) -> JSONResponse:
    async with _history_lock:
        snap = list(_history)
    return JSONResponse(snap)


async def reset_history(_: Request) -> JSONResponse:
    async with _history_lock:
        _history.clear()
    return JSONResponse({"status": "ok"})


async def view_history_ui(_: Request) -> HTMLResponse:
    async with _history_lock:
        entries = list(_history)
    parts = [
        "<html><body style='font-family: monospace; max-width: 800px; margin: auto; "
        "padding: 20px; background: #1e1e1e; color: #d4d4d4;'>",
        "<h2 style='color: #569cd6;'>Sandbox execution history</h2>",
        "<p><a href='/history' style='color:#4fc1ff;'>JSON</a></p>",
        "<hr style='border-color: #333;'>",
    ]
    for entry in entries:
        action = entry["action"]
        content = html.escape(entry["content"])
        if action == "CODE_INPUT":
            bg, title_col = "#2d2d2d", "#ce9178"
        elif action == "CODE_OUTPUT":
            bg, title_col = "#1e1e1e", "#4af626"
        elif action == "SYSTEM":
            bg, title_col = "#004080", "#4fc1ff"
        else:
            bg, title_col = "#4d0000", "#f44336"
        parts.append(
            f"<div style='background: {bg}; padding: 10px; margin-bottom: 10px; "
            f"border-left: 4px solid {title_col};'>"
        )
        parts.append(f"<strong style='color: {title_col};'>{html.escape(action)}:</strong>")
        parts.append(f"<pre style='white-space: pre-wrap; margin-top: 5px;'>{content}</pre>")
        parts.append("</div>")
    parts.append("</body></html>")
    return HTMLResponse("".join(parts))


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/run", run_code, methods=["POST"]),
        Route("/history", get_history, methods=["GET"]),
        Route("/history", reset_history, methods=["POST"]),
        Route("/ui/history", view_history_ui, methods=["GET"]),
    ]
)
