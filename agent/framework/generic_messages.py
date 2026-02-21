from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel

MessageRole = Literal["user", "assistant", "system", "tool", "function"]
ToolCallType = Literal["function"]


ANTHROPIC_EXCLUDE_FIELDS = {
    # "id": ...,
    # "model": ...,
    # "stop_reason": ...,
    # "stop_sequence": ...,
    # "type": ...,
    # "usage": ...,
    # "content": {"__all__": ["citations"]}
}


class Function(BaseModel):
    """function definition"""

    name: str
    arguments: Union[str, Dict[str, Any]]  # Some APIs use string, others dict
    description: Optional[str] = None


class ToolCall(BaseModel):
    """tool call structure"""

    id: Optional[str] = None
    type: ToolCallType = "function"
    function: Function
    is_error: Optional[bool]


class Message(BaseModel):
    """message model that can be converted to any provider format"""

    role: MessageRole
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None  # For tool responses
    function_call: Optional[Function] = None  # Legacy OpenAI format
    name: Optional[str] = None  # Function name for function role


class ToolMessage(Message):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: Optional[str | List[Dict[str, Any]]] = None
    is_error: Optional[bool] = None


class AIMessage(Message):
    role: Literal["user", "assistant"] = "assistant"
    content: Optional[Union[str, List[Dict[str, Any]]]] = None


class SystemMessage(Message):
    role: Literal["system"] = "system"
    content: Optional[Union[str, List[Dict[str, Any]]]] = None


class Conversation(BaseModel):
    messages: List[SystemMessage | AIMessage | ToolMessage]


# OpenAI specific models
class OpenAIFunction(BaseModel):
    name: str
    arguments: str


class OpenAIToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: OpenAIFunction


class OpenAIMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool", "function"]
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    tool_calls: Optional[List[OpenAIToolCall]] = None
    tool_call_id: Optional[str] = None
    function_call: Optional[OpenAIFunction] = None
    name: Optional[str] = None


