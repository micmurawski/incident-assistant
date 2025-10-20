from typing import Annotated, Optional

from .decorators import Tools, tool


@tool(tags=["planning"])
async def new_task(
    assignee: Annotated[str, "The slug of the mode to start the new task in (e.g., {available_agents})"],
    message: Annotated[str, "The initial user message or instructions for this new task."],
    todos: Annotated[str, "The initial todo list in markdown checklist format for the new task."],
) -> str:
    """
    This will let you create a new task instance in the chosen mode using your provided message and initial todo list.

    Usage:
    new_task(assignee="code", message="Implement user authentication", todos="[ ] Set up auth middleware\n[ ] Create login endpoint\n[ ] Add session management\n[ ] Write tests")

    Example:
    new_task(assignee="code", message="Implement user authentication", todos="[ ] Set up auth middleware\n[ ] Create login endpoint\n[ ] Add session management\n[ ] Write tests")
    """

    return "This is a test response"


@tool(tags=["planning"])
async def reassign_task(
    assignee: Annotated[str, "The slug of the mode to reassign the task to (e.g., {available_agents})"],
    reason: Annotated[Optional[str], "The reason for reassigning the task"] = None,
) -> str:
    """
    This will let you reassign a task instance to a different mode.
    Usage:
    reassign_task(assignee=<assignee slug>, reason=<reason for reassigning the task>)

    Example:
    reassign_task(assignee="coder", reason="Need to make code changes")
    """
    return "This is a test response"


@tool(tags=["planning"])
async def update_todo_list(
    todos: Annotated[str, "The updated todo list in markdown checklist format for the task."],
) -> str:
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
    update_todo_list(todos=<updated todo list in markdown checklist format>)

    Example:
    update_todo_list(todos="[x] Analyze requirements\n[x] Design architecture\n[-] Implement core logic\n[ ] Write tests\n[ ] Update documentation]")

    *After completing "Implement core logic" and starting "Write tests":*

    update_todo_list(todos="[x] Analyze requirements\n[x] Design architecture\n[x] Implement core logic\n[-] Write tests\n[ ] Update documentation\n[ ] Add performance benchmarks")

    """
    return "This is a test response"


PlanningTools = Tools(tools=[new_task, reassign_task, update_todo_list])
