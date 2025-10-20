from typing import Literal, Optional

from pydantic import BaseModel


class TextContent(BaseModel):
    text: str
    citations: Optional[list[dict]] = None
    type: Literal["text"] = "text"


class ToolUse(BaseModel):
    id: str
    input: dict
    name: str
    type: Literal["tool_use"] = "tool_use"


class ToolResult(BaseModel):
    tool_use_id: str
    content: str
    type: Literal["tool_result"] = "tool_result"


class BaseMessage(BaseModel):
    role: str
    content: str | list[TextContent | ToolUse | ToolResult]


class Message(BaseMessage):
    class Config:
        extra = "allow"


EXCLUDE_FIELDS = {
    "id": ...,
    "model": ...,
    "stop_reason": ...,
    "stop_sequence": ...,
    "type": ...,
    "usage": ...,
    "content": {"__all__": ["citations"]},
}


def load_messages(messages: list[dict]) -> list[Message]:
    serialized_messages = []
    for message in messages:
        message = Message(**message)
        serialized_messages.append(message)
    return serialized_messages


def dump_messages(messages: list[Message], exclude_fields: dict | None = None) -> list[dict]:
    if exclude_fields is None:
        exclude_fields = {}
    serialized_messages = []
    for message in messages:
        serialized_message = message.model_dump(exclude=exclude_fields)
        serialized_messages.append(serialized_message)
    return serialized_messages


def select_tools_use(messages: list[Message]) -> list[dict]:
    deserialized_messages = dump_messages(messages)
    tool_use_ids = {
        c["id"]
        for m in deserialized_messages
        if isinstance(m.get("content"), list)
        for c in m["content"]
        if c.get("type") == "tool_use"
    }
    tool_result_ids = {
        c["tool_use_id"]
        for m in deserialized_messages
        if isinstance(m.get("content"), list)
        for c in m["content"]
        if c.get("type") == "tool_result"
    }
    tools_to_call = tool_use_ids - tool_result_ids
    return [
        c
        for m in deserialized_messages
        if m.get("role") == "assistant" and isinstance(m.get("content"), list)
        for c in m["content"]
        if c.get("type") == "tool_use" and c["id"] in tools_to_call
    ]


def print_messages(messages: list[Message]):
    for i, message in enumerate(messages):
        print(f"{i}: {message.role}:")
        if isinstance(message.content, list):
            for content in message.content:
                if isinstance(content, TextContent):
                    print(content.text)
                elif isinstance(content, ToolUse):
                    result = messages[i + 1].content[0].content
                    kwags_str = ", ".join(f"{k}={v}" for k, v in content.input.items())
                    print(f"{content.name}({kwags_str})={result}")
                elif isinstance(content, ToolResult):
                    pass
        else:
            print(message.content)
        print()
