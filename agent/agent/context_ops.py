from typing import Dict, List, Optional, Required, TypedDict

from framework.decorators import node

from agent.providers.base import AnthropicMessage, ApiHandler
from agent.tooling.decorators import Hidden

TOKEN_BUFFER_PERCENTAGE = 0.1
N_MESSAGES_TO_KEEP = 3
MIN_CONDENSE_THRESHOLD = 5
ANTHROPIC_DEFAULT_MAX_TOKENS = 8192
MAX_CONDENSE_THRESHOLD = 100

SUMMARY_PROMPT = """\
Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.
This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing with the conversation and supporting any continuing tasks.

Your summary should be structured as follows:
Context: The context to continue the conversation with. If applicable based on the current task, this should include:
  1. Previous Conversation: High level details about what was discussed throughout the entire conversation with the user. This should be written to allow someone to be able to follow the general overarching conversation flow.
  2. Current Work: Describe in detail what was being worked on prior to this request to summarize the conversation. Pay special attention to the more recent messages in the conversation.
  3. Key Technical Concepts: List all important technical concepts, technologies, coding conventions, and frameworks discussed, which might be relevant for continuing with this work.
  4. Relevant Files and Code: If applicable, enumerate specific files and code sections examined, modified, or created for the task continuation. Pay special attention to the most recent messages and changes.
  5. Problem Solving: Document problems solved thus far and any ongoing troubleshooting efforts.
  6. Pending Tasks and Next Steps: Outline all pending tasks that you have explicitly been asked to work on, as well as list the next steps you will take for all outstanding work, if applicable. Include code snippets where they add clarity. For any next steps, include direct quotes from the most recent conversation showing exactly what task you were working on and where you left off. This should be verbatim to ensure there's no information loss in context between tasks.

Example summary structure:
1. Previous Conversation:
  [Detailed description]
2. Current Work:
  [Detailed description]
3. Key Technical Concepts:
  - [Concept 1]
  - [Concept 2]
  - [...]
4. Relevant Files and Code:
  - [File Name 1]
    - [Summary of why this file is important]
    - [Summary of the changes made to this file, if any]
    - [Important Code Snippet]
  - [File Name 2]
    - [Important Code Snippet]
  - [...]
5. Problem Solving:
  [Detailed description]
6. Pending Tasks and Next Steps:
  - [Task 1 details & next steps]
  - [Task 2 details & next steps]
  - [...]

Output only the summary of the conversation so far, without any additional commentary or explanation.
"""


class TruncateOptions(TypedDict, total=False):
    """Options for truncation"""

    messages: List[AnthropicMessage]
    total_tokens: int
    context_window: int
    max_tokens: Optional[int]
    api_handler: ApiHandler
    auto_condense_context: bool
    auto_condense_context_percent: float
    system_prompt: str
    task_id: str
    custom_condensing_prompt: Optional[str]
    condensing_api_handler: Optional[ApiHandler]
    profile_thresholds: Dict[str, float]
    current_profile_id: str


class SummarizeResponse(TypedDict, total=False):
    """Response from the summarization operation."""

    messages: Required[List[AnthropicMessage]]
    summary: Required[str]
    cost: float
    new_context_tokens: Optional[int] = None
    error: Optional[str] = None


class TruncateResponse(SummarizeResponse):
    """Response from truncation with previous context tokens"""

    prev_context_tokens: Required[int]


async def estimate_token_count(
    content: list[AnthropicMessage],
    api_handler: ApiHandler,
) -> int:
    if not content or len(content) == 0:
        return 0
    return await api_handler.count_tokens(content)


def truncate_conversation(
    messages: List[AnthropicMessage],
    frac_to_remove: float,
) -> List[AnthropicMessage]:
    truncated_messages = [messages[0]]
    raw_messages_to_remove = int((len(messages) - 1) * frac_to_remove)
    messages_to_remove = raw_messages_to_remove - (raw_messages_to_remove % 2)
    remaining_messages = messages[messages_to_remove + 1:]
    truncated_messages.extend(remaining_messages)
    return truncated_messages


