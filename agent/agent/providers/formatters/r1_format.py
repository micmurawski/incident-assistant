from anthropic.types.message_param import MessageParam as AnthropicMessage
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam as AssistantMessage,
)
from openai.types.chat.chat_completion_content_part_image import ChatCompletionContentPartImage as ContentPartImage
from openai.types.chat.chat_completion_content_part_text import ChatCompletionContentPartText as ContentPartText
from openai.types.chat.chat_completion_function_message_param import (
    ChatCompletionFunctionMessageParam as FunctionMessage,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam as Message
from openai.types.chat.chat_completion_tool_message_param import ChatCompletionToolMessageParam as ToolMessage
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam as UserMessage


def _convert_on_type(message: AnthropicMessage) -> Message:
    if message.get("role") == "user":
        return UserMessage(**{"role": message.get("role"), "content": message.get("content")})
    elif message.get("role") == "assistant":
        return AssistantMessage(**{"role": message.get("role"), "content": message.get("content")})
    elif message.get("role") == "function":
        return FunctionMessage(**{"role": message.get("role"), "content": message.get("content")})
    elif message.get("role") == "tool":
        return ToolMessage(**{"role": message.get("role"), "content": message.get("content")})
    else:
        return {"role": message.get("role"), "content": message.get("content")}


def convert_to_r1_format(messages: list[AnthropicMessage]) -> list[Message]:
    r1_messages: list[Message] = []

    for message in messages:
        last_message = r1_messages[-1] if r1_messages else None
        message_content: str | list[(ContentPartText | ContentPartImage)] = ""
        has_images = False

        # Convert content to appropriate format
        if isinstance(message.get("content"), list):
            text_parts: list[str] = []
            image_parts: list[ContentPartImage] = []

            for part in message["content"]:
                if part.get("type") == "text":
                    text_parts.append(part["text"])
                elif part.get("type") == "image":
                    has_images = True
                    image_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{part['source']['media_type']};base64,{part['source']['data']}"
                            },
                        }
                    )

            if has_images:
                parts = []
                if text_parts:
                    parts.append({"type": "text", "text": "\n".join(text_parts)})
                parts.extend(image_parts)
                message_content = parts
            else:
                message_content = "\n".join(text_parts)
        else:
            message_content = message.get("content", "")

        # If last message has same role, merge the content
        if last_message and last_message.get("role") == message.get("role"):
            if isinstance(last_message["content"], str) and isinstance(message_content, str):
                last_message["content"] += f"\n{message_content}"
            else:
                # If either has image content, convert both to array format
                last_content = (
                    last_message["content"]
                    if isinstance(last_message["content"], list)
                    else [{"type": "text", "text": last_message["content"] or ""}]
                )

                new_content = (
                    message_content
                    if isinstance(message_content, list)
                    else [{"type": "text", "text": message_content}]
                )

                last_message["content"] = last_content + new_content
        else:
            # Add as new message with the correct type based on role

            new_message = _convert_on_type({"role": message.get("role"), "content": message_content})

            r1_messages.append(new_message)

    return r1_messages
