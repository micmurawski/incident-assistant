"""OpenAI **Responses** API handler: streams reasoning summaries, assistant text, and tools.

Use this provider when you want human-readable **reasoning summaries** (not raw
internal reasoning tokens) from GPT-5 / o-series models. Chat Completions
(`openai_compatible`) does not surface the same content.

Tool definitions must use ``Tools.tools_definitions(format="openai_responses")`` (flat
``{"type": "function", "name", "description", "parameters"}``), which matches the
Responses API ``tools`` parameter.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from typing import Any, Coroutine, Optional

from anthropic.types.message_param import MessageParam
from openai import AsyncOpenAI, OpenAIError

from agent.providers.base import ApiHandler, ApiHandlerCreateMessageMetadata, AsyncIterator
from agent.providers.formatters.open_ai_format import convert_to_openai_messages
from agent.providers.models import OPENAI_DEFAULT_MODEL_ID, OPENAI_MODELS
from agent.providers.params import get_model_params
from agent.providers.settings import ModelInfo, OpenAISettings
from agent.repo_paths import get_repo_root
from agent.providers.utils.cost import calculate_api_cost_openai
from agent.providers.utils.error_handling import handle_open_ai_error
from agent.providers.utils.tiktoken import count_tokens
from agent.types import ReasoningChunk, StreamChunk, TextChunk, ToolUse, UsageChunk


def _normalize_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return shallow copies suitable for ``responses.create`` (flat function tools)."""
    out: list[dict[str, Any]] = []
    for raw in tools:
        t = dict(raw)
        if t.get("type") != "function":
            continue
        # Chat Completions shape: unwrap nested ``function`` if present.
        if "function" in t and isinstance(t["function"], dict):
            fn = t.pop("function")
            t.setdefault("name", fn.get("name", ""))
            t.setdefault("description", fn.get("description") or "")
            t.setdefault("parameters", fn.get("parameters") or {"type": "object", "properties": {}})
        t.setdefault("description", "")
        t.setdefault("parameters", {"type": "object", "properties": {}})
        # Default off strict mode so typical agent JSON schemas do not fail validation.
        if "strict" not in t:
            t["strict"] = False
        out.append(t)
    return out


