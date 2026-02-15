import asyncio
import json
import os
# NOTE: Do NOT use anthropic.types.ToolUseBlockParam here.
# When messages round-trip through the @node decorator's Pydantic model
# (input_model(**prep_res).model_dump()), Anthropic TypedDicts cause the
# content list to be wrapped in a SerializationIterator — a one-shot
# iterator that gets consumed on first access (e.g. debug printing) and
# is then empty for the Gemini message converter. Use plain dicts instead.
from typing import Any, AsyncIterator, List, Optional, TypeVar
from uuid import uuid4

from agent.context import Context
from agent.persistence.model import MemoryService
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools, CodebaseWriteTools
from agent.tooling.decorators import Tools
from agent.types import (AnthropicMessage, ApiHandlerCreateMessageMetadata,
                         StreamChunk)
from framework import AsyncFlow
from framework.decorators import node
from framework.decorators import noop_async as end

T = TypeVar('T')


def pr_red(s: str, *args: Any, **kwargs: Any): print("\033[91m{}\033[0m".format(s), *args, **kwargs)
def pr_green(s: str, *args: Any, **kwargs: Any): print("\033[92m{}\033[0m".format(s), *args, **kwargs)
def pr_yellow(s: str, *args: Any, **kwargs: Any): print("\033[93m{}\033[0m".format(s), *args, **kwargs)
def pr_light_purple(s: str, *args: Any, **kwargs: Any): print("\033[94m{}\033[0m".format(s), *args, **kwargs)
def pr_purple(s: str, *args: Any, **kwargs: Any): print("\033[95m{}\033[0m".format(s), *args, **kwargs)
def pr_cyan(s: str, *args: Any, **kwargs: Any): print("\033[96m{}\033[0m".format(s), *args, **kwargs)
def pr_light_gray(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)  # dim
def pr_black(s: str, *args: Any, **kwargs: Any): print("\033[90m{}\033[0m".format(s), *args, **kwargs)


class ChunkProxyIterator:
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
        memory_service: MemoryService | None = None,
    ):
        self.iterator = iterator
        self.id = id
        self.reasoning = ""
        self.text = ""
        self.usage = None
        self.tool_use = []
        self.agent_id = agent_id
        self.session_id = session_id
        self.task_id = task_id
        self.conversation_id = conversation_id
        self.conversation_version = conversation_version
        self.memory_service = memory_service
        
        
    async def _process_chunk(self, chunk: StreamChunk) -> None:
        _type = chunk.get("type")
        match _type:
            case "text":
                print(chunk.get("text", ""), end="", flush=True)
                self.text += chunk.get("text", "")
            case "reasoning":
                pr_light_gray(chunk.get("text", ""), end="", flush=True)
                self.reasoning += chunk.get("text", "")
            case "text":
                print(chunk.get("text", ""), end="", flush=True)
                self.text += chunk.get("text", "")
            case "usage":
                print()
                pr_yellow(json.dumps(chunk), flush=True)
                self.usage = chunk
            case "tool_use":
                function_name = chunk["name"]
                function_input = chunk["input"]
                _input_str = ", ".join([f"{k}={v}" for k, v in function_input.items()])
                text = f"{function_name}({_input_str})"
                pr_light_purple(f"calling: {text}", end="", flush=True)
                self.tool_use.append(chunk)
            case _:
                raise ValueError(f"Unknown chunk type: {_type}")


    def get_response(self) -> List[AnthropicMessage]:
        result = []
        if self.text:
            result.append({"role": "assistant", "content": self.text})
        if self.reasoning:
            result.append({"role": "assistant", "content": self.reasoning})
        if self.usage:
            result.append({"role": "assistant", "content": self.usage})
        if self.tool_use:
            result.append({"role": "assistant", "content": self.tool_use})
        return result
    
    def had_tool_use(self) -> bool:
        return bool(self.tool_use)
    
    async def __aiter__(self):
        chunk: StreamChunk
        async for chunk in self.iterator:
            await self._process_chunk(chunk)
            yield chunk

        if True: # no recording output
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

class Agent:
    def __init__(self, name: str, tools: Tools, system_prompt: str, memory_service: MemoryService | None = None):
        self.name = name
        self.context = Context()
        self.tools = tools
        self.system_prompt = system_prompt
        self.tool_format_arguments = {
            "cwd": self.context.cwd
        }
        self._tools_definitions = self.tools.tools_definitions(
            format=self.context.api_handler.provider,
            format_kwargs=self.tool_format_arguments
        )
        self.memory_service = memory_service
        if self.memory_service:
            self.memory_service.upsert_agent(
                id=self.name,
                name=self.name,
                description=self.system_prompt
            )
        
        self._call_llm - "tools" >> self.tools
        self._call_llm - "default" >> end
        self._call_llm - "end" >> end
        self.tools >> self._call_llm
        self.flow = AsyncFlow(start=self._call_llm)
    
    @node
    async def _call_llm(self, messages: List[AnthropicMessage], metadata: Optional[ApiHandlerCreateMessageMetadata] = None, **kwargs: dict[str, Any]) -> tuple[dict[str, list[AnthropicMessage]], str]:
        kwargs = {**kwargs.pop("kwargs", {}), **kwargs}
        iter: ChunkProxyIterator = await self.create_message(
            messages=messages,
            metadata=metadata,
            **kwargs
        )
        
        async for _ in iter:
            pass

        data = {"messages": list(messages) + iter.get_response()}
        _next = "tools" if iter.had_tool_use() else "default"
        return data, _next

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
        
        _iterator = self.context.api_handler.create_message(
            system_prompt=self.system_prompt,
            messages=messages,
            metadata=metadata,
            tools=self._tools_definitions,
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
            memory_service=self.memory_service
        )
    

async def main():
    settings = SettingsManager.get_instance()
    memory_service = MemoryService()
    tools = CodebaseReadTools | CodebaseWriteTools
    settings.get("workspace.path") or os.getcwd()
    settings.set("api.provider", "gemini")
    settings.set("api.model_id", "gemini-2.5-flash:thinking")
    settings.set("api.api_key", "AIzaSyAmNJmXdpejo2LQWDowsqsK3bvMhZSXfII")
    
    #settings.set("api.provider", "anthropic")
    #settings.set("api.model_id", "claude-sonnet-4-5:thinking")
    #settings.set("api.api_key", "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")
    
    agent = Agent(
        name="testing_agent",
        tools=tools,
        system_prompt="You are a helpful assistant.",
        memory_service=memory_service
    )
    # Shared must contain "messages" (no default in _call_llm); add any initial user message here.
    # Tools with Hidden[Context] params require shared["context"] to be set (injected by framework).
    shared = {
        "messages": [{"role": "user", "content": "Hello, can you list files in the current directory?"}],
        "context": agent.context,
    }
    await agent.flow.run_async(shared)

if __name__ == "__main__":
    asyncio.run(main())
