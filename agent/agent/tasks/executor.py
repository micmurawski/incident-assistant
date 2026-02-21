from agent.llm import AgentRegistry, ChunkProxyIterator, LLMAgent
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import ToolResult, Tools


class TaskExecutor:
    @staticmethod
    async def assign_and_run(task: Task, assigner_agent: LLMAgent, assignee: str, message: str, todos_str: str, feedback_tools: Tools) -> ToolResult:
        message = f"\n Here is the todo list: \n{todos_str}\n\n Please when you finish your work report back."

        _input_messages = [
            {
                "role": "user",
                "content": message,
            }
        ]
        current_task = task.create_child_task(
            assignee=assignee,
            conversation=_input_messages,
            todo_list_str=todos_str,
        )
        assignee_agent: LLMAgent = AgentRegistry.get_instance().get(assignee)
        shared = {"task": current_task, "messages": current_task.conversation}

        for _ in range(task.consecutive_mistakes_limit):
            await assignee_agent.call(shared=shared)
            current_task.status = TaskStatus.AWAITING_FEEDBACK
            # find last assistant message
            filtered_messages = [msg for msg in shared["messages"] if msg["role"]
                                 == "assistant" and isinstance(msg.get("content"), str)]
            if len(filtered_messages) == 0:
                raise ValueError("No assistant message found")

            current_task.conversation += [{"role": "assistant", "content": msg["content"]} for msg in filtered_messages]
            print("NOW ITS TIME TO PROVIDE FEEDBACK")
            print("THIS IS THE CONVERSATION: ")
            for msg in current_task.get_conversation_with_swapped_roles():
                print(msg["role"], ":", msg["content"])

            print("THIS IS TODO LIST: ")
            print(current_task.get_todo_str())

            prompt = """
            Now is your turn to provide feedback on the task. Use feedback tool to provide feedback.
            """
            feedback_tools_definitions = feedback_tools.tools_definitions(format=assignee_agent.api_handler.provider)
            feedback_iterator: ChunkProxyIterator = await assigner_agent.create_message(
                messages=current_task.get_conversation_with_swapped_roles(), metadata=None, tools=feedback_tools_definitions, system_prompt=prompt
            )
            async for _ in feedback_iterator:
                pass

            feedback_tool_use = next(filter(lambda tu: tu["name"] ==
                                     "provide_feedback", feedback_iterator.tool_use), None)
            print("FEEDBACK TOOL USE: ", feedback_tool_use)
            if feedback_tool_use is None:
                raise ValueError("No feedback tool use found")
            if feedback_tool_use["input"].get("approve"):
                current_task.attempt_complete()
                return ToolResult(result=current_task.conversation[-1]["content"], error=None)
            elif feedback_tool_use["input"].get("discard"):
                current_task.status = TaskStatus.DISCARDED
                return ToolResult(result="Task is not longer relevant and was discarded", error=None)
            else:
                task.consecutive_mistakes_count += 1
                current_task.add_feedback(feedback=feedback_tool_use["input"].get("feedback"))
            return ToolResult(result=None, error="Assigned task execution exhausted all completion attempts. Please try again with a different approach.")