async def truncate_conversation_if_needed(
    messages: List[AnthropicMessage],
    total_tokens: int,
    context_window: int,
    api_handler: ApiHandler,
    auto_condense_context: bool,
    auto_condense_context_percent: float,
    system_prompt: str,
    max_tokens: Optional[int] = None,
    custom_condensing_prompt: Optional[str] = None,
    condensing_api_handler: Optional[ApiHandler] = None,
    profile_thresholds: Optional[Dict[str, float]] = None,
    current_profile_id: str = "",
) -> TruncateResponse:
    """
    Conditionally truncates the conversation messages if the total token count
    exceeds the model's limit, considering the size of incoming content.

    Args:
        messages: The conversation messages
        total_tokens: The total number of tokens in the conversation (excluding the last user message)
        context_window: The context window size
        max_tokens: The maximum number of tokens allowed
        api_handler: The API handler to use for token counting
        auto_condense_context: Whether to use LLM summarization or sliding window implementation
        auto_condense_context_percent: Percentage threshold for auto-condensing
        system_prompt: The system prompt, used for estimating the new context size after summarizing
        custom_condensing_prompt: Optional custom prompt for condensing
        condensing_api_handler: Optional separate API handler for condensing
        profile_thresholds: Per-profile thresholds for condensing
        current_profile_id: The current profile ID

    Returns:
        The original or truncated conversation messages with metadata
    """
    if profile_thresholds is None:
        profile_thresholds = {}

    error: Optional[str] = None
    cost = 0

    # Calculate the maximum tokens reserved for response
    reserved_tokens = max_tokens or ANTHROPIC_DEFAULT_MAX_TOKENS

    # Estimate tokens for the last message (which is always a user message)
    last_message = messages[-1]
    last_message_content = last_message.content

    if isinstance(last_message_content, list):
        last_message_tokens = await estimate_token_count(last_message_content, api_handler)
    else:
        last_message_tokens = await estimate_token_count(
            [{"type": "text", "text": str(last_message_content)}], api_handler
        )

    # Calculate total effective tokens (total_tokens never includes the last message)
    prev_context_tokens = total_tokens + last_message_tokens

    # Calculate available tokens for conversation history
    # Truncate if we're within TOKEN_BUFFER_PERCENTAGE of the context window
    allowed_tokens = context_window * (1 - TOKEN_BUFFER_PERCENTAGE) - reserved_tokens

    # Determine the effective threshold to use
    effective_threshold = auto_condense_context_percent
    profile_threshold = profile_thresholds.get(current_profile_id)

    if profile_threshold is not None:
        if profile_threshold == -1:
            # Special case: -1 means inherit from global setting
            effective_threshold = auto_condense_context_percent
        elif MIN_CONDENSE_THRESHOLD <= profile_threshold <= MAX_CONDENSE_THRESHOLD:
            # Valid custom threshold
            effective_threshold = profile_threshold
        else:
            # Invalid threshold value, fall back to global setting
            print(
                f"Invalid profile threshold {profile_threshold} for profile "
                f'"{current_profile_id}". Using global default of '
                f"{auto_condense_context_percent}%"
            )
            effective_threshold = auto_condense_context_percent
    # If no specific threshold is found for the profile, fall back to global setting

    if auto_condense_context:
        context_percent = (100 * prev_context_tokens) / context_window
        if context_percent >= effective_threshold or prev_context_tokens > allowed_tokens:
            # Attempt to intelligently condense the context
            result = await summarize_conversation(
                messages=messages,
                api_handler=api_handler,
                system_prompt=system_prompt,
                prev_context_tokens=prev_context_tokens,
                custom_condensing_prompt=custom_condensing_prompt,
                condensing_api_handler=condensing_api_handler,
            )
            if result.get("error"):
                error = result["error"]
                cost = result.get("cost", 0)
            else:
                return TruncateResponse(**result, prev_context_tokens=prev_context_tokens)

    # Fall back to sliding window truncation if needed
    if prev_context_tokens > allowed_tokens:
        truncated_messages = truncate_conversation(messages, 0.5)
        return TruncateResponse(
            messages=truncated_messages,
            prev_context_tokens=prev_context_tokens,
            summary="",
            cost=cost,
            error=error,
        )

    # No truncation or condensation needed
    return TruncateResponse(
        messages=messages,
        summary="",
        cost=cost,
        prev_context_tokens=prev_context_tokens,
        error=error,
    )


def get_messages_since_last_summary(messages: List[AnthropicMessage]) -> List[AnthropicMessage]:
    """
    Returns the list of all messages since the last summary message, including the summary.
    Returns all messages if there is no summary.
    """
    # Find the last summary message
    last_summary_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("isSummary", False):
            last_summary_index = i
            break

    if last_summary_index == -1:
        return messages

    messages_since_summary = messages[last_summary_index:]

    # Bedrock requires the first message to be a user message.
    # See https://github.com/RooCodeInc/Roo-Code/issues/4147
    user_message: AnthropicMessage = AnthropicMessage(
        role="user",
        content="Please continue from the following summary:",
        ts=messages[0]["ts"] - 1 if messages and "ts" in messages[0] else int(__import__("time").time() * 1000),
    )

    return [user_message] + messages_since_summary


