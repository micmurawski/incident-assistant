#!/usr/bin/env python3
"""Align root task timestamps in SQLite with fault_history.yaml order.

Reads ``history`` entries in file order. For each consecutive pair, the step
between new root ``created_at`` values is ``abs(original[i+1] - original[i])``,
and ``new[0] = original[0]``. That preserves the magnitude of separation between
each pair (including when the DB order was inverted relative to YAML).

For every root id, all tasks under that ``root_id`` get the same delta applied
to ``created_at``, ``updated_at``, and ``resolved_at`` (see
``experiment_runner_backfill.shift_timestamps``).

Usage (from repo root, default paths):
  PYTHONPATH=agent python3 agent/episodes_runner/shift_fault_history_timestamps.py \\
    --db agent_no_learning.db \\
    --fault-history agent/episodes_runner/fault_history.yaml
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def _shift_task_tree_timestamps(
    db_path: str, root_id: str, target_created_at: str
) -> None:
    """Same semantics as experiment_runner_backfill.shift_timestamps."""
    ts_cols = ("created_at", "updated_at", "resolved_at")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, created_at, updated_at, resolved_at FROM tasks WHERE root_id = ?",
        (root_id,),
    ).fetchall()
    if not rows:
        conn.close()
        raise RuntimeError(f"No tasks with root_id={root_id!r} in {db_path}")

    root_row = next((r for r in rows if r["id"] == root_id), None)
    if not root_row:
        conn.close()
        raise RuntimeError(f"Root task {root_id!r} not found in {db_path}")

    actual = datetime.fromisoformat(root_row["created_at"])
    target = datetime.fromisoformat(target_created_at)
    delta = target - actual

    for row in rows:
        updates = {}
        for col in ts_cols:
            val = row[col]
            if val is not None:
                updates[col] = (datetime.fromisoformat(val) + delta).isoformat(sep=" ")
        if updates:
            set_clause = ", ".join(f"{c} = ?" for c in updates)
            conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE root_id = ? AND id = ?",
                (*updates.values(), root_id, row["id"]),
            )

    conn.commit()
    conn.close()


def load_fault_history_entries(path: Path) -> list[dict]:
    """Parse minimal fault_history.yaml (no PyYAML dependency).

    Line-based so the last entry is included even when the file ends with a
    blank line (regex lookaheads could skip it).
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].strip().startswith("history:"):
        raise ValueError(f"Expected top-level 'history:' in {path}")
    entries: list[dict] = []
    i = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("- class_id:"):
            class_id = int(stripped.split(":", 1)[1].strip())
            i += 1
            d: dict = {"class_id": class_id}
            while i < len(lines):
                sline = lines[i].strip()
                if sline.startswith("- class_id:"):
                    break
                if not sline:
                    i += 1
                    continue
                if ":" in sline:
                    key, val = sline.split(":", 1)
                    d[key.strip()] = val.strip()
                i += 1
            entries.append(d)
        else:
            i += 1
    if not entries:
        raise ValueError(f"No history entries parsed from {path}")
    required = ("class_id", "id", "service_name", "status")
    for j, e in enumerate(entries):
        missing = [k for k in required if k not in e]
        if missing:
            raise ValueError(f"Entry {j} missing keys {missing}")
    return entries


def fault_history_playbook_revision_1based(fault_id: str, path: Path) -> int:
    """Playbook revision to pin for replay, aligned with ``experiment_runner.run_experiment``.

    At the start of each experiment, ``episode_count`` is the number of rows already in
    ``fault_history.yaml``. ACE runs when ``episode_count > 0``, ``episode_count % 5 == 0``,
    and the revision floor is not met; each successful run adds one revision per assignee.

    The revision in effect **during** the episode that occupies **0-based index** *i* in
    ``history`` (file order) is ``1 + i // 5``: episodes 0–4 use revision 1, 5–9 use 2,
    …, 40–44 use 9 (e.g. last of 45 episodes → revision 9).

    See ``experiment_runner._should_run_ace_pipeline`` and ``expected_floor``.
    """
    entries = load_fault_history_entries(path)
    for i, e in enumerate(entries):
        if e["id"] == fault_id:
            return 1 + i // 5
    raise ValueError(f"Fault id {fault_id!r} not found in {path}")


def render_fault_history(entries: list[dict]) -> str:
    lines = ["history:"]
    for e in entries:
        lines.append(f"- class_id: {e['class_id']}")
        lines.append(f"  id: {e['id']}")
        lines.append(f"  service_name: {e['service_name']}")
        lines.append(f"  status: {e['status']}")
        if "created_at" in e:
            lines.append(f"  created_at: {e['created_at']}")
    return "\n".join(lines) + "\n"


def compute_ordered_root_times(
    ordered_ids: list[str], root_created: dict[str, datetime]
) -> list[datetime]:
    o = [root_created[i] for i in ordered_ids]
    new = [o[0]]
    for i in range(len(o) - 1):
        new.append(new[i] + abs(o[i + 1] - o[i]))
    return new


def fetch_root_created_at(conn: sqlite3.Connection, root_id: str) -> datetime:
    row = conn.execute(
        "SELECT created_at FROM tasks WHERE root_id = ? AND id = ?",
        (root_id, root_id),
    ).fetchone()
    if not row:
        raise RuntimeError(
            f"No root row (id = root_id) for {root_id!r} — run against the tasks DB "
            "that contains these episodes."
        )
    return datetime.fromisoformat(row[0])


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db",
        type=Path,
        default=Path("agent_no_learning.db"),
        help="SQLite DB with tasks table (default: ./agent_no_learning.db)",
    )
    p.add_argument(
        "--fault-history",
        type=Path,
        default=Path(__file__).resolve().parent / "fault_history.yaml",
        help="Path to fault_history.yaml",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned shifts only; do not modify DB or YAML",
    )
    p.add_argument(
        "--skip-yaml",
        action="store_true",
        help="Update DB only; do not write fault_history.yaml",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    entries = load_fault_history_entries(args.fault_history)
    ordered_ids = [e["id"] for e in entries]

    conn = sqlite3.connect(args.db)
    try:
        root_created = {fid: fetch_root_created_at(conn, fid) for fid in ordered_ids}
    finally:
        conn.close()

    new_times = compute_ordered_root_times(ordered_ids, root_created)

    for i, fid in enumerate(ordered_ids):
        old = root_created[fid]
        new = new_times[i]
        delta = new - old
        print(f"{i:2d} {fid[:56]:<56}  {old}  ->  {new}  (delta {delta})")

    if args.dry_run:
        print("\nDry run: no files modified.")
        return

    for i, fid in enumerate(ordered_ids):
        target = new_times[i].isoformat(sep=" ")
        _shift_task_tree_timestamps(str(args.db), fid, target)

    if not args.skip_yaml:
        out_entries = []
        for i, e in enumerate(entries):
            row = dict(e)
            row["created_at"] = new_times[i].isoformat(sep=" ")
            out_entries.append(row)
        args.fault_history.write_text(
            render_fault_history(out_entries), encoding="utf-8"
        )
        print(f"\nWrote {args.fault_history} with created_at on each entry.")

    print(f"\nUpdated task timestamps in {args.db} for {len(ordered_ids)} roots.")


if __name__ == "__main__":
    main()
