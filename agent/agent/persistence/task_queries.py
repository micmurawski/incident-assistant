"""Read tasks from the persistence layer (Peewee / SQLite).

Root tasks are rows where ``id == root_id`` (one persisted row per top-level task).
``fetch_last_root_tasks`` never returns standalone child tasks as list entries.
"""

from __future__ import annotations

import json

from agent.persistence.model import TaskModel
from agent.persistence.settings import init_db
from agent.tasks.tasks import Task


def _loads(raw: str, default):
    if not raw:
        return default
    return json.loads(raw)


def _row_to_dict(row: TaskModel) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "todo_list": _loads(row.todo_list, []),
        "assignee": row.assignee or None,
        "assigner": row.assigner or None,
        "conversation": _loads(row.conversation, []),
        "messages_history": _loads(row.messages_history, []),
        "iterations_count": row.iterations_count,
        "iterations_limit": row.iterations_limit,
        "total_usage": _loads(row.total_usage, {}),
        "usage": _loads(row.usage, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "resolved_at": row.resolved_at,
    }


def _build_task_dict(task_id: str, rows_by_id: dict[str, TaskModel]) -> dict:
    row = rows_by_id[task_id]
    child_ids = _loads(row.children, [])
    d = _row_to_dict(row)
    d["children"] = [_build_task_dict(cid, rows_by_id) for cid in child_ids if cid in rows_by_id]
    return d


def fetch_first_root_tasks(first_n: int = 2) -> list[Task]:
    """
    Return the ``first_n`` **root** task trees (full hierarchies), **not** child rows.
    """
    if first_n <= 0:
        return []

    init_db()
    
    roots = (
        TaskModel.select()
        .where(TaskModel.id == TaskModel.root_id)
        .order_by(TaskModel.created_at.asc())
        .limit(first_n)
    )

    result: list[Task] = []
    for root in roots:
        all_rows = TaskModel.select().where(TaskModel.root_id == root.root_id)
        rows_by_id = {r.id: r for r in all_rows}
        if root.id not in rows_by_id:
            continue
        payload = _build_task_dict(root.id, rows_by_id)
        result.append(Task.from_dict(payload))
    return result


def fetch_last_root_tasks(last_n: int = 2) -> list[Task]:
    """
    Return the ``last_n`` **root** task trees (full hierarchies), **not** child rows.

    Selection: rows with ``id == root_id`` only. Order: root row ``updated_at``
    descending (most recently touched roots first). Each returned ``Task`` includes
    nested children restored from the DB.
    """
    if last_n <= 0:
        return []

    init_db()

    roots = (
        TaskModel.select()
        .where(TaskModel.id == TaskModel.root_id)
        .order_by(TaskModel.updated_at.desc())
        .limit(last_n)
    )

    result: list[Task] = []
    for root in roots:
        all_rows = TaskModel.select().where(TaskModel.root_id == root.root_id)
        rows_by_id = {r.id: r for r in all_rows}
        if root.id not in rows_by_id:
            continue
        payload = _build_task_dict(root.id, rows_by_id)
        result.append(Task.from_dict(payload))

    return result


def fetch_tasks_by_assignee(n: int = 2, last: bool = True) -> dict[str, list[Task]]:
    """
    Fetch all tasks for the n recent or oldest root_ids (root tasks), and map tasks to each assignee.
    This gives {"incident_commander": [Task, ...], "sre_agent": [Task, ...], ...}, 
    where each list includes *all tasks* (root and child) for the selected root_ids, 
    and each Task object is built with its full child hierarchy.
    """
    init_db()

    # Step 1: Fetch n root-ids (most recent or oldest roots)
    root_qs = TaskModel.select(TaskModel.root_id).where(TaskModel.id == TaskModel.root_id)
    if last:
        root_qs = root_qs.order_by(TaskModel.updated_at.desc()).limit(n)
    else:
        root_qs = root_qs.order_by(TaskModel.created_at.asc()).limit(n)
    root_ids = [row.root_id for row in root_qs]
    if not root_ids:
        return {}

    # Step 2: Get all TaskModel rows for these root_ids
    all_task_rows = list(TaskModel.select().where(TaskModel.root_id << root_ids))

    # Step 3: Organize all rows by root, then by id
    rows_by_root: dict[str, dict[str, TaskModel]] = {}
    for row in all_task_rows:
        rows_by_root.setdefault(row.root_id, {})[row.id] = row

    # Step 4: Build each root+hierarchy, distributing to each assignee's list
    result: dict[str, list[Task]] = {}
    for root_id in root_ids:
        # Find the actual root row, skip if broken
        root_row = rows_by_root.get(root_id, {}).get(root_id)
        if not root_row:
            continue
        task_dict = _build_task_dict(root_id, rows_by_root[root_id])
        root_task = Task.from_dict(task_dict)
        # Walk the full task hierarchy to collect all assignees
        stack = [root_task]
        while stack:
            task = stack.pop()
            assignee = getattr(task, "assignee", None)
            if assignee:
                result.setdefault(assignee, []).append(task)
            # Support both .children and list of children as attribute
            children = getattr(task, "children", [])
            if children:
                stack.extend(children)
    return result
 