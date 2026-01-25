import asyncio
import os
from typing import Any, AsyncIterator, List, Optional

from agent.context import Context
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools
from agent.tooling.decorators import Tools
from agent.types import (AnthropicMessage, ApiHandlerCreateMessageMetadata,
                         StreamChunk)
from typing import TypeVar
from agent.persistence.model import MemoryService
from uuid import uuid4
import json


T = TypeVar('T')


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
            case "reasoning":
                self.reasoning += chunk.get("text", "")
            case "text":
                self.text += chunk.get("text", "")
            case "usage":
                self.usage = chunk
            case "tool_use":
                self.tool_use.append(chunk)
            case _:
                raise ValueError(f"Unknown chunk type: {_type}")

    async def __aiter__(self):
        chunk: StreamChunk
        async for chunk in self.iterator:
            await self._process_chunk(chunk)
            yield chunk

        if not self.memory_service:
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
    tools = CodebaseReadTools
    
    settings.get("workspace.path") or os.getcwd()
    agent = Agent(
        name="testing_agent",
        tools=tools,
        system_prompt="You are a helpful assistant.",
        memory_service=memory_service
    )
    message_id = str(uuid4())
    session_id = str(uuid4())
    conversation_id = f"agent-user-{session_id}"
    conversation_version = 1
    task_id = str(uuid4())
    
    new_message = {
        "id": message_id,
        "role": "user",
        "content": "What is the main function in the code?"
    }
    
    memory_service.upsert_conversation(
        id=conversation_id,
        version=conversation_version,
        participants=[agent.name, "user"]
    )
    
    memory_service.save_message(
        message=new_message,
        session_id=session_id,
        task_id=task_id,
        conversation_id=conversation_id,
        conversation_version=conversation_version
    )
    
    response = await agent.create_message(
        messages=[new_message],
        conversation_id=conversation_id,
        conversation_version=conversation_version,
        session_id=session_id,
        task_id=task_id,
        id=message_id
    )
    async for chunk in response:
        if chunk["type"] in ("text", "reasoning"):
            print(chunk["text"], end="", flush=True)
        else:
            print(chunk, flush=True)
    
    # call_llm - "tools" >> tools
    # tools >> call_llm

if __name__ == "__main__":
    asyncio.run(main())
