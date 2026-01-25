import json
from typing import List, Optional

from anthropic.types.message_param import MessageParam as AnthropicMessage
from openai.types.chat.chat_completion_message_param import \
    ChatCompletionMessageParam as OpenAIMessage
from openai.types.chat.chat_completion_message_tool_call_param import \
    ChatCompletionMessageToolCallParam


def convert_to_openai_messages(anthropic_messages: List[AnthropicMessage]) -> List[OpenAIMessage]:
    """
    Convert Anthropic message format to OpenAI message format.

    Args:
        anthropic_messages: List of Anthropic-formatted messages

    Returns:
        List of OpenAI-formatted chat completion messages
    """
    openai_messages: List[OpenAIMessage] = []

    for anthropic_message in anthropic_messages:
        if isinstance(anthropic_message.get("content"), str):
            openai_messages.append(dict(role=anthropic_message["role"], content=anthropic_message["content"]))
        else:
            # Process array content
            if anthropic_message["role"] == "user":
                non_tool_messages = []
                tool_messages = []

                for part in anthropic_message["content"]:
                    if part.get("type") == "tool_result":
                        tool_messages.append(part)
                    elif part.get("type") in ("text", "image"):
                        non_tool_messages.append(part)
                    # user cannot send tool_use messages

                # Process tool result messages FIRST since they must follow the tool use messages
                tool_result_images = []
                for tool_message in tool_messages:
                    # The Anthropic SDK allows tool results to be a string or an array of text
                    # and image blocks, enabling rich and structured content. In contrast, the
                    # OpenAI SDK only supports tool results as a single string, so we map the
                    # Anthropic tool result parts into one concatenated string to maintain compatibility.
                    content: str

                    if isinstance(tool_message.get("content"), str):
                        content = tool_message["content"]
                    else:
                        parts = []
                        for part in tool_message.get("content") or []:
                            if part.get("type") == "image":
                                tool_result_images.append(part)
                                parts.append("(see following user message for image)")
                            else:
                                parts.append(part.get("text", ""))
                        content = "\n".join(parts)

                    openai_messages.append(
                        OpenAIMessage(
                            role="tool",
                            tool_call_id=tool_message["tool_use_id"],
                            content=content,
                        )
                    )

                # If tool results contain images, send as a separate user message
                # I ran into an issue where if I gave feedback for one of many tool uses, the request would fail.
                # "Messages following `tool_use` blocks must begin with a matching number of `tool_result` blocks."
                # Therefore we need to send these images after the tool result messages
                # NOTE: it's actually okay to have multiple user messages in a row, the model will treat them
                # as a continuation of the same input (this way works better than combining them into one message,
                # since the tool result specifically mentions (see following user message for image)
                # UPDATE v2.0: we don't use tools anymore, but if we did it's important to note that the
                # openrouter prompt caching mechanism requires one user message at a time, so we would need
                # to add these images to the user content array instead.
                # if tool_result_images:
                #     openai_messages.append({
                #         'role': 'user',
                #         'content': [
                #             {
                #                 'type': 'image_url',
                #                 'image_url': {
                #                     'url': f"data:{part['source']['media_type']};base64,{part['source']['data']}"
                #                 }
                #             }
                #             for part in tool_result_images
                #         ]
                #     })

                # Process non-tool messages
                if non_tool_messages:
                    content_parts = []
                    for part in non_tool_messages:
                        if part.get("type") == "image":
                            content_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{part['source']['media_type']};base64,{part['source']['data']}"
                                    },
                                }
                            )
                        else:
                            content_parts.append({"type": "text", "text": part["text"]})

                    openai_messages.append(OpenAIMessage(role="user", content=content_parts))

            elif anthropic_message["role"] == "assistant":
                non_tool_messages = []
                tool_messages = []

                for part in anthropic_message["content"]:
                    if part.get("type") == "tool_use":
                        tool_messages.append(part)
                    elif part.get("type") in ("text", "image"):
                        non_tool_messages.append(part)
                    # assistant cannot send tool_result messages

                # Process non-tool messages
                content: Optional[str] = None
                if non_tool_messages:
                    parts = []
                    for part in non_tool_messages:
                        if part.get("type") == "image":
                            # impossible as the assistant cannot send images
                            parts.append("")
                        else:
                            parts.append(part["text"])
                    content = "\n".join(parts)

                # Process tool use messages
                tool_calls: List[ChatCompletionMessageToolCallParam] = [
                    ChatCompletionMessageToolCallParam(
                        id=tool_message["id"],
                        type="function",
                        function={
                            "name": tool_message["name"],
                            # json string
                            "arguments": json.dumps(tool_message["input"]),
                        },
                    )
                    for tool_message in tool_messages
                ]

                message: OpenAIMessage = OpenAIMessage(
                    role="assistant",
                    content=content,
                )

                # Cannot be an empty array. API expects an array with minimum length 1,
                # and will respond with an error if it's empty
                if tool_calls:
                    message.tool_calls = tool_calls

                openai_messages.append(message)

    return openai_messages