async def summarize_conversation(
    messages: List[AnthropicMessage],
    api_handler: ApiHandler,
    system_prompt: str,
    prev_context_tokens: int,
    custom_condensing_prompt: Optional[str] = None,
    condensing_api_handler: Optional[ApiHandler] = None,
) -> SummarizeResponse:
    """
    Summarizes the conversation messages using an LLM call.

    Args:
        messages: The conversation messages
        api_handler: The API handler to use for token counting (fallback if condensing_api_handler not provided)
        system_prompt: The system prompt for API requests (fallback if custom_condensing_prompt not provided)
        prev_context_tokens: The number of tokens currently in the context, used to ensure we don't grow the context
        custom_condensing_prompt: Optional custom prompt to use for condensing
        condensing_api_handler: Optional specific API handler to use for condensing

    Returns:
        SummarizeResponse with the result of the summarization operation
    """

    # Always preserve the first message (which may contain slash command content)
    first_message = messages[0]

    # Get messages to summarize, excluding the first message and last N messages
    messages_to_summarize = get_messages_since_last_summary(
        messages[1:-N_MESSAGES_TO_KEEP] if len(messages) > N_MESSAGES_TO_KEEP else []
    )

    if len(messages_to_summarize) <= 1:
        error = (
            "Not enough messages to condense"
            if len(messages) <= N_MESSAGES_TO_KEEP + 1
            else "Conversation was condensed recently"
        )
        return SummarizeResponse(messages=messages, cost=0.0, summary="", error=error)

    keep_messages = messages[-N_MESSAGES_TO_KEEP:]

    # Check if there's a recent summary in the messages we're keeping
    recent_summary_exists = any(msg.get("isSummary", False) for msg in keep_messages)

    if recent_summary_exists:
        error = "Conversation was condensed recently"
        return SummarizeResponse(messages=messages, cost=0.0, summary="", error=error)

    final_request_message = {
        "role": "user",
        "content": "Summarize the conversation so far, as described in the prompt instructions.",
    }

    request_messages = messages_to_summarize + [final_request_message]

    request_messages = [{"role": msg["role"], "content": msg["content"]} for msg in request_messages]

    # Use custom prompt if provided and non-empty, otherwise use the default SUMMARY_PROMPT
    prompt_to_use = (
        custom_condensing_prompt.strip()
        if custom_condensing_prompt and custom_condensing_prompt.strip()
        else SUMMARY_PROMPT
    )

    # Use condensing API handler if provided, otherwise use main API handler
    handler_to_use = condensing_api_handler or api_handler

    # Check if the chosen handler supports the required functionality
    if not handler_to_use or not hasattr(handler_to_use, "create_message"):
        print(
            "Chosen API handler for condensing does not support message creation or is invalid, "
            "falling back to main api_handler."
        )
        handler_to_use = api_handler

        if not handler_to_use or not hasattr(handler_to_use, "create_message"):
            print("Main API handler is also invalid for condensing. Cannot proceed.")
            error = "Invalid API handler for condensing"
            return SummarizeResponse(messages=messages, cost=0.0, summary="", error=error)

    stream = handler_to_use.create_message(prompt_to_use, request_messages)

    summary = ""
    cost = 0.0
    output_tokens = 0

    async for chunk in stream:
        if chunk.get("type") == "text":
            summary += chunk.get("text", "")
        elif chunk.get("type") == "usage":
            # Record final usage chunk only
            cost = chunk.get("totalCost", 0.0)
            output_tokens = chunk.get("outputTokens", 0)

    summary = summary.strip()

    if not summary:
        error = "Failed to generate summary"
        return SummarizeResponse(messages=messages, cost=cost, summary="", error=error)

    summary_message: AnthropicMessage = AnthropicMessage(
        role="assistant", content=summary, ts=keep_messages[0]["ts"], isSummary=True
    )

    # Reconstruct messages: [first message, summary, last N messages]
    new_messages = [first_message, summary_message] + keep_messages

    # Count the tokens in the context for the next API request
    # We only estimate the tokens in summary_message if output_tokens is 0, otherwise we use output_tokens
    system_prompt_message: AnthropicMessage = AnthropicMessage(role="user", content=system_prompt)

    context_messages = (
        [system_prompt_message] + keep_messages
        if output_tokens
        else [system_prompt_message, summary_message] + keep_messages
    )

    # Extract content blocks
    context_blocks = []
    for message in context_messages:
        content = message["content"]
        if isinstance(content, str):
            context_blocks.append({"text": content, "type": "text"})
        else:
            context_blocks.extend(content)

    new_context_tokens = output_tokens + await api_handler.count_tokens(context_blocks)

    if new_context_tokens >= prev_context_tokens:
        error = "Context grew after condensing"
        return SummarizeResponse(messages=messages, cost=cost, summary="", error=error)

    return SummarizeResponse(messages=new_messages, summary=summary, cost=cost, new_context_tokens=new_context_tokens)


@node
async def context_summarization_node(
    context: Hidden[dict],
    system_prompt: Hidden[str],
    messages: List[AnthropicMessage],
) -> List[AnthropicMessage]:
    
    api_handler = context.get("api_handler", None)
    if not isinstance(api_handler, ApiHandler):
        raise ValueError("api_handler must be an instance of ApiHandler")
    prev_context_tokens = await api_handler.count_tokens(messages)
    result = await summarize_conversation(
        messages=messages,
        api_handler=api_handler,
        system_prompt=system_prompt,
        prev_context_tokens=prev_context_tokens,
    )
    return result.messages
