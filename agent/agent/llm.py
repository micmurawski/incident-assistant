import json
import random
from abc import ABC
from typing import Any, AsyncIterator, List, Optional, TypeVar
from uuid import uuid4

from agent.context_ops import SummarizeResponse, summarize_conversation
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tracing import trace_flow
from agent.types import (AnthropicMessage, ApiHandlerCreateMessageMetadata,
                         StreamChunk)
from framework import AsyncFlow
from framework.decorators import node
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
        tools >> self.summarize_context
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
        # override shared with self.get_shared()
        shared = {**shared, **self.get_shared()}
        return await self.flow.run_async(shared)

    @node
    async def call_llm(
        self,
        messages: List[AnthropicMessage],
        metadata: Optional[ApiHandlerCreateMessageMetadata] = None,
        **kwargs: dict[str, Any],
    ) -> tuple[dict[str, list[AnthropicMessage]], str]:
        kwargs = {**kwargs.pop("kwargs", {}), **kwargs}

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
        tools: list[dict] | None = None,
    ) -> List[AnthropicMessage]:
        total_tokens = await self.api_handler.count_tokens(messages, tools)
        model_info = self.api_handler.get_model()
        print(f"\033[92mtotal_tokens: {total_tokens}\033[0m")
        print(f"\033[92mPercentage of max tokens: {total_tokens / model_info['max_tokens'] * 100}%\033[0m")
        if model_info["max_tokens"] <= total_tokens:
            result: SummarizeResponse = await summarize_conversation(
                messages=messages,
                api_handler=self.api_handler,
                system_prompt=self.system_prompt,
                prev_context_tokens=total_tokens,
            )
            if result.get("error"):
                pr_red(f"Error summarizing context: {result['error']}", flush=True)
            else:
                return {"messages": result["messages"]}
        return {"messages": messages}, "default"

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