def _openai_chat_to_responses_input(openai_msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Chat Completions-style messages to Responses ``input`` items."""
    items: list[dict[str, Any]] = []
    for m in openai_msgs:
        role = m.get("role")
        if role == "user":
            items.append({"type": "message", "role": "user", "content": m["content"]})
        elif role == "assistant":
            content = m.get("content")
            tool_calls = m.get("tool_calls")
            if isinstance(content, str) and content.strip():
                items.append({"type": "message", "role": "assistant", "content": content})
            elif isinstance(content, list) and content:
                items.append({"type": "message", "role": "assistant", "content": content})
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    items.append(
                        {
                            "type": "function_call",
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments") or "{}",
                            "call_id": tc.get("id", ""),
                        }
                    )
        elif role == "tool":
            raw = m.get("content", "")
            out = raw if isinstance(raw, str) else json.dumps(raw)
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": m.get("tool_call_id", ""),
                    "output": out,
                }
            )
    return items


def _is_rate_limit_error(error: OpenAIError) -> bool:
    """Best-effort check for OpenAI rate-limit failures."""
    text = str(error).lower()
    return "rate limit" in text or "429" in text


def _extract_retry_after_seconds(error: OpenAIError) -> float | None:
    """
    Extract retry delay from OpenAI error text, capturing both ms and s units.
    Handles OpenAI error messages such as:
      - 'try again in 527ms'
      - 'Please try again in 1.303s.'
    """
    text = str(error).lower()
    # Try for milliseconds, e.g., 'try again in 527ms'
    match_ms = re.search(r"try again in\s+(\d+)\s*ms", text)
    if match_ms:
        return max(0.0, int(match_ms.group(1)) / 1000.0)
    # Try for seconds as float, e.g., 'please try again in 1.303s'
    match_s = re.search(r"try again in\s+([0-9]*\.?[0-9]+)\s*s", text)
    if match_s:
        return max(0.0, float(match_s.group(1)))
    # Try alternative phrasing with 'please'
    match_please_s = re.search(r"please try again in\s+([0-9]*\.?[0-9]+)\s*s", text)
    if match_please_s:
        return max(0.0, float(match_please_s.group(1)))
    return None


class OpenAIResponsesHandler(ApiHandler):
    """Streams ``response.reasoning_*`` and ``response.output_text.delta`` events."""

    provider: str = "openai_responses"

    def __init__(
        self,
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.model_id = model_id
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        if not self.model_id:
            self.model_id = OPENAI_DEFAULT_MODEL_ID
        if self.model_id not in OPENAI_MODELS:
            self.model_id = OPENAI_DEFAULT_MODEL_ID
        self.options = kwargs
        self.kwargs: dict[str, Any] = dict(kwargs)
        self.client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            base_url=self.base_url,
        )

    def get_model(self) -> ModelInfo:
        is_thinking = self.model_id.endswith(":thinking") if self.model_id else False
        _model_id = (
            self.model_id.replace(":thinking", "")
            if is_thinking and self.model_id
            else self.model_id
        )
        model_id = _model_id if _model_id in OPENAI_MODELS else OPENAI_DEFAULT_MODEL_ID
        info = OPENAI_MODELS[model_id]
        params: OpenAISettings = get_model_params(
            format="openai",
            model_id=model_id,
            model=info,
            settings=self.kwargs,
        )
        data: dict[str, Any] = {"id": model_id, **info, **params}
        return ModelInfo(**data)

    async def create_message(
        self,
        system_prompt: str,
        messages: list[MessageParam],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        tools = kwargs.pop("tools", None)
        
        config = self.get_model()
        model_id = config["id"]
        openai_chat = convert_to_openai_messages(messages)
        input_items = _openai_chat_to_responses_input(openai_chat)

        reasoning_effort = kwargs.pop("reasoning_effort", config.get("reasoning_effort"))
        if reasoning_effort is None:
            reasoning_effort = config.get("reasoning_effort")
        # Responses API uses nested ``reasoning``; omit effort if unsupported / None.
        reasoning_cfg: dict[str, Any] = {}
        if reasoning_effort:
            reasoning_cfg["effort"] = reasoning_effort

        # ``auto`` / ``concise`` / ``detailed`` — opt out with reasoning_summary=None in handler options.
        summary_level = kwargs.pop(
            "reasoning_summary",
            self.options.get("reasoning_summary", "auto"),
        )
        if summary_level:
            reasoning_cfg["summary"] = summary_level

        max_out = config.get("max_tokens")
        create_kwargs: dict[str, Any] = {
            "model": model_id,
            "instructions": system_prompt or None,
            "input": input_items,
            "stream": True,
            "tools": tools,
        }
        if reasoning_cfg:
            create_kwargs["reasoning"] = reasoning_cfg
        if isinstance(max_out, int) and max_out > 0:
            create_kwargs["max_output_tokens"] = max_out

        temp = kwargs.pop("temperature", self.options.get("temperature", config.get("default_temperature")))
        if temp is not None and config.get("supports_temperature", True):
            create_kwargs["temperature"] = temp

        create_kwargs.update(kwargs)
        max_retries = 3
        base_backoff_seconds = 0.5
        last_usage: Any = None
        for attempt in range(max_retries + 1):
            # Map streaming ``item_id`` (output item) → ``call_id`` for ``tool_use`` / tool_result correlation.
            item_id_to_call_id: dict[str, str] = {}
            # Incremental function-call JSON: ``response.function_call_arguments.delta`` → buffer; finalized on ``.done``.
            fc_arg_buffers: dict[str, dict[str, str]] = {}
            saw_output_text_delta = False
            emitted_chunks = False
            try:
                stream = await self.client.responses.create(**create_kwargs)
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if item is not None and getattr(item, "type", None) == "function_call":
                            iid = getattr(item, "id", None)
                            cid = getattr(item, "call_id", None)
                            if iid is not None and cid is not None:
                                sid = str(iid)
                                item_id_to_call_id[sid] = str(cid)
                                buf = fc_arg_buffers.setdefault(sid, {"name": "", "arguments": ""})
                                iname = getattr(item, "name", None) or ""
                                if iname:
                                    buf["name"] = str(iname)
                                iargs = getattr(item, "arguments", None)
                                if isinstance(iargs, str) and iargs:
                                    buf["arguments"] = iargs
                    elif etype == "response.output_text.delta":
                        saw_output_text_delta = True
                        delta = getattr(event, "delta", None) or ""
                        if delta:
                            emitted_chunks = True
                            yield TextChunk(type="text", text=str(delta))
                    elif etype == "response.output_text.done":
                        # Some streams omit per-token text deltas and only emit the full string here.
                        full = getattr(event, "text", None) or ""
                        if full and not saw_output_text_delta:
                            emitted_chunks = True
                            yield TextChunk(type="text", text=str(full))
                    elif etype == "response.reasoning_summary_text.delta":
                        delta = getattr(event, "delta", None) or ""
                        if delta:
                            emitted_chunks = True
                            yield ReasoningChunk(type="reasoning", text=str(delta))
                    elif etype == "response.reasoning_text.delta":
                        delta = getattr(event, "delta", None) or ""
                        if delta:
                            emitted_chunks = True
                            yield ReasoningChunk(type="reasoning", text=str(delta))
                    elif etype == "response.function_call_arguments.delta":
                        iid = str(getattr(event, "item_id", "") or "")
                        if not iid:
                            continue
                        buf = fc_arg_buffers.setdefault(iid, {"name": "", "arguments": ""})
                        frag = getattr(event, "delta", None) or ""
                        buf["arguments"] += str(frag)
                    elif etype == "response.function_call_arguments.done":
                        item_id = str(getattr(event, "item_id", "") or "")
                        buf = fc_arg_buffers.pop(item_id, {"name": "", "arguments": ""})
                        name = (getattr(event, "name", None) or buf.get("name") or "").strip()
                        ev_args = getattr(event, "arguments", None)
                        if isinstance(ev_args, str) and ev_args.strip():
                            args_str = ev_args
                        else:
                            args_str = (buf.get("arguments") or "").strip() or "{}"
                        if not name:
                            continue
                        try:
                            parsed_args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            parsed_args = {"_raw_arguments": args_str}
                        call_id = item_id_to_call_id.get(item_id) or item_id or hashlib.sha256(
                            json.dumps({"name": name, "arguments": args_str}, sort_keys=True).encode()
                        ).hexdigest()
                        emitted_chunks = True
                        yield ToolUse(
                            type="tool_use",
                            id=call_id,
                            name=name,
                            input=parsed_args if isinstance(parsed_args, dict) else {"value": parsed_args},
                        )
                    elif etype == "response.completed":
                        resp = getattr(event, "response", None)
                        if resp is not None and getattr(resp, "usage", None):
                            last_usage = resp.usage
                break
            except OpenAIError as e:
                should_retry = (
                    attempt < max_retries
                    and _is_rate_limit_error(e)
                    and not emitted_chunks
                )
                if not should_retry:
                    raise handle_open_ai_error(e, "openai_responses") from e
                retry_after = _extract_retry_after_seconds(e)
                exp_backoff = base_backoff_seconds * (2 ** attempt)
                await asyncio.sleep(max(retry_after or 0.0, exp_backoff))

        if last_usage is not None:
            prompt_tokens = int(getattr(last_usage, "input_tokens", 0) or 0)
            completion_tokens = int(getattr(last_usage, "output_tokens", 0) or 0)
            cache_read_tokens = 0
            reasoning_tokens = 0
            pin = getattr(last_usage, "input_tokens_details", None)
            if pin is not None:
                cache_read_tokens = int(getattr(pin, "cached_tokens", 0) or 0)
            pout = getattr(last_usage, "output_tokens_details", None)
            if pout is not None:
                reasoning_tokens = int(getattr(pout, "reasoning_tokens", 0) or 0)
            total_cost = calculate_api_cost_openai(
                config,
                prompt_tokens,
                completion_tokens,
                0,
                cache_read_tokens,
            )
            usage_chunk: UsageChunk = {
                "type": "usage",
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "cache_read_tokens": cache_read_tokens,
                "total_cost": total_cost,
            }
            if reasoning_tokens:
                usage_chunk["reasoning_tokens"] = reasoning_tokens
            yield usage_chunk

    async def complete_prompt(self, prompt: str) -> Coroutine[Any, Any, str]:
        text_parts: list[str] = []
        async for chunk in self.create_message(
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        ):
            if chunk.get("type") == "text":
                text_parts.append(str(chunk.get("text", "")))
        return "".join(text_parts)

    async def count_tokens(self, content: list[MessageParam], tools: list[dict] | None = None) -> int:
        return await asyncio.to_thread(count_tokens, content, tools)


async def _demo() -> None:
    import sys

    key_path = get_repo_root() / "api_key.json"
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key and key_path.exists():
        api_key = json.loads(key_path.read_text()).get("openai_api_key", "")
    if not api_key:
        print("Set OPENAI_API_KEY or add openai_api_key to api_key.json at repo root.", file=sys.stderr)
        sys.exit(1)

    model_id = os.environ.get("DEMO_MODEL", "gpt-5-nano")
    handler = OpenAIResponsesHandler(model_id=model_id, api_key=api_key)
    print(f"--- OpenAIResponsesHandler demo model={model_id} ---\n")
    sys.stdout.write("[reasoning summary] ")
    sys.stdout.flush()
    async for chunk in handler.create_message(
        system_prompt="You are a concise reasoning assistant.",
        messages=[
            {
                "role": "user",
                "content": "In 2–3 sentences, why might a Kubernetes pod stay Pending?",
            }
        ],
    ):
        t = chunk.get("type")
        if t == "reasoning":
            sys.stdout.write(chunk.get("text", ""))
            sys.stdout.flush()
        elif t == "text":
            sys.stdout.write("\n[answer]\n")
            sys.stdout.write(chunk.get("text", ""))
            sys.stdout.flush()
        elif t == "usage":
            print("\n\n[usage]", json.dumps(dict(chunk), indent=2))
    print()


async def _mock_demo() -> None:
    """Offline smoke test: patches ``responses.create`` to emit synthetic stream events."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    usage = SimpleNamespace(
        input_tokens=42,
        output_tokens=17,
        input_tokens_details=SimpleNamespace(cached_tokens=3),
        output_tokens_details=SimpleNamespace(reasoning_tokens=9),
    )
    completed = SimpleNamespace(
        type="response.completed",
        response=SimpleNamespace(usage=usage),
    )

    fc_item = SimpleNamespace(
        type="function_call", id="fc_item_1", call_id="call_mock_1", name="demo_tool"
    )

    async def fake_events():
        yield SimpleNamespace(type="response.reasoning_summary_text.delta", delta="(mock summary) ")
        yield SimpleNamespace(type="response.output_text.delta", delta="(mock answer)")
        yield SimpleNamespace(type="response.output_item.added", item=fc_item)
        # Real API streams many ``function_call_arguments.delta`` chunks; ``.done`` carries the final JSON.
        yield SimpleNamespace(
            type="response.function_call_arguments.delta", item_id="fc_item_1", delta='{"x": '
        )
        yield SimpleNamespace(type="response.function_call_arguments.delta", item_id="fc_item_1", delta="1}")
        # Finalize: name/arguments may be empty on ``.done`` when they were streamed incrementally.
        yield SimpleNamespace(
            type="response.function_call_arguments.done",
            item_id="fc_item_1",
            name="",
            arguments="",
        )
        yield completed

    # ``responses.create`` is awaited and must resolve to an async-iterable of events.
    fake_create = AsyncMock(return_value=fake_events())
    handler = OpenAIResponsesHandler(model_id="gpt-5-nano", api_key="sk-mock")
    demo_tools = [
        {
            "type": "function",
            "name": "demo_tool",
            "description": "demo",
            "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
        }
    ]
    with patch.object(handler.client.responses, "create", fake_create):
        print("--- OpenAIResponsesHandler --mock (no network) ---\n")
        kinds: list[str] = []
        tool_ids: list[str] = []
        async for chunk in handler.create_message(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hello"}],
            tools=demo_tools,
        ):
            kinds.append(str(chunk.get("type")))
            if chunk.get("type") == "tool_use":
                tool_ids.append(str(chunk.get("id", "")))
        print("chunk types:", kinds)
        assert "tool_use" in kinds
        assert tool_ids == ["call_mock_1"]
        fake_create.assert_awaited_once()
        _, kwargs = fake_create.await_args
        assert kwargs.get("stream") is True
        assert kwargs.get("reasoning", {}).get("summary") == "auto"
        assert kwargs.get("tools") and kwargs["tools"][0]["name"] == "demo_tool"
        print("mock assertions: ok")


if __name__ == "__main__":
    import sys

    if "--mock" in sys.argv:
        asyncio.run(_mock_demo())
    else:
        asyncio.run(_demo())
