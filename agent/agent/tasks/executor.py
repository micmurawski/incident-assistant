
from agent.llm import AgentRegistry, ChunkProxyIterator, LLMAgent
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import ToolResult, Tools

FEEDBACK_SYSTEM_PROMPT = """
You are a feedback assistant. You are given a task and a feedback. You need to provide feedback on the task.
"""

TODO_LIST_PROMPT = """
Here is the todo list:
{todos_str}

Please provide feedback on the todo list.
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
    ) -> ToolResult:
        messages = [
            {
                "role": "user",
                "content": message + TODO_LIST_PROMPT.format(todos_str=todos_str)
            }
        ]
        current_task = parent_task.create_child_task(
            assignee=assignee,
            conversation=messages,
            todo_list_str=todos_str,
        )
        assignee_agent: LLMAgent = AgentRegistry.get_instance().get(assignee)
        assigner_agent: LLMAgent = AgentRegistry.get_instance().get(assigner)
        shared = {"task": current_task, "messages": current_task.conversation}

        for _ in range(parent_task.consecutive_mistakes_limit):
            await assignee_agent.call(shared=shared)
            current_task.status = TaskStatus.AWAITING_FEEDBACK
            current_task.conversation = shared["messages"]

            feedback_tools_definitions = feedback_tools.tools_definitions(
                format=assignee_agent.api_handler.provider,
                format_kwargs=assignee_agent.get_shared()
            )

            # How to elegantly add conversation trajectory fron assingner to feedback agent?

            feedback_iterator: ChunkProxyIterator = await assigner_agent.create_message(
                messages=current_task.get_conversation_with_swapped_roles(),
                metadata=None,
                tools=feedback_tools_definitions,
                system_prompt=FEEDBACK_SYSTEM_PROMPT,
            )

            async for _ in feedback_iterator:
                pass

            feedback_tool_use = next(
                filter(
                    lambda tu: tu["name"] == "provide_feedback",
                    feedback_iterator.tool_use
                ),
                None
            )
            if feedback_tool_use is None:
                parent_task.consecutive_mistakes_count += 1
                continue
            if feedback_tool_use["input"].get("approve"):
                current_task.attempt_complete()
                return ToolResult(result=current_task.conversation[-1]["content"], error=None)
            elif feedback_tool_use["input"].get("discard"):
                current_task.status = TaskStatus.DISCARDED
                return ToolResult(result="Task is not longer relevant and was discarded", error=None)
            else:
                parent_task.consecutive_mistakes_count += 1
                parent_task.status = TaskStatus.AWAITING_INPUT
                shared["messages"].append({"role": "user", "content": feedback_tool_use["input"].get("feedback")})
        return ToolResult(result=None, error="Assigned task execution exhausted all completion attempts. Please try again with a different approach.")
