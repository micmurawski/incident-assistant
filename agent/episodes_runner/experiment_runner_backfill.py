"""Run a single episode against a specific fault with a pinned playbook revision.

Usage:
    python3 -u agent/episodes_runner/experiment_runner_backfill.py \
        --fault fault-1-shipping-chaos_http_abort-76a8908fc8db482bbeade60b592b96fb \
        --playbook-revision 1 \
        --db ./agent_no_learning.db \
        --target-created-at "2026-04-09 13:48:00"
"""

import argparse
import asyncio
import os
import sqlite3
import uuid
from datetime import datetime

from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import Tools
from episodes_runner.episode_runner import (detect_differences,
                                            ensure_load_gen_deployed,
                                            format_diff_status_report,
                                            get_metrics_summary, run_episode)
from episodes_runner.runner import delete_chaos_mesh_all_experiments
from episodes_runner.sre_agent import configure_settings, create_sre_agent
from episodes_runner.utils import (clean_all_containers,
                                   collect_meaningful_actions, live_timer,
                                   restore_eks_node_group)

SRE_AGENT_CALL_TIMEOUT_SEC = float(os.environ.get("SRE_AGENT_TIMEOUT_SEC", "4000"))

JUDGE_SYSTEM_PROMPT = """
You are a Senior SRE Judge. Your role is to evaluate if an SRE Agent successfully resolved an incident.
You have access to:
1. The conversation history (including text-based representations of tool actions).
2. System metrics before and after the attempt.
3. System Execution Evidence (Ground Truth of which tools were actually executed by the framework).

Your evaluation must be grounded in evidence. If the agent claims to have fixed a file or deployed a change, but the "System Execution Evidence" does not show the corresponding tool call, you must consider the action as not performed.

Criteria:
- root_cause_analysis: 1 if the agent correctly identified the specific failure (e.g., the exact bug in a file or the misconfigured parameter), 0 otherwise.
- successful_fix: 1 if the agent applied a correct fix AND triggered a deployment (deploy_app or kubectl_apply or scale_node_group or any other tool that is relevant for the incident), 0 otherwise.
    - assess files changes, if correct file was modified in correct place it needs to be correct fix, but not exactly the same code as before the incident, if not it needs to be 0.
    - assess deployment, if deployment was triggered and it was successful, 0 otherwise.
- system_recovery_visible: 1 if the metrics report clearly shows the system returned to a healthy state, 0 otherwise.
    - if 5XX are visible in metrics put it as 0.
    - assess all metrics, if CPU, memory usage or any other metric is lower than before the incident, 0 otherwise.
"""


def create_judge_agent(provider: str = "minimax"):
    configure_settings("sre-agent", provider)
    judge_agent = LLMAgent(
        name="judge_agent",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        tools=Tools(tools=[]),
    )
    return judge_agent


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a single backfill episode with a pinned playbook revision."
    )
    parser.add_argument(
        "--fault",
        required=True,
        help="Fault directory name inside fault-vault (e.g. fault-1-shipping-chaos_http_abort-...)",
    )
    parser.add_argument(
        "--playbook-revision",
        type=int,
        default=None,
        help="1-based playbook revision to use (default: latest)",
    )
    parser.add_argument(
        "--db",
        default="./agent_no_learning.db",
        help="Path to the target SQLite database (default: ./agent_no_learning.db)",
    )
    parser.add_argument(
        "--target-created-at",
        default=None,
        help=(
            "ISO datetime for the root task's created_at (e.g. '2026-04-09 13:48:00'). "
            "All task timestamps in the tree are shifted by the same delta. "
            "Omit to keep real wall-clock times."
        ),
    )
    return parser.parse_args()


def shift_timestamps(db_path: str, root_id: str, target_created_at: str):
    """Shift created_at, updated_at, resolved_at for every task in the tree
    so that the root's created_at lands on *target_created_at*.

    Arithmetic is done in Python to preserve microsecond precision and
    maintain exact deltas between the three timestamp columns.
    """
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
        raise RuntimeError(f"Root task {root_id} not found in {db_path}")

    actual = datetime.fromisoformat(root_row["created_at"])
    target = datetime.fromisoformat(target_created_at)
    delta = target - actual
    print(f"Shifting timestamps by {delta}  ({actual} -> {target})")

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

    print("Shifted timestamps:")
    for row in conn.execute(
        "SELECT id, created_at, updated_at, resolved_at FROM tasks "
        "WHERE root_id = ? ORDER BY created_at",
        (root_id,),
    ).fetchall():
        print(
            f"  {row['id']}\n"
            f"    created  = {row['created_at']}\n"
            f"    updated  = {row['updated_at']}\n"
            f"    resolved = {row['resolved_at']}"
        )
    conn.close()


