import json
import os
import random
from abc import ABC
from typing import Any, AsyncIterator, List, Optional, TypeVar
from uuid import uuid4

from agent.context_ops import SummarizeResponse, summarize_conversation
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tracing import trace_flow
from agent.types import (AnthropicMessage, ApiHandlerCreateMessageMetadata,
                         StreamChunk)
from framework import AsyncFlow
from framework.decorators import end, node
from framework.viz import build_mermaid, to_png

T = TypeVar('T')


def pr_red(s: str, *args: Any, **kwargs: Any): print("\033[91m{}\033[0m".format(s), *args, **kwargs)
def pr_green(s: str, *args: Any, **kwargs: Any): print("\033[92m{}\033[0m".format(s), *args, **kwargs)
def pr_yellow(s: str, *args: Any, **kwargs: Any): print("\033[93m{}\033[0m".format(s), *args, **kwargs)
def pr_light_purple(s: str, *args: Any, **kwargs: Any): print("\033[94m{}\033[0m".format(s), *args, **kwargs)
def pr_purple(s: str, *args: Any, **kwargs: Any): print("\033[95m{}\033[0m".format(s), *args, **kwargs)
def pr_cyan(s: str, *args: Any, **kwargs: Any): print("\033[96m{}\033[0m".format(s), *args, **kwargs)
def pr_light_gray(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)  # dim
def pr_black(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)


def _debug_llm_enabled() -> bool:
    return os.environ.get("DEBUG_LLM", "").lower() in ("1", "true", "yes")


def _debug_llm(msg: str) -> None:
    if _debug_llm_enabled():
        pr_cyan(f"[call_llm] {msg}", flush=True)


adjectives = [
    "thinking",
    "reflecting",
    "ruminating",
    "pondering",
    "concluding",
    "contemplating",
    "considering",
    "evaluating",
    "deciding",
    "discombobulating",
]


