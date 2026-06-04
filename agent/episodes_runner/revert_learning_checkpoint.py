#!/usr/bin/env python3
"""Revert learning artifacts to a chosen completed fault (checkpoint).

Aligns with ``experiment_runner.run_experiment`` + ACE layout:

1. **SQLite** — deletes every ``tasks`` row whose ``root_id`` appears in
   ``fault_history.yaml`` *after* the checkpoint fault (same order as the file).
2. **fault_history.yaml** — truncates ``history`` so the last entry is the
   checkpoint fault (preserves ``created_at`` on kept rows when present).
3. **agent/ace/playbook_history/** — for each assignee, keeps the first *K*
   ``{assignee}-*.json`` files (sorted by filename) and deletes the rest.
   *K* = ``1 + index // 5`` for the checkpoint fault's 0-based *index* in
   history (see ``fault_history_playbook_revision_1based``).
4. **agent/ace/prompts/** — removes numeric revision directories ``K``,
   ``K+1``, …, ``N-1`` where *N* is the maximum on-disk playbook JSON count
   across assignees (the folders used by reflector/curator for ACE rounds that
   produced deleted revisions). Does **not** touch ``agent/ace/prompts_gpt_5_nano_100``.

``session_messages`` is not modified (no ``root_id`` column; optional manual cleanup).

Usage (from repo root):

  PYTHONPATH=agent python3 agent/episodes_runner/revert_learning_checkpoint.py \\
    --fault-id fault-2-cart-515a8a54-c8e1-4861-9691-474d6b05f6d4

Dry-run (default): prints planned actions. To execute:

  PYTHONPATH=agent python3 agent/episodes_runner/revert_learning_checkpoint.py \\
    --fault-id fault-2-cart-515a8a54-c8e1-4861-9691-474d6b05f6d4 \\
    --apply --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from episodes_runner.shift_fault_history_timestamps import (
    fault_history_playbook_revision_1based,
    load_fault_history_entries,
    render_fault_history,
)

ACE_ASSIGNEES = (
    "incident_commander",
    "monitoring_agent",
    "devops_agent",
    "coder_agent",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _checkpoint_index(entries: list[dict], fault_id: str) -> int:
    for i, e in enumerate(entries):
        if e["id"] == fault_id:
            return i
    raise ValueError(f"Fault id {fault_id!r} not found in fault history")


def _collect_playbook_deletes(playbook_history: Path, keep_n: int) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for aid in ACE_ASSIGNEES:
        files = sorted(playbook_history.glob(f"{aid}-*.json"), key=lambda p: p.name)
        if len(files) > keep_n:
            out[aid] = files[keep_n:]
        else:
            out[aid] = []
    return out


def _max_playbook_file_count(playbook_history: Path) -> int:
    m = 0
    for aid in ACE_ASSIGNEES:
        n = len(list(playbook_history.glob(f"{aid}-*.json")))
        m = max(m, n)
    return m


def main() -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fault-id",
        required=True,
        help="Checkpoint fault id (must exist in fault_history.yaml).",
    )
    parser.add_argument(
        "--fault-history",
        type=Path,
        default=root / "agent" / "episodes_runner" / "fault_history.yaml",
        help="Path to fault_history.yaml",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=root / "agent.db",
        help="Path to SQLite DB (tasks table)",
    )
    parser.add_argument(
        "--playbook-history",
        type=Path,
        default=root / "agent" / "ace" / "playbook_history",
        help="Directory with {assignee}-*.json playbook revisions",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=root / "agent" / "ace" / "prompts",
        help="ACE prompts dir (numeric revision subfolders only; never prompts_gpt_5_nano_100)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform deletions and YAML rewrite (default is dry-run)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="With --apply, skip interactive confirmation",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Do not delete tasks from SQLite",
    )
    parser.add_argument(
        "--skip-fault-history",
        action="store_true",
        help="Do not truncate fault_history.yaml",
    )
    parser.add_argument(
        "--skip-ace",
        action="store_true",
        help="Do not delete playbook JSON or prompt revision folders",
    )
    args = parser.parse_args()

    fh_path: Path = args.fault_history
    entries = load_fault_history_entries(fh_path)
    idx = _checkpoint_index(entries, args.fault_id)
    keep_playbooks = fault_history_playbook_revision_1based(args.fault_id, fh_path)
    later_roots = [e["id"] for e in entries[idx + 1 :]]

    n_files = _max_playbook_file_count(args.playbook_history)
    playbook_drops = _collect_playbook_deletes(args.playbook_history, keep_playbooks)
    prompt_dirs: list[Path] = []
    if n_files > keep_playbooks:
        for d in range(keep_playbooks, n_files):
            p = args.prompts_dir / str(d)
            if p.is_dir():
                prompt_dirs.append(p)

    print(f"Checkpoint fault: {args.fault_id}")
    print(f"  0-based history index: {idx}")
    print(f"  Playbook JSON files to keep per assignee: {keep_playbooks}")
    print(f"  Max playbook JSON count on disk: {n_files}")
    print(f"  History entries after checkpoint (DB + YAML): {len(later_roots)}")
    if later_roots:
        for rid in later_roots:
            print(f"    - {rid}")

    pb_total = sum(len(v) for v in playbook_drops.values())
    print(f"\nPlaybook JSON files to delete: {pb_total}")
    for aid, paths in playbook_drops.items():
        for p in paths:
            print(f"    {p.relative_to(root)}")

    print(f"\nPrompt revision dirs to delete ({len(prompt_dirs)}):")
    for p in prompt_dirs:
        n_files_under = sum(1 for _ in p.rglob("*") if _.is_file())
        print(f"    {p.relative_to(root)}  ({n_files_under} files)")

    if not args.skip_db and args.db.is_file():
        conn = sqlite3.connect(str(args.db))
        try:
            qmarks = ",".join("?" * len(later_roots)) if later_roots else ""
            if later_roots:
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM tasks WHERE root_id IN ({qmarks})",
                    later_roots,
                )
                n_tasks = cur.fetchone()[0]
            else:
                n_tasks = 0
        finally:
            conn.close()
        print(f"\nSQLite tasks rows to delete: {n_tasks}  (db={args.db})")
    elif not args.skip_db:
        print(f"\nSQLite: skip (db not found: {args.db})")

    if not args.skip_fault_history:
        kept = idx + 1
        print(f"\nfault_history.yaml: truncate to {kept} entries (from {len(entries)})")
    else:
        print("\nfault_history.yaml: skipped")

    if not args.apply:
        print("\n[DRY-RUN] Pass --apply --yes to execute.")
        return 0

    if not args.yes:
        print("\nAborted: --apply requires --yes (confirmation).", file=sys.stderr)
        return 2

    if not args.skip_db and args.db.is_file() and later_roots:
        conn = sqlite3.connect(str(args.db))
        try:
            qmarks = ",".join("?" * len(later_roots))
            conn.execute(f"DELETE FROM tasks WHERE root_id IN ({qmarks})", later_roots)
            conn.commit()
            print(f"\nDeleted tasks for {len(later_roots)} root_id(s).")
        finally:
            conn.close()
    elif not args.skip_db and later_roots:
        print(f"\nDB missing, skip delete: {args.db}")

    if not args.skip_fault_history:
        truncated = entries[: idx + 1]
        fh_path.write_text(render_fault_history(truncated), encoding="utf-8")
        print(f"Wrote truncated fault history ({len(truncated)} entries).")

    if not args.skip_ace:
        for paths in playbook_drops.values():
            for p in paths:
                p.unlink(missing_ok=True)
        print(f"Removed {pb_total} playbook_history JSON file(s).")

        for p in prompt_dirs:
            shutil.rmtree(p, ignore_errors=False)
        print(f"Removed {len(prompt_dirs)} prompt revision director(ies).")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
