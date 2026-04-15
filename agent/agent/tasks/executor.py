
import copy
import json
import os
from uuid import uuid4

from agent.llm import AgentRegistry, ChunkProxyIterator, LLMAgent
from agent.persistence.session_queries import (fetch_session_messages,
                                               upsert_session_messages)
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import ToolResult, Tools

MAX_TASK_DEPTH = int(os.environ.get("MAX_TASK_DEPTH", 2))

FEEDBACK_SYSTEM_PROMPT_TEMPLATE = """
You are a feedback assistant. You are given a task and a feedback. You need to provide feedback on the task.

Use feedback tool to provide feedback on the task. If you are approving task, do not provide any feedback.
Make sure all todos are completed:
Current todos:
{todos_str}
"""

TODO_LIST_PROMPT = """
Here is the todo list:\n
{todos_str}

Please work on the todo list. And report back when you are done. 
"""


class TaskExecutor:
    @staticmethod
    def _result_with_session_id(result, session_id: str):
        """Append session_id to tool results returned to the assigner (does not mutate task conversation)."""
        suffix = (
            f"\n\nsession_id: {session_id}\n"
            "To continue this task with the same assignee, use this session_id with the assign_task tool. "
            "This will let you pick up right where you left off and follow up on the current task."
        )
   
        if result is None:
            return None
        if isinstance(result, str):
            return result + suffix
        if isinstance(result, list):
            out = list(result)
            out.append({"type": "text", "text": suffix.strip()})
            return out
        if isinstance(result, dict):
            merged = dict(result)
            merged["session_id"] = session_id
            return merged
        return f"{result}{suffix}"

    @staticmethod
    async def assign_and_run(
        parent_task: Task,
        assigner: str,
        assignee: str,
        message: str,
        todos_str: str,
        feedback_tools: Tools | None = None,
        depth: int = 0,
        session_id: str | None = None,
    ) -> ToolResult:
        sid = session_id if session_id is not None else str(uuid4())
        settings = SettingsManager.get_instance()
        feedback_enabled = settings.get("features.feedback_enabled", False)


        if depth >= MAX_TASK_DEPTH:
            return ToolResult(result=None, error="Task depth limit reached. You cannot assign tasks to anymore.")

        prior_raw = fetch_session_messages(assigner, assignee, sid)
        if session_id is not None and prior_raw is None:
            return ToolResult(
                result=None,
                error=f"No session found for session_id={sid}",
            )
        prior_messages = copy.deepcopy(prior_raw) if prior_raw is not None else []

        initial_message = {
            "role": "user",
            "content": message + TODO_LIST_PROMPT.format(todos_str=todos_str),
        }
        conversation_messages = prior_messages + [initial_message]
        history_messages = prior_messages + [copy.deepcopy(initial_message)]

        current_task = parent_task.create_child_task(
            assignee=assignee,
            assigner=assigner,
            conversation=conversation_messages,
            messages_history=history_messages,
            todo_list_str=todos_str,
        )
        assignee_agent: LLMAgent = AgentRegistry.get_instance().get(assignee)
        assigner_agent: LLMAgent = AgentRegistry.get_instance().get(assigner)

        if depth - 1 == MAX_TASK_DEPTH:
            from copy import deepcopy
            assignee_agent = deepcopy(assignee_agent)
            tools = deepcopy(assignee_agent.tools)
            tools.pop("assign_task")
            tools.pop("update_todo")
            tools.pop("provide_feedback")
            assignee_agent.update_tools_definitions(tools=tools)

        shared = TaskExecutor._build_assignee_shared(current_task, depth)
        await assignee_agent.call(shared=shared)
        current_task.conversation = shared["messages"]
        upsert_session_messages(assigner, assignee, sid, list(shared["messages"]))

        if not feedback_enabled:
            current_task.attempt_complete(force=True)
            current_task.save()
            return ToolResult(
                result=TaskExecutor._result_with_session_id(current_task.conversation[-1]["content"], sid),
                error=None,
            )
        else:

            feedback_tools_definitions = feedback_tools.tools_definitions(
                format=assignee_agent.api_handler.provider,
                format_kwargs=assignee_agent.get_shared()
            )

            for _ in range(current_task.consecutive_mistakes_limit):
                feedback_attempts = 0
                max_feedback_attempts = 3
                additional_messages = None
                feedback_tool_use = None
                while feedback_attempts < max_feedback_attempts:
                    feedback_iterator = await TaskExecutor.iterate_feedback(current_task, assigner_agent, feedback_tools_definitions, additional_messages)
                    if feedback_iterator.usage_summary:
                        for k, v in feedback_iterator.usage_summary.items():
                            current_task.usage[k] = current_task.usage.get(k, 0) + v

                    print("tool uses: ", feedback_iterator.tool_use)

                    feedback_tool_use = next(
                        filter(lambda tu: tu["name"] == "provide_feedback", feedback_iterator.tool_use),
                        None
                    )
                    if feedback_tool_use is not None:
                        break
                    # Try to fetch feedback again (simulate re-iterating)
                    feedback_attempts += 1
                    additional_messages = [
                        {"role": "user", "content": "Please provide feedback now! You may approve, discard or provide feedback."}]
                    print(f"Feedback not found, attempt {feedback_attempts} of {max_feedback_attempts}")
                if feedback_tool_use is None:
                    raise Exception("Feedback not found after multiple attempts.")
                if feedback_tool_use["input"].get("approve"):
                    feedback_message = None
                    if feedback_tool_use["input"].get("feedback"):
                        feedback_message = {"role": "user", "content": feedback_tool_use["input"].get("feedback")}
                    else:
                        feedback_message = {"role": "user", "content": "Task is approved"}

                    current_task.feedback(feedback_message)
                    current_task.attempt_complete(force=True)
                    current_task.save()
                    upsert_session_messages(assigner, assignee, sid, list(current_task.conversation))
                    return ToolResult(
                        result=TaskExecutor._result_with_session_id(current_task.conversation[-1]["content"], sid),
                        error=None,
                    )
                elif feedback_tool_use["input"].get("discard"):
                    current_task.status = TaskStatus.DISCARDED
                    feedback_message = None
                    if feedback_tool_use["input"].get("feedback"):
                        feedback_message = {"role": "user", "content": feedback_tool_use["input"].get("feedback")}
                    else:
                        feedback_message = {"role": "user", "content": "Task is not longer relevant and was discarded"}
                    current_task.feedback(feedback_message)
                    current_task.save()
                    upsert_session_messages(assigner, assignee, sid, list(current_task.conversation))
                    return ToolResult(
                        result=TaskExecutor._result_with_session_id(
                            "Task is not longer relevant and was discarded", sid
                        ),
                        error=None,
                    )
                elif feedback_tool_use["input"].get("feedback"):
                    current_task.consecutive_mistakes_count += 1
                    current_task.status = TaskStatus.AWAITING_INPUT
                    feedback_message = {"role": "user", "content": feedback_tool_use["input"].get("feedback")}
                    current_task.feedback(feedback_message)
                    current_task.save()
                    upsert_session_messages(assigner, assignee, sid, list(current_task.conversation))
            return ToolResult(result=None, error="Feedback not found after multiple attempts.")

    @staticmethod
    def _build_assignee_shared(task: Task, depth: int) -> dict:
        return {"task": task, "messages": list(task.conversation), "depth": depth + 1}

    @classmethod
    async def iterate_feedback(cls, current_task: Task, assigner_agent: LLMAgent, feedback_tools_definitions: list[dict], additional_messages: list[dict] = None) -> ChunkProxyIterator:

        debug_payload = cls._build_feedback_debug_payload(
            parent_task=current_task.parent,
            current_task=current_task,
            history=current_task.messages_history,
            candidate_result=current_task.conversation[-1],
            final_feedback_messages=current_task.conversation,
        )
        with open("debug_feedback_messages.json", "w") as f:
            json.dump(debug_payload, f)

        if additional_messages is None:
            additional_messages = []
        messages = current_task.get_conversation_with_swapped_roles() + additional_messages
        feedback_iterator: ChunkProxyIterator = await assigner_agent.create_message(
            messages=messages,
            metadata=None,
            tools=feedback_tools_definitions,
            system_prompt=FEEDBACK_SYSTEM_PROMPT_TEMPLATE.format(todos_str=current_task.get_todo_str())
        )
        async for _ in feedback_iterator:
            pass
        return feedback_iterator

    @staticmethod
    def _build_feedback_debug_payload(
        parent_task: Task,
        current_task: Task,
        history: list[dict],
        candidate_result: dict,
        final_feedback_messages: list[dict],
    ) -> dict:
        return {
            "parent_task_id": parent_task.id,
            "child_task_id": current_task.id,
            "attempt": {
                "consecutive_mistakes_count": current_task.consecutive_mistakes_count,
                "consecutive_mistakes_limit": current_task.consecutive_mistakes_limit,
            },
            "history_context": history,
            "candidate_result": candidate_result,
            "final_feedback_messages": final_feedback_messages,
        }
