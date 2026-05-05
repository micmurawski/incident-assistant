#!/usr/bin/env python3
import argparse
import json
import sqlite3
from typing import Optional


DEFAULT_SUCCESS_METRICS = {
    "root_cause_analysis": 0,
    "successful_fix": 0,
    "system_recovery_visible": 0,
}


def _normalize_success_metrics(raw: dict) -> dict:
    return {
        "root_cause_analysis": int(raw.get("root_cause_analysis", 0)),
        "successful_fix": int(raw.get("successful_fix", 0)),
        "system_recovery_visible": int(raw.get("system_recovery_visible", 0)),
    }


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None

    candidates = []
    if "```json" in text:
        part = text.split("```json")[-1]
        candidates.append(part.split("```")[0].strip())
    candidates.append(text.strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        for idx, ch in enumerate(candidate):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _merge_scores(existing_content: str, rca: Optional[int], successful_fix: Optional[int], recovery_visible: Optional[int]) -> str:
    extracted = _extract_json_object(existing_content)
    scores = dict(DEFAULT_SUCCESS_METRICS)
    if isinstance(extracted, dict):
        scores.update(_normalize_success_metrics(extracted))

    if rca is not None:
        scores["root_cause_analysis"] = int(rca)
    if successful_fix is not None:
        scores["successful_fix"] = int(successful_fix)
    if recovery_visible is not None:
        scores["system_recovery_visible"] = int(recovery_visible)

    return json.dumps(scores, indent=2)


def _extract_content_as_text(message: dict) -> str:
    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        )
    if isinstance(content, str):
        return content
    return str(content)


def amend_root_task_scores(db_path: str, task_id: str, rca: Optional[int], successful_fix: Optional[int], recovery_visible: Optional[int], dry_run: bool) -> bool:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT rowid, id, parent, conversation
        FROM tasks
        WHERE id = ?
        LIMIT 1
        """,
        (task_id,),
    )
    row = cursor.fetchone()
    if not row:
        print(f"[ERROR] Task not found: {task_id}")
        conn.close()
        return False

    if row["parent"] not in (None, ""):
        print(f"[WARN] Task {task_id} is not a root task (parent={row['parent']}). Proceeding anyway.")

    try:
        conversation = json.loads(row["conversation"])
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid conversation JSON for task: {task_id}")
        conn.close()
        return False

    if not isinstance(conversation, list) or not conversation:
        print(f"[ERROR] Empty conversation for task: {task_id}")
        conn.close()
        return False

    last = conversation[-1]
    if not isinstance(last, dict):
        print(f"[ERROR] Last conversation message is not an object for task: {task_id}")
        conn.close()
        return False

    old_content = _extract_content_as_text(last)
    old_scores = _extract_json_object(old_content) or {}
    new_content = _merge_scores(old_content, rca, successful_fix, recovery_visible)
    new_scores = _extract_json_object(new_content) or {}

    print(f"[INFO] Task: {task_id}")
    print(f"       old: {json.dumps(_normalize_success_metrics(old_scores), separators=(',', ':'))}")
    print(f"       new: {json.dumps(_normalize_success_metrics(new_scores), separators=(',', ':'))}")

    if dry_run:
        print("[INFO] Dry-run enabled. No DB changes written.")
        conn.close()
        return True

    # Keep message shape simple/compatible with parser in analyze_tasks.py.
    last["content"] = new_content
    conversation[-1] = last

    cursor.execute(
        "UPDATE tasks SET conversation = ?, updated_at = CURRENT_TIMESTAMP WHERE rowid = ?",
        (json.dumps(conversation), row["rowid"]),
    )
    conn.commit()
    conn.close()
    print("[OK] Conversation score payload updated.")
    return True


def find_root_tasks_by_scores(
    db_path: str,
    rca: int,
    successful_fix: Optional[int],
    recovery_visible: int,
) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, conversation
        FROM tasks
        WHERE root_id = id
        """
    )
    rows = cursor.fetchall()
    conn.close()

    matches: list[str] = []
    for row in rows:
        try:
            conversation = json.loads(row["conversation"])
        except json.JSONDecodeError:
            continue
        if not isinstance(conversation, list) or not conversation:
            continue
        last = conversation[-1]
        content = _extract_content_as_text(last if isinstance(last, dict) else {})
        parsed = _extract_json_object(content)
        if not isinstance(parsed, dict):
            continue

        normalized = _normalize_success_metrics(parsed)
        if normalized.get("root_cause_analysis", 0) != rca:
            continue
        if successful_fix is not None and normalized.get("successful_fix", 0) != successful_fix:
            continue
        if normalized.get("system_recovery_visible", 0) != recovery_visible:
            continue
        matches.append(row["id"])
    return matches


def amend_tasks_to_zero(db_path: str, task_ids: list[str], dry_run: bool) -> bool:
    if not task_ids:
        print("[INFO] No matching tasks found.")
        return True

    print(f"[INFO] Matching tasks: {len(task_ids)}")
    ok = True
    for task_id in task_ids:
        task_ok = amend_root_task_scores(
            db_path=db_path,
            task_id=task_id,
            rca=0,
            successful_fix=0,
            recovery_visible=0,
            dry_run=dry_run,
        )
        ok = ok and task_ok
    return ok


def _score_arg(value: str) -> int:
    ivalue = int(value)
    if ivalue not in (0, 1):
        raise argparse.ArgumentTypeError("score values must be 0 or 1")
    return ivalue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Amend root task success scores in tasks.conversation final message."
    )
    parser.add_argument("--db", default="./agent.db", help="Path to sqlite DB (default: ./agent.db)")
    parser.add_argument("--task-id", help="Task ID to amend")
    parser.add_argument(
        "--batch-root-rca0-recovery1-to-zero",
        action="store_true",
        help=(
            "Bulk amend root tasks (root_id=id) where root_cause_analysis=0 and "
            "system_recovery_visible=1, setting all scores to 0."
        ),
    )
    parser.add_argument(
        "--match-successful-fix",
        type=_score_arg,
        help="Optional extra filter for batch mode: successful_fix must match 0/1.",
    )
    parser.add_argument("--rca", type=_score_arg, help="Value for root_cause_analysis (0/1)")
    parser.add_argument("--successful-fix", type=_score_arg, help="Value for successful_fix (0/1)")
    parser.add_argument(
        "--recovery-visible",
        type=_score_arg,
        help="Value for system_recovery_visible (0/1)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing DB")

    args = parser.parse_args()

    if args.batch_root_rca0_recovery1_to_zero:
        task_ids = find_root_tasks_by_scores(
            db_path=args.db,
            rca=0,
            successful_fix=args.match_successful_fix,
            recovery_visible=1,
        )
        ok = amend_tasks_to_zero(args.db, task_ids, args.dry_run)
        raise SystemExit(0 if ok else 1)

    if not args.task_id:
        raise SystemExit("Task ID is required unless running batch mode.")
    if args.rca is None and args.successful_fix is None and args.recovery_visible is None:
        raise SystemExit("No score values provided. Use one or more of: --rca --successful-fix --recovery-visible")

    ok = amend_root_task_scores(
        db_path=args.db,
        task_id=args.task_id,
        rca=args.rca,
        successful_fix=args.successful_fix,
        recovery_visible=args.recovery_visible,
        dry_run=args.dry_run,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
