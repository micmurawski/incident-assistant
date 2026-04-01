"""Persist assignee shared ``messages`` keyed by assigner + assignee + session_id."""

from __future__ import annotations

import json
from datetime import datetime

from agent.persistence.model import SessionMessagesModel


def upsert_session_messages(
    assigner: str,
    assignee: str,
    session_id: str,
    messages: list[dict],
) -> None:
    payload = json.dumps(messages)
    row = {
        "assigner": assigner,
        "assignee": assignee,
        "session_id": session_id,
        "messages_json": payload,
    }
    SessionMessagesModel.insert(row).on_conflict(
        conflict_target=[
            SessionMessagesModel.assigner,
            SessionMessagesModel.assignee,
            SessionMessagesModel.session_id,
        ],
        update={**row, "updated_at": datetime.now()},
    ).execute()


def fetch_session_messages(
    assigner: str,
    assignee: str,
    session_id: str,
) -> list[dict] | None:
    try:
        row = SessionMessagesModel.get(
            (SessionMessagesModel.assigner == assigner)
            & (SessionMessagesModel.assignee == assignee)
            & (SessionMessagesModel.session_id == session_id)
        )
    except SessionMessagesModel.DoesNotExist:
        return None
    if not row.messages_json:
        return None
    return json.loads(row.messages_json)
