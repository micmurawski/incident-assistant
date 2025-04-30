from typing import List, Dict, Any
from langchain_core.messages import AnyMessage, ToolMessage, HumanMessage, SystemMessage


def serialize_messages(messages: List[AnyMessage]) -> List[Dict[str, Any]]:
    """
    Serialize a list of LangChain messages to a list of dictionaries.

    Args:
        messages: List of LangChain message objects

    Returns:
        List of dictionaries containing message data
    """
    serialized = []
    for message in messages:
        message_dict = {
            "type": message.__class__.__name__,
            "content": message.content,
            "id": message.id,
            "name": message.name,
        }
        # Add additional fields based on message type
        if isinstance(message, ToolMessage):
            message_dict["tool_call_id"] = message.tool_call_id
        elif isinstance(message, SystemMessage):
            message_dict["additional_kwargs"] = message.additional_kwargs
        elif isinstance(message, HumanMessage):
            message_dict["additional_kwargs"] = message.additional_kwargs

        serialized.append(message_dict)
    return serialized


def deserialize_messages(messages: List[Dict[str, Any]]) -> List[AnyMessage]:
    """
    Deserialize a list of dictionaries to LangChain message objects.

    Args:
        messages: List of dictionaries containing message data

    Returns:
        List of LangChain message objects
    """
    deserialized = []
    for message_dict in messages:
        message_type = message_dict["type"]
        content = message_dict["content"]
        name = message_dict["name"]
        if message_type == "ToolMessage":
            message = ToolMessage(
                content=content,
                tool_call_id=message_dict.get("tool_call_id"),
                name=name
            )
        elif message_type == "SystemMessage":
            message = SystemMessage(
                content=content,
                additional_kwargs=message_dict.get("additional_kwargs", {}),
                name=name
            )
        elif message_type == "HumanMessage":
            message = HumanMessage(
                content=content,
                additional_kwargs=message_dict.get("additional_kwargs", {}),
                name=name
            )
        else:
            raise ValueError(f"Unknown message type: {message_type}")

        deserialized.append(message)
    return deserialized
