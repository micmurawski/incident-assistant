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
        "tool_usage": _loads(row.tool_usage, []),
        "usage": _loads(row.usage, {}),
        "created_at": row.created_at,
    }


def _build_task_dict(task_id: str, rows_by_id: dict[str, TaskModel]) -> dict:
    row = rows_by_id[task_id]
    child_ids = _loads(row.children, [])
    d = _row_to_dict(row)
    d["children"] = [_build_task_dict(cid, rows_by_id) for cid in child_ids if cid in rows_by_id]
    return d


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
