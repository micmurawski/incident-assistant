import json
import random
from abc import ABC
from typing import Any, AsyncIterator, List, Optional, TypeVar
from uuid import uuid4

from framework import AsyncFlow
from framework.decorators import node
from agent.tooling.decorators import Tools
from framework.viz import build_mermaid, to_png

from agent.context_ops import SummarizeResponse, summarize_conversation
from agent.providers.base import ApiHandler
from agent.types import (AnthropicMessage, ApiHandlerCreateMessageMetadata,
                         StreamChunk)
from openinference.instrumentation import Tool

T = TypeVar('T')


def pr_red(s: str, *args: Any, **kwargs: Any): print("\033[91m{}\033[0m".format(s), *args, **kwargs)
def pr_green(s: str, *args: Any, **kwargs: Any): print("\033[92m{}\033[0m".format(s), *args, **kwargs)
def pr_yellow(s: str, *args: Any, **kwargs: Any): print("\033[93m{}\033[0m".format(s), *args, **kwargs)
def pr_light_purple(s: str, *args: Any, **kwargs: Any): print("\033[94m{}\033[0m".format(s), *args, **kwargs)
def pr_purple(s: str, *args: Any, **kwargs: Any): print("\033[95m{}\033[0m".format(s), *args, **kwargs)
def pr_cyan(s: str, *args: Any, **kwargs: Any): print("\033[96m{}\033[0m".format(s), *args, **kwargs)
def pr_light_gray(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)  # dim
def pr_black(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)


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


def _to_plain(obj: Any) -> Any:
    """Recursively convert a Pydantic model / iterator / typed-dict to a plain dict/list."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        return _to_plain(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(item) for item in obj]
    try:
        return [_to_plain(item) for item in obj]
    except Exception:
        return str(obj)


def _materialize_messages(messages: list) -> list[dict]:
    """
    Deep-materialize message content from Pydantic's SerializationIterator
    and model objects. Ensures every message is a plain dict with content
    that is either a str or a list of plain dicts (valid content blocks).
    Drops messages whose content is not valid conversation content (e.g.
    usage metadata dicts).
    """
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            m = dict(msg)
        else:
            m = {"role": getattr(msg, "role", "user"), "content": getattr(msg, "content", "")}
        content = m.get("content")
        if content is None or isinstance(content, str):
            result.append(m)
            continue
        if isinstance(content, dict) and content.get("type") == "usage":
            continue
        m["content"] = _to_plain(content)
        result.append(m)
    return result


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
                print(chunk.get("text", ""), end="", flush=True)
                self.text += chunk.get("text", "")
            case "reasoning":
                pr_light_gray(chunk.get("text", ""), end="", flush=True)
                self.reasoning += chunk.get("text", "")
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
                pr_light_purple(f"calling: {text}", end="", flush=True)
                self.tool_use.append(chunk)
            case "grounding":
                sources = chunk.get("sources", [])
                if sources:
                    pr_cyan(f"grounding: {json.dumps(sources)}", flush=True)

    def get_response(self) -> List[AnthropicMessage]:
        result = []
        if self.tool_use:
            content_blocks = []
            if self.text:
                content_blocks.append({"type": "text", "text": self.text})
            for tu in self.tool_use:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tu["id"],
                    "name": tu["name"],
                    "input": tu["input"],
                })
            result.append({"role": "assistant", "content": content_blocks})
        elif self.text:
            result.append({"role": "assistant", "content": self.text})
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

    def __repr__(self):
        return f"LLMAgent(name={self.name})"

    async def call(self, shared: dict[str, Any]):
        if self.flow is None:
            raise ValueError("Flow is not bound")
        shared["agent"] = self
        return await self.flow.run_async(shared)

    @node
    async def call_llm(
        self,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        worktree_path: Optional[str] = None,
        cwd: Optional[str] = None,
        **kwargs: dict[str, Any],
    ) -> tuple[dict[str, list[AnthropicMessage]], str]:
        kwargs = {**kwargs.pop("kwargs", {}), **kwargs}
        # Materialize messages to consume any one-shot SerializationIterators
        # injected by Pydantic's model_dump() in the @node decorator pipeline.
        messages = _materialize_messages(messages)

        iter: ChunkProxyIterator = await self.create_message(
            messages=messages,
            metadata=metadata,
            **kwargs
        )

        async for _ in iter:
            pass

        data = {"messages": messages + iter.get_response()}
        if iter.usage_summary:
            data["_last_usage"] = iter.usage_summary
        _next = "tools" if iter.had_tool_use() else "default"
        return data, _next

    @node
    async def summarize_context(
        self,
        messages: List[AnthropicMessage],
    ) -> List[AnthropicMessage]:

        total_tokens = await self.api_handler.count_tokens(messages)
        model_info = await self.api_handler.get_model()
        if model_info["max_tokens"] >= total_tokens:
            result: SummarizeResponse = await summarize_conversation(
                messages=messages,
                api_handler=self.api_handler,
                system_prompt=self.system_prompt,
                prev_context_tokens=total_tokens,
            )
            if result.error:
                pr_red(f"Error summarizing context: {result.error}", flush=True)
            else:
                return {"messages": result.messages}
        return {"messages": messages}, "default"

    def bind_tools(self, tools: Tools, tool_format_arguments: dict[str, Any] = None):
        self.tools_arguments = tool_format_arguments
        self.tools_definitions = tools.tools_definitions(
            format=self.api_handler.provider,
            format_kwargs=self.tools_arguments
        )

    def update_tools_definitions(self, tools: Tools | None = None, tool_format_arguments: dict[str, Any] = None):
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

        _iterator = self.api_handler.create_message(
            system_prompt=kwargs.pop("system_prompt", self.system_prompt),
            messages=messages,
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
