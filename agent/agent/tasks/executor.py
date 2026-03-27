
import os

from agent.llm import AgentRegistry, ChunkProxyIterator, LLMAgent
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import ToolResult, Tools

MAX_TASK_DEPTH = int(os.environ.get("MAX_TASK_DEPTH", 2))

FEEDBACK_SYSTEM_PROMPT_TEMPLATE = """
You need to feedback completion of the task, verify if all tasks objectives are met.
The task was the following:
{task_description}

user will report back with the result of the task.
"""

TODO_LIST_PROMPT = """
Here is the todo list:
{todos_str}

Please work on the todo list. And report back when you are done. 
Only last message will be considered as the final answer.
If you will be ask to improve result, you should correct your previous answer.
"""


class TaskExecutor:
    @staticmethod
    async def assign_and_run(
        parent_task: Task,
        assigner: str,
        assignee: str,
        message: str,
        todos_str: str,
        feedback_tools: Tools | None = None,
        depth: int = 0,
    ) -> ToolResult:
        if depth >= MAX_TASK_DEPTH:
            raise Exception("Task depth limit reached. You cannot assign tasks to anymore.")

        messages = [
            {
                "role": "user",
                "content": message + TODO_LIST_PROMPT.format(todos_str=todos_str)
            }
        ]
        current_task = parent_task.create_child_task(
            assignee=assignee,
            assigner=assigner,
            conversation=messages,
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

        shared = {"task": current_task, "messages": current_task.conversation, "depth": depth + 1}

        for _ in range(current_task.consecutive_mistakes_limit):
            await assignee_agent.call(shared=shared)
            # print("THIS IS RESULT CONVO")
            # print(json.dumps(shared["messages"], indent=4))
            current_task.status = TaskStatus.AWAITING_FEEDBACK
            current_task.conversation = shared["messages"]

            # Sync tool usage from conversation
            current_task.tool_usage = []
            tool_calls = {}
            for msg in current_task.conversation:
                role = msg.get("role")
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                if role == "assistant":
                    for block in content:
                        if block.get("type") == "tool_use":
                            tool_calls[block["id"]] = block
                elif role == "user":
                    for block in content:
                        if block.get("type") == "tool_result":
                            tid = block.get("tool_use_id")
                            if tid in tool_calls:
                                call = tool_calls[tid]
                                res = block.get("content", "")
                                current_task.tool_usage.append({
                                    "name": call["name"],
                                    "input": call["input"],
                                    "is_success": not block.get("is_error", False),
                                    "result_summary": str(res)[:200] if res else ""
                                })

            feedback_tools_definitions = feedback_tools.tools_definitions(
                format=assignee_agent.api_handler.provider,
                format_kwargs=assignee_agent.get_shared()
            )

            # How to elegantly add conversation trajectory fron assingner to feedback agent?
            # print("THIS IS CONVO")
            # print(current_task.get_conversation_with_swapped_roles())
            
            messages = current_task.get_conversation_with_swapped_roles(include_actions=True)
            feedback_messages = messages[1:] if len(messages) > 1 else []
            if not feedback_messages:
                feedback_messages = [
                    {
                        "role": "user",
                        "content": (
                            "No transcript remained after filtering (or only the task line exists). "
                            "Use the task description in the system prompt to provide_feedback."
                        ),
                    }
                ]

            feedback_iterator: ChunkProxyIterator = await assigner_agent.create_message(
                messages=feedback_messages,
                metadata=None,
                tools=feedback_tools_definitions,
                system_prompt=FEEDBACK_SYSTEM_PROMPT_TEMPLATE.format(task_description=messages[0]["content"])
            )

            async for _ in feedback_iterator:
                pass

            if feedback_iterator.usage_summary:
                for k, v in feedback_iterator.usage_summary.items():
                    current_task.usage[k] = current_task.usage.get(k, 0) + v

            feedback_tool_use = next(
                filter(
                    lambda tu: tu["name"] == "provide_feedback",
                    feedback_iterator.tool_use
                ),
                None
            )
            if feedback_tool_use is None:
                current_task.consecutive_mistakes_count += 1
                current_task.save()
                continue
            if feedback_tool_use["input"].get("approve"):
                current_task.attempt_complete()
                current_task.save()
                return ToolResult(result=current_task.conversation[-1]["content"], error=None)
            elif feedback_tool_use["input"].get("discard"):
                current_task.status = TaskStatus.DISCARDED
                current_task.save()
                return ToolResult(result="Task is not longer relevant and was discarded", error=None)
            else:
                current_task.consecutive_mistakes_count += 1
                current_task.status = TaskStatus.AWAITING_INPUT
                shared["messages"].append({"role": "user", "content": feedback_tool_use["input"].get("feedback")})
                current_task.save()

        return ToolResult(result=None, error="Assigned task execution exhausted all completion attempts. Please try again with a different approach.")