# Anthropic specific models
class AnthropicToolUse(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class AnthropicToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: Optional[bool] = None


class AnthropicTextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


AnthropicContent = Union[str, List[Union[AnthropicTextContent, AnthropicToolUse, AnthropicToolResult]]]


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: AnthropicContent


# Ollama specific models (similar to OpenAI but with some differences)
class OllamaMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None


class MessageConverter:
    """Converter class to transform between generic and provider-specific formats"""

    @staticmethod
    def to_openai(messages: List[Message]) -> List[OpenAIMessage]:
        """Convert generic messages to OpenAI format"""
        openai_messages = []

        for msg in messages:
            openai_msg_data = {"role": msg.role, "content": msg.content}

            if msg.tool_calls:
                openai_msg_data["tool_calls"] = [
                    OpenAIToolCall(
                        id=tc.id or f"call_{i}",
                        type="function",
                        function=OpenAIFunction(
                            name=tc.function.name,
                            arguments=tc.function.arguments
                            if isinstance(tc.function.arguments, str)
                            else str(tc.function.arguments),
                        ),
                    )
                    for i, tc in enumerate(msg.tool_calls)
                ]

            if msg.tool_call_id:
                openai_msg_data["tool_call_id"] = msg.tool_call_id

            if msg.function_call:
                openai_msg_data["function_call"] = OpenAIFunction(
                    name=msg.function_call.name,
                    arguments=msg.function_call.arguments
                    if isinstance(msg.function_call.arguments, str)
                    else str(msg.function_call.arguments),
                )

            if msg.name:
                openai_msg_data["name"] = msg.name

            openai_messages.append(OpenAIMessage(**openai_msg_data))

        return openai_messages

    @staticmethod
    def to_anthropic(messages: List[Message]) -> List[AnthropicMessage]:
        """Convert generic messages to Anthropic format"""
        anthropic_messages = []
        system_message = None

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            if msg.role == "tool":
                # Tool results in Anthropic format
                content = [
                    AnthropicToolResult(tool_use_id=msg.tool_call_id, content=msg.content or "", is_error=msg.is_error)
                ]
                anthropic_messages.append(AnthropicMessage(role="user", content=content))
                continue

            # Handle regular messages
            if msg.role in ["user", "assistant"]:
                content_parts = []

                # Add text content
                if msg.content:
                    if isinstance(msg.content, str):
                        content_parts.append(AnthropicTextContent(text=msg.content))
                    elif isinstance(msg.content, list):
                        # Handle multimodal content
                        content_parts.extend(msg.content)

                # Add tool calls as tool_use blocks
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_input = tc.function.arguments
                        if isinstance(tool_input, str):
                            import json

                            try:
                                tool_input = json.loads(tool_input)
                            except json.JSONDecodeError:
                                tool_input = {"arguments": tool_input}

                        content_parts.append(
                            AnthropicToolUse(
                                id=tc.id or f"toolu_{len(content_parts)}", name=tc.function.name, input=tool_input
                            )
                        )

                anthropic_messages.append(
                    AnthropicMessage(role=msg.role, content=content_parts if content_parts else "")
                )
        if system_message:
            return [system_message, *anthropic_messages]
        else:
            return anthropic_messages

    @staticmethod
    def to_ollama(messages: List[Message]) -> List[OllamaMessage]:
        """Convert generic messages to Ollama format"""
        ollama_messages = []

        for msg in messages:
            if msg.role == "function":
                continue  # Ollama doesn't support function role

            content = msg.content
            if isinstance(content, list):
                # Convert list content to string for Ollama
                content = str(content)
            elif content is None:
                content = ""

            ollama_msg_data = {"role": msg.role if msg.role != "assistant" else "assistant", "content": content}

            if msg.tool_calls:
                # Convert tool calls to Ollama format
                ollama_msg_data["tool_calls"] = [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]

            ollama_messages.append(OllamaMessage(**ollama_msg_data))

        return ollama_messages


    @staticmethod
    def from_openai(openai_messages: List[OpenAIMessage]) -> List[Message]:
        """Convert OpenAI messages to generic format"""
        generic_messages = []

        for msg in openai_messages:
            generic_msg_data = {"role": MessageRole(msg.role), "content": msg.content}

            if msg.tool_calls:
                generic_msg_data["tool_calls"] = [
                    ToolCall(
                        id=tc.id,
                        type="function",
                        function=Function(name=tc.function.name, arguments=tc.function.arguments),
                    )
                    for tc in msg.tool_calls
                ]

            if msg.tool_call_id:
                generic_msg_data["tool_call_id"] = msg.tool_call_id

            if msg.function_call:
                generic_msg_data["function_call"] = Function(
                    name=msg.function_call.name, arguments=msg.function_call.arguments
                )

            if msg.name:
                generic_msg_data["name"] = msg.name

            generic_messages.append(Message(**generic_msg_data))

        return generic_messages

    @staticmethod
    def from_anthropic(
        anthropic_messages: List[AnthropicMessage], system_message: Optional[str] = None
    ) -> List[Message]:
        """Convert Anthropic messages to generic format"""
        generic_messages = []

        # Add system message if provided
        if system_message:
            generic_messages.append(Message(role="system", content=system_message))

        for msg in anthropic_messages:
            if isinstance(msg.content, str):
                # Simple text message
                generic_messages.append(
                    Message(role=msg.role, content=msg.content if isinstance(msg.content, str) else str(msg.content))
                )
            elif isinstance(msg.content, list):
                # Complex content with potential tool uses/results
                text_parts = []
                tool_calls = []
                tool_results = []

                for content_block in msg.content:
                    if hasattr(content_block, "type"):
                        if content_block.type == "text":
                            text_parts.append(content_block.text)
                        elif content_block.type == "tool_use":
                            tool_calls.append(
                                ToolCall(
                                    id=content_block.id,
                                    type=ToolCallType.FUNCTION,
                                    function=Function(name=content_block.name, arguments=content_block.input),
                                )
                            )
                        elif content_block.type == "tool_result":
                            # Tool results become separate messages
                            tool_results.append((content_block.tool_use_id, content_block.content))
                    else:
                        # Handle dict-like content
                        if isinstance(content_block, dict):
                            if content_block.get("type") == "text":
                                text_parts.append(content_block.get("text", ""))

                # Create message with text content and tool calls
                if text_parts or tool_calls:
                    content = " ".join(text_parts) if text_parts else None
                    generic_messages.append(
                        Message(role=msg.role, content=content, tool_calls=tool_calls if tool_calls else None)
                    )

                # Add tool result messages
                for tool_call_id, result_content in tool_results:
                    generic_messages.append(
                        Message(
                            role="tool",
                            tool_call_id=tool_call_id,
                            content=result_content if isinstance(result_content, str) else str(result_content),
                        )
                    )

        return generic_messages

    @staticmethod
    def from_ollama(ollama_messages: List[OllamaMessage]) -> List[Message]:
        """Convert Ollama messages to generic format"""
        generic_messages = []

        for msg in ollama_messages:
            generic_msg_data = {"role": MessageRole(msg.role), "content": msg.content}

            if msg.tool_calls:
                generic_msg_data["tool_calls"] = [
                    ToolCall(
                        id=f"call_{i}",  # Ollama might not have IDs
                        type="function",
                        function=Function(
                            name=tc.get("function", {}).get("name", ""),
                            arguments=tc.get("function", {}).get("arguments", {}),
                        ),
                    )
                    for i, tc in enumerate(msg.tool_calls)
                ]

            generic_messages.append(Message(**generic_msg_data))

        return generic_messages


def select_tools_use(messages: list[Message]) -> list[dict]:
    deserialized_messages = [m for m in messages]
    tool_use_ids = {
        c["id"]
        for m in deserialized_messages
        if isinstance(m.get("content"), list)
        for c in m["content"]
        if c.get("type") == "tool_use"
    }
    tool_result_ids = set()
    for m in deserialized_messages:
        if m.get("role") == "tool" and "tool_call_id" in m:
            tool_result_ids.add(m["tool_call_id"])
        elif isinstance(m.get("content"), list):
            for c in m["content"]:
                if isinstance(c, dict) and c.get("type") == "tool_result" and "tool_use_id" in c:
                    tool_result_ids.add(c["tool_use_id"])
    tools_to_call = tool_use_ids - tool_result_ids
    return [
        c
        for m in deserialized_messages
        if m.get("role") == "assistant" and isinstance(m.get("content"), list)
        for c in m["content"]
        if c.get("type") == "tool_use" and c["id"] in tools_to_call
    ]


# Example usage and testing
if __name__ == "__main__":
    import json

    # Example generic messages
    generic_messages = [
        dict(role="system", content="You are a helpful assistant."),
        dict(role="user", content="What's the weather like in Paris?"),
        dict(
            role="assistant",
            content="I'll help you check the weather in Paris.",
            tool_calls=[
                dict(id="call_123", function=dict(name="get_weather", arguments={"city": "Paris", "country": "France"}))
            ],
        ),
        dict(role="tool", tool_call_id="call_123", content="The weather in Paris is currently 22°C and sunny."),
    ]
    conversation = Conversation(messages=generic_messages)
    generic_messages = conversation.messages

    converter = MessageConverter()

    # Convert to OpenAI format
    openai_messages = converter.to_openai(generic_messages)
    print("OpenAI Format:")
    print(json.dumps([msg.model_dump() for msg in openai_messages], indent=2))
    print("\n" + "=" * 50 + "\n")

    # Convert to Anthropic format
    anthropic_messages, system_prompt = converter.to_anthropic(generic_messages)
    print("Anthropic Format:")
    print(f"System: {system_prompt}")
    print(json.dumps([msg.model_dump() for msg in anthropic_messages], indent=2))
    print("\n" + "=" * 50 + "\n")

    # Convert to Ollama format
    ollama_messages = converter.to_ollama(generic_messages)
    print("Ollama Format:")
    print(json.dumps([msg.model_dump() for msg in ollama_messages], indent=2))
