from typing import Annotated

from agent.llm import LLMAgent
from agent.tasks.executor import TaskExecutor
from agent.tasks.formatting import parse_markdown_checklist
from agent.tasks.tasks import Task
from agent.tooling.decorators import ToolResult

from .decorators import Hidden, Tools, tool


@tool(tags=["planning", "assign"])
async def assign_task(
    agent: Hidden[LLMAgent],
    task: Hidden[Task],
    assignee: Annotated[str, "The slug of the mode to start the new task in (e.g., {available_agents})"],
    message: Annotated[str, "The initial user message or instructions for this new task."],
    todos: Annotated[str, "The initial todo list in markdown checklist format for the new task."],
) -> ToolResult:
    """
    This will let you create a new task instance in the chosen mode using your provided message and initial todo list.

    Usage:
    assign_task(assignee="coder", message="Implement user authentication", todos="[ ] Set up auth middleware\n[ ] Create login endpoint\n[ ] Add session management\n[ ] Write tests")

    Example:
    assign_task(assignee="coder", message="Implement user authentication", todos="[ ] Set up auth middleware\n[ ] Create login endpoint\n[ ] Add session management\n[ ] Write tests")
    """

    return await TaskExecutor.assign_and_run(task=task, assigner_agent=agent, assignee=assignee, message=message, todos_str=todos, feedback_tools=Tools(tools=[provide_feedback]))


@tool(tags=["planning", "update_todo"])
async def update_todo(
    agent: Hidden[LLMAgent],
    task: Hidden[Task],
    todos: Annotated[str, "The updated todo list in markdown checklist format for the task."],
) -> ToolResult:
    """
    Replace the entire TODO list with an updated checklist reflecting the current state. Always provide the full list; the system will overwrite the previous one. This tool is designed for step-by-step task tracking, allowing you to confirm completion of each step before updating, update multiple task statuses at once (e.g., mark one as completed and start the next), and dynamically add new todos discovered during long or complex tasks.
    **Checklist Format:**
    - Use a single-level markdown checklist (no nesting or subtasks).
    - List todos in the intended execution order.
    - Status options:
             - [ ] Task description (pending)
             - [x] Task description (completed)
             - [-] Task description (in progress)

    **Status Rules:**
    - [ ] = pending (not started)
    - [x] = completed (fully finished, no unresolved issues)
    - [-] = in_progress (currently being worked on)

    **Core Principles:**
    - Before updating, always confirm which todos have been completed since the last update.
    - You may update multiple statuses in a single update (e.g., mark the previous as completed and the next as in progress).
    - When a new actionable item is discovered during a long or complex task, add it to the todo list immediately.
    - Do not remove any unfinished todos unless explicitly instructed.
    - Always retain all unfinished tasks, updating their status as needed.
    - Only mark a task as completed when it is fully accomplished (no partials, no unresolved dependencies).
    - If a task is blocked, keep it as in_progress and add a new todo describing what needs to be resolved.
    - Remove tasks only if they are no longer relevant or if the user requests deletion.

    **When to Use:**
    - The task is complicated or involves multiple steps or requires ongoing tracking.
    - You need to update the status of several todos at once.
    - New actionable items are discovered during task execution.
    - The user requests a todo list or provides multiple tasks.
    - The task is complex and benefits from clear, stepwise progress tracking.

    **When NOT to Use:**
    - There is only a single, trivial task.
    - The task can be completed in one or two simple steps.
    - The request is purely conversational or informational.

    **Task Management Guidelines:**
    - Mark task as completed immediately after all work of the current task is done.
    - Start the next task by marking it as in_progress.
    - Add new todos as soon as they are identified.
    - Use clear, descriptive task names.

    Usage:
    update_todo(todos=<updated todo list in markdown checklist format>)

    Example:
    update_todo(todos="[x] Analyze requirements\n[x] Design architecture\n[-] Implement core logic\n[ ] Write tests\n[ ] Update documentation]")

    *After completing "Implement core logic" and starting "Write tests":*

    update_todo(todos="[x] Analyze requirements\n[x] Design architecture\n[x] Implement core logic\n[-] Write tests\n[ ] Update documentation\n[ ] Add performance benchmarks")

    """
    task: Task
    task.todo_list = parse_markdown_checklist(todos)
    return ToolResult(result="TODO list updated", error=None)


@tool(tags=["planning", "feedback"])
async def provide_feedback(
    feedback: Annotated[str, "The feedback for the task."] = None,
    discard: Annotated[bool, "Whether to discard the task."] = False,
    approve: Annotated[bool, "Whether to approve the task."] = False,
) -> ToolResult:
    """
    Provide feedback on the task.

    Usage:
    provide_feedback(approve=True)
    provide_feedback(discard=True)
    provide_feedback(feedback="The task is not complete. Can you please try to make sure that second todo is finished?")
    """
    return ToolResult(result="", error=None)

PlanningTools = Tools(tools=[assign_task, update_todo])