def _sanitize_message_content(content: Any) -> Any | None:
    """Best-effort normalize Anthropic message content to supported shapes."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return {k: v for k, v in content.items()}
    if not isinstance(content, list):
        try:
            content = list(content)
        except TypeError:
            return None
    sanitized_blocks: list[dict[str, Any]] = []
    for block in content:
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if not isinstance(block_type, str):
            continue
        sanitized_blocks.append(dict(block))
    # Empty list content is invalid/no-op for Anthropic-style chat turns.
    return sanitized_blocks or None


def _sanitize_messages_for_provider(messages: List[AnthropicMessage]) -> List[AnthropicMessage]:
    """Drop malformed messages/contents so provider payloads stay serializable."""
    sanitized: list[AnthropicMessage] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = _sanitize_message_content(msg.get("content"))
        if content is None:
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized


class ChunkProxyIterator[T]:
    """Wrapper for async iterator that saves chunks to database before yielding."""

    def __init__(
        self,
        iterator: AsyncIterator[T],
        id: str,
        agent_id: str,
        session_id: str,
        task_id: str,
        conversation_id: str,
        conversation_version: int,
    ):
        self.iterator = iterator
        self.id = id
        self.reasoning = ""
        self.text = ""
        self.usage = None
        self.usage_summary: dict = {}
        self.tool_use = []
        self.agent_id = agent_id
        self.session_id = session_id
        self.task_id = task_id
        self.conversation_id = conversation_id
        self.conversation_version = conversation_version

    async def _process_chunk(self, chunk: StreamChunk) -> None:
        _type = chunk.get("type")
        match _type:
            case "text":
                piece = chunk.get("text") if chunk.get("text") is not None else chunk.get("content", "")
                piece = piece if isinstance(piece, str) else str(piece or "")
                print(piece, end="", flush=True)
                self.text += piece
            case "reasoning":
                piece = chunk.get("text") if chunk.get("text") is not None else chunk.get("content", "")
                piece = piece if isinstance(piece, str) else str(piece or "")
                pr_light_gray(piece, end="", flush=True)
                self.reasoning += piece
            case "usage":
                print()
                pr_yellow(json.dumps(chunk), flush=True)
                self.usage = chunk
                for key in ("input_tokens", "output_tokens", "cache_write_tokens",
                            "cache_read_tokens", "reasoning_tokens", "total_cost"):
                    val = chunk.get(key)
                    if val:
                        self.usage_summary[key] = self.usage_summary.get(key, 0) + val
            case "tool_use":
                function_name = chunk["name"]
                function_input = chunk["input"]
                _input_str = ", ".join([f"{k}={v}" for k, v in function_input.items()])
                text = f"{function_name}({_input_str})"
                pr_light_purple(f"calling: {text}", end="\n", flush=True)
                self.tool_use.append(chunk)
            case "grounding":
                sources = chunk.get("sources", [])
                if sources:
                    pr_cyan(f"grounding: {json.dumps(sources)}", flush=True)

    def get_response(self, include_reasoning: bool = False) -> List[AnthropicMessage]:
        result = []
        content_blocks = []
        if include_reasoning and self.reasoning:
            content_blocks.append({"type": "reasoning", "text": self.reasoning})
        if self.text:
            content_blocks.append({"type": "text", "text": self.text})
        if self.tool_use:
            for tu in self.tool_use:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tu["id"],
                    "name": tu["name"],
                    "input": tu["input"],
                })

        if content_blocks:
            # If there's only one block and it's text, return it as simple string (standard)
            # unless reasoning is included, which always requires array format.
            if len(content_blocks) == 1 and content_blocks[0]["type"] == "text":
                result.append({"role": "assistant", "content": self.text})
            else:
                result.append({"role": "assistant", "content": content_blocks})
        return result

    def had_tool_use(self) -> bool:
        return bool(self.tool_use)

    async def __aiter__(self):
        chunk: StreamChunk
        last_chunk_type = None
        async for chunk in self.iterator:
            if last_chunk_type != chunk.get("type"):
                print()
                pr_red(self.agent_id + " is " + random.choice(adjectives), flush=True)
                last_chunk_type = chunk.get("type")
            await self._process_chunk(chunk)
            yield chunk

        if True:  # no recording output
            return

        if self.text:
            self.memory_service.save_message(
                id=self.id,
                role="assistant",
                type="text",
                content=self.text,
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=self.task_id,
                conversation_id=self.conversation_id,
                conversation_version=self.conversation_version
            )
        if self.reasoning:
            self.memory_service.save_message(
                message={
                    "id": self.id,
                    "role": "assistant",
                    "type": "reasoning",
                    "content": self.reasoning
                },
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=self.task_id,
                conversation_id=self.conversation_id,
                conversation_version=self.conversation_version
            )
        if self.usage:
            self.memory_service.save_message(
                message={
                    "id": self.id,
                    "role": "assistant",
                    "type": "usage",
                    "content": json.dumps(self.usage)
                },
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=self.task_id,
                conversation_id=self.conversation_id,
                conversation_version=self.conversation_version
            )
        for tool_use in self.tool_use:
            self.memory_service.save_message(
                message={
                    "id": self.id,
                    "role": "assistant",
                    "type": "tool_use",
                    "content": json.dumps(tool_use)
                },
                session_id=self.session_id,
                agent_id=self.agent_id,
                task_id=self.task_id,
                conversation_id=self.conversation_id,
                conversation_version=self.conversation_version
            )


class LLMAgent(ABC):
    api_handler: ApiHandler
    system_prompt: str
    name: str
    flow: AsyncFlow | None = None
    tools_arguments: dict[str, Any] = {}
    tools: list[dict] | None = None
    cwd: str | None = None
    shared_context: dict[str, Any] | None = None

    def __init__(
        self,
        name: str,
        system_prompt: str,
        api_settings: dict[str, Any] | None = None,
        tools: Any | None = None,
        shared_context: dict[str, Any] | None = None,
        disable_tracing: bool = False,
    ):
        # construct the agent
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.name = name

        if shared_context is None:
            shared_context = shared_context or {}

        if not disable_tracing:
            @trace_flow(f"agent-{name}-flow")
            class _TracedFlow(AsyncFlow):
                def __init__(self, start):
                    super().__init__(start=start)
            self.flow = _TracedFlow(start=self.call_llm)
        else:
            self.flow = AsyncFlow(start=self.call_llm)

        self.shared_context = shared_context
        # create re-act agent with summarization
        self.bind_tools(tools, self.get_shared())
        self.call_llm - "tools" >> tools
        self.call_llm - "default" >> end
        tools >> self.check_context_size
        self.check_context_size - "summarize" >> self.summarize_context
        self.check_context_size - "default" >> self.call_llm
        self.summarize_context >> self.call_llm

    def __repr__(self):
        return f"LLMAgent(name={self.name})"

    def get_shared(self) -> dict[str, Any]:
        res = {
            "agent": self,
            **self.shared_context,
        }
        if self.tools:
            # summarize_context expects list[dict] (tool definitions for token counting), not the Tools instance
            res["tools"] = self.tools_definitions
        return res

    async def call(self, shared: dict[str, Any]):
        if self.flow is None:
            raise ValueError("Flow is not bound")
        # Flow runs on a merged dict; node post() updates that dict only, so we must copy
        # results back into the caller's `shared` (same dict the executor holds).
        merged = {**shared, **self.get_shared()}
        result = await self.flow.run_async(merged)
        shared.update(merged)
        return result

    async def _complete_llm_turn(
        self,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata],
        task: Task | None,
        call_kwargs: dict[str, Any],
        *,
        forced_next: str | None = None,
        log_label: str = "turn",
    ) -> tuple[dict[str, list[AnthropicMessage]], str]:
        """Stream one model completion, merge assistant output into messages, update history."""
        it: ChunkProxyIterator = await self.create_message(
            messages=messages,
            metadata=metadata,
            **call_kwargs,
        )
        async for _ in it:
            pass

        if task:
            task.messages_history.extend(it.get_response(include_reasoning=True))
            task.tool_usage.extend(it.tool_use)
            if it.usage_summary:
                for k, v in it.usage_summary.items():
                    task.usage[k] = task.usage.get(k, 0) + v

        data: dict[str, Any] = {"messages": messages}
        response = it.get_response()
        if task:
            _debug_llm(
                f"{log_label} task={task.id} iterations_count={task.iterations_count}: "
                f"text_len={len(it.text)} had_tool_use={it.had_tool_use()} "
                f"response_blocks={len(response) if response else 0}"
            )
        if response:
            data["messages"] = data["messages"] + response
        if it.usage_summary:
            data["_last_usage"] = it.usage_summary

        if forced_next is not None:
            return data, forced_next
        _next = "tools" if it.had_tool_use() else "default"
        return data, _next

    @node
    async def call_llm(
        self,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        task: Task | None = None,
        **kwargs: dict[str, Any],
    ) -> tuple[dict[str, list[AnthropicMessage]], str]:
        kwargs = {**kwargs.pop("kwargs", {}), **kwargs}

        if task:
            task.iterations_count += 1
            _debug_llm(
                f"task={task.id} iterations_count={task.iterations_count}/"
                f"{task.iterations_limit} (before branch)"
            )

            if task.iterations_count > task.iterations_limit:
                _debug_llm(
                    f"hard stop: count > limit; skipping API (messages_len={len(messages)})"
                )
                print(
                    f"\033[91mIteration hard stop for task {task.id} "
                    f"(>{task.iterations_limit}).\033[0m"
                )
                terminal = {
                    "role": "assistant",
                    "content": "[Iteration limit already handled; no further model turn for this task.]",
                }
                return {"messages": messages + [terminal]}, "default"

            if task.iterations_count >= task.iterations_limit:
                print(
                    f"\033[91mIteration limit reached for task {task.id}. "
                    f"Generating final response (no tools).\033[0m"
                )
                _debug_llm(
                    f"final wrap-up: messages_len={len(messages)}, create_message with tools=[]"
                )
                messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            "Iteration limit reached. Do not use any tools. "
                            "Reply with your final summary and findings in plain text only."
                        ),
                    }
                ]
                return await self._complete_llm_turn(
                    messages,
                    metadata,
                    task,
                    {**kwargs, "tools": []},
                    forced_next="default",
                    log_label="final",
                )
            if task.iterations_count == task.iterations_limit - 3:
                messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            "WARNING: You are approaching the iteration limit for this task. "
                            f"You have {task.iterations_limit - task.iterations_count} turns left before the limit is reached. "
                            "Use your tools wisely."
                        ),
                    }
                ]
            elif task.iterations_count == task.iterations_limit - 1:
                messages = messages + [
                    {
                        "role": "user",
                        "content": (
                            "WARNING: You have reached the iteration limit for this task. "
                            "This is your LAST turn. Do not use any more tools. "
                            "Summarize your findings and report back with your final answer now."
                        ),
                    }
                ]
                print(f"\033[93mIteration limit warning sent to agent for task {task.id}.\033[0m")
                _debug_llm(
                    f"penultimate turn: appended WARNING, messages_len={len(messages)}"
                )

        return await self._complete_llm_turn(messages, metadata, task, kwargs)

    @node
    async def check_context_size(self, messages: List[AnthropicMessage], tools: list[dict] | None = None) -> bool:
        total_tokens = await self.api_handler.count_tokens(messages, tools)
        max_tokens = self.api_handler.get_model()["max_tokens"]
        print(f"\033[92mtotal_tokens: {total_tokens}\033[0m")
        print(f"\033[92mPercentage of max tokens: {total_tokens / max_tokens * 100}%\033[0m")
        if max_tokens <= total_tokens:
            return {"total_tokens": total_tokens}, "summarize"
        return {"total_tokens": total_tokens}, "default"

    @node
    async def summarize_context(
        self,
        total_tokens: int,
        messages: List[AnthropicMessage]
    ) -> tuple[dict[str, Any], str]:
        result: SummarizeResponse = await summarize_conversation(
            messages=messages,
            api_handler=self.api_handler,
            system_prompt=self.system_prompt,
            prev_context_tokens=total_tokens,
        )
        if result.get("error"):
            pr_red(f"Error summarizing context: {result['error']}", flush=True)
            return {"messages": messages}, "default"
        return {"messages": result["messages"]}, "default"

    def bind_tools(self, tools: Any, tool_format_arguments: dict[str, Any] = None):
        self.tools_arguments = tool_format_arguments
        self.tools = tools
        self.tools_definitions = self.tools.tools_definitions(
            format=self.api_handler.provider,
            format_kwargs=self.tools_arguments
        )

    def update_tools_definitions(self, tools: Any = None, tool_format_arguments: dict[str, Any] = None):
        if tool_format_arguments is not None:
            self.tools_arguments.update(tool_format_arguments)

        if tools is not None:
            self.tools = tools

        self.tools_definitions = self.tools.tools_definitions(
            format=self.api_handler.provider,
            format_kwargs=self.tools_arguments
        )

    def get_flow_graph(self):
        return build_mermaid(self.flow)

    def get_flow_graph_png(self, filename: str):
        return to_png(self.flow, filename)

    def register(self):
        AgentRegistry.get_instance().register(self)

    async def create_message(
        self,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:

        _id = kwargs.pop("id", str(uuid4()))
        conversation_id = kwargs.pop("conversation_id", None)
        conversation_version = kwargs.pop("conversation_version", 1)
        task_id = kwargs.pop("task_id", None)
        session_id = kwargs.pop("session_id", None)

        safe_messages = _sanitize_messages_for_provider(messages)
        if not safe_messages:
            safe_messages = [
                {
                    "role": "user",
                    "content": "(No valid messages in context; judge or respond using the system prompt only.)",
                }
            ]
            _debug_llm("create_message: empty after sanitize → placeholder user message")

        _iterator = self.api_handler.create_message(
            system_prompt=kwargs.pop("system_prompt", self.system_prompt),
            messages=safe_messages,
            metadata=metadata,
            tools=kwargs.pop("tools", self.tools_definitions),
            **kwargs
        )

        return ChunkProxyIterator(
            _iterator,
            id=_id,
            agent_id=self.name,
            session_id=session_id,
            task_id=task_id,
            conversation_id=conversation_id,
            conversation_version=conversation_version,
        )


class AgentRegistry(dict[str, LLMAgent]):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.agents = {}

    def register(self, agent: LLMAgent):
        self.agents[agent.name] = agent

    def get(self, name: str) -> LLMAgent:
        return self.agents[name]

    def available_agents(self) -> list[str]:
        return list(self.agents.keys())

    def available_agents_str(self) -> str:
        return ",".join(self.available_agents())