async def run_backfill(
    fault: str,
    playbook_revision: int | None,
    db_path: str,
    target_created_at: str | None,
):
    settings = SettingsManager.get_instance()
    settings.set("persistence.url", db_path)
    init_db()
    print(f"Database: {db_path}")
    print(f"Fault:    {fault}")
    print(f"Playbook revision: {playbook_revision or 'latest'}")
    if target_created_at:
        print(f"Target created_at: {target_created_at}")

    await ensure_load_gen_deployed()
    episode = await run_episode(selected_fault=fault)

    goal = Task.create_root_task(
        id=episode["fault_id"],
        assignee="incident_commander",
        assigner="judge_agent",
        content=episode["agent_prompt"],
    )
    goal.save()

    shared = {
        "task": goal,
        "messages": goal.conversation,
        "depth": 0,
    }
    name = "sre-agent-backfill-" + episode["fault_id"] + "-" + str(uuid.uuid4())

    sre_agent: LLMAgent
    with create_sre_agent(name, playbook_revision=playbook_revision) as sre_agent:
        try:
            await asyncio.wait_for(
                sre_agent.call(shared),
                timeout=SRE_AGENT_CALL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            print(f"SRE agent exceeded {SRE_AGENT_CALL_TIMEOUT_SEC}s timeout")
            goal.status = TaskStatus.DISCARDED
            goal.save()
            return

        goal.conversation = shared["messages"]
        goal.attempt_complete(force=True)

        live_timer(5 * 60)
        metrics_after_fixing = await get_metrics_summary()
        diff = detect_differences(episode["metrics_after"], metrics_after_fixing)
        focused_metrics_report = format_diff_status_report(diff, "recovery attempt")

        meaningful_actions, modified_files, deploy_app_called = collect_meaningful_actions(goal)

        evidence_report = "### System Execution Evidence (Ground Truth):\n"
        if meaningful_actions:
            evidence_report += "### Meaningful Tool Actions:\n"
        for action in meaningful_actions:
            evidence_report += f"{action}\n"
        if not meaningful_actions:
            evidence_report += "No meaningful tool actions were detected in the execution logs.\n"
        if modified_files:
            evidence_report += f"- Files modified during session: {', '.join(modified_files)}\n"
        else:
            evidence_report += "- No file modification tools were detected in the execution logs.\n"

        rich_history = goal.get_conversation_with_swapped_roles(include_actions=False)

        assessment_request = (
            "Please assess the SRE Agent's performance based on the following data.\n\n"
            f"**Fault Description:**\n{episode['fault_md']}\n\n"
            f"**Metrics Recovery Report:**\n{focused_metrics_report}\n\n"
            f"{evidence_report}\n\n"
            "Return the assessment in this JSON format:\n"
            "```json\n"
            "{\n"
            '    "root_cause_analysis": 0 or 1,\n'
            '    "successful_fix": 0 or 1,\n'
            '    "system_recovery_visible": 0 or 1\n'
            "}\n"
            "Add also constructive feedback for the agent to improve its performance. This should be in markdown format."
            "```markdown\n"
            "{constructive_feedback}\n"
            "```"
        )

        judge_messages = rich_history + [{"role": "user", "content": assessment_request}]
        shared_judge = {"messages": judge_messages}

        judge_agent = create_judge_agent()
        await judge_agent.call(shared_judge)

        goal.conversation.append(
            {"role": "user", "content": shared_judge["messages"][-1]["content"]}
        )
        print(f"Final judgement: {goal.conversation[-1]['content']}")
        total_usage = goal.get_total_usage()
        print("Total usage:")
        print(total_usage)
        goal.usage = total_usage
        goal.save()

    clean_all_containers()
    await restore_eks_node_group()
    delete_chaos_mesh_all_experiments()

    if target_created_at:
        shift_timestamps(db_path, episode["fault_id"], target_created_at)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run_backfill(args.fault, args.playbook_revision, args.db, args.target_created_at)
    )
