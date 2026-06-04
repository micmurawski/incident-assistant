import argparse
import asyncio
import os
import subprocess
import uuid

import yaml

from ace.pipeline import run_ace_pipeline
from ace.playbook_core import Playbook
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus
from agent.tooling.decorators import Tools
from agent.tooling.metrics import NAMESPACE
from episodes_runner.episode_runner import (detect_differences,
                                            ensure_load_gen_deployed,
                                            format_diff_status_report,
                                            get_metrics_summary, run_episode)
from episodes_runner.runner import delete_chaos_mesh_all_experiments
from episodes_runner.sre_agent import configure_settings, create_sre_agent
from episodes_runner.utils import (clean_all_containers,
                                   cleanup_keep_initial_services,
                                   collect_meaningful_actions, live_timer,
                                   restore_eks_node_group, get_pod_snapshot)

# Max wall time for the SRE agent flow; override with env SRE_AGENT_TIMEOUT_SEC.
SRE_AGENT_CALL_TIMEOUT_SEC = float(os.environ.get("SRE_AGENT_TIMEOUT_SEC", "3600"))
ACE_ASSIGNEES = ["incident_commander", "monitoring_agent", "devops_agent", "coder_agent"]
FIX_REDIS_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "fix-redis.sh")
)
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


def create_judge_agent(provider: str | None = None, model_id: str | None = None):
    configure_settings("sre-agent", provider=provider, model_id=model_id)
    judge_agent = LLMAgent(
        name="judge_agent",
        system_prompt=JUDGE_SYSTEM_PROMPT,
        tools=Tools(tools=[]),
    )
    return judge_agent


def get_episode_count():
    FAULT_HISTORY_PATH = "agent/episodes_runner/fault_history.yaml"
    with open(FAULT_HISTORY_PATH, "r") as f:
        fault_history = yaml.safe_load(f)
        history = fault_history.get("history", [])
    return len(history)


def _current_playbook_revisions() -> dict[str, int]:
    revisions: dict[str, int] = {}
    for assignee in ACE_ASSIGNEES:
        revisions[assignee] = Playbook.load_last_revision_of(assignee).number_of_revisions
    return revisions


def _should_run_ace_pipeline(episode_count: int) -> bool:
    if episode_count <= 0 or episode_count % 5 != 0:
        return False
    current_revisions = _current_playbook_revisions()
    expected_floor = 1 + (episode_count // 5)
    return any(rev < expected_floor for rev in current_revisions.values())


async def run_experiment(
    db_path: str = "./agent.db",
    learning: bool = True,
    provider: str = "minimax",
    model_id: str | None = None,
):
    """Run one experiment episode.

    Args:
        db_path: SQLite database to write tasks to.
        learning: When True (default) behaves like the original runner —
            may trigger the ACE pipeline on the normal cadence and uses the
            latest playbook revision. When False, the ACE pipeline is never
            run and every agent is pinned to playbook revision 1.
        provider: LLM provider (e.g. ``"minimax"``, ``"groq"``). Also exported
            as ``EXPERIMENT_PROVIDER`` so nested agents (reflector/curator/
            judge) use the same provider.
        model_id: Explicit model id (e.g. ``"openai/gpt-oss-120b"``). When
            ``None``, the provider's default model is used. Exported as
            ``EXPERIMENT_MODEL`` for nested agents.
    """
    SettingsManager.get_instance().set("persistence.url", db_path)
    init_db()
    # Expose provider/model to every nested ``configure_settings`` call
    # (reflector/curator inside run_ace_pipeline, judge agent, etc.).
    os.environ["EXPERIMENT_PROVIDER"] = provider
    if model_id:
        os.environ["EXPERIMENT_MODEL"] = model_id
    else:
        os.environ.pop("EXPERIMENT_MODEL", None)

    print(f"Database: {db_path}")
    print(f"Learning: {learning}")
    print(f"Provider: {provider}")
    print(f"Model:    {model_id or '<provider default>'}")

    if learning:
        # Every 5 episodes, run ACE pipeline only if revision floor is not reached.
        episode_count = get_episode_count()
        if _should_run_ace_pipeline(episode_count):
            print(f"Running ACE pipeline for episode {episode_count}")
            await run_ace_pipeline()
        else:
            print(f"Skipping ACE pipeline for episode {episode_count}")
    else:
        print("Learning disabled — skipping ACE pipeline and pinning playbook revision to 1")

    print(f"Running pre-deployment redis reset script: {FIX_REDIS_SCRIPT}")
    subprocess.run(["bash", FIX_REDIS_SCRIPT], check=True)
    print("Waiting 5 minutes after redis reset...")
    live_timer(5 * 60)

    baseline_pods = set(get_pod_snapshot(NAMESPACE).keys())
    try:
        await ensure_load_gen_deployed()
        episode = await run_episode()
        goal = Task.create_root_task(
            id=episode["fault_id"],
            assignee="incident_commander",
            assigner="judge_agent",
            content=episode["agent_prompt"]
        )
        goal.save()

        shared = {
            "task": goal,
            "messages": goal.conversation,
            "depth": 0
        }
        name = "sre-agent-experiment-" + episode["fault_id"] + "-" + str(uuid.uuid4())

        playbook_revision = None if learning else 1

        sre_agent: LLMAgent
        with create_sre_agent(
            name,
            provider=provider,
            model_id=model_id,
            playbook_revision=playbook_revision,
        ) as sre_agent:
            timed_out = False
            try:
                await asyncio.wait_for(
                    sre_agent.call(shared),
                    timeout=SRE_AGENT_CALL_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                print(f"SRE agent exceeded {SRE_AGENT_CALL_TIMEOUT_SEC}s timeout")
                timed_out = True
            goal.conversation = shared["messages"]
            goal.attempt_complete(force=True)

            # For completed runs, wait for stabilization before evaluating recovery.
            # For timeout runs, still evaluate and generate feedback immediately.
            if not timed_out:
                live_timer(5 * 60)
            metrics_after_fixing = await get_metrics_summary()
            diff = detect_differences(episode["metrics_after"], metrics_after_fixing)
            focused_metrics_report = format_diff_status_report(diff, "recovery attempt")
            if timed_out:
                focused_metrics_report += (
                    f"\n\nRun status note: the SRE agent timed out after "
                    f"{SRE_AGENT_CALL_TIMEOUT_SEC}s. Evaluate the partial attempt and "
                    "provide constructive feedback anyway."
                )

            # 1. Collect all meaningful tool actions from the entire task tree
            meaningful_actions, modified_files, deploy_app_called = collect_meaningful_actions(goal)
            print(f"Meaningful actions: {meaningful_actions}")
            print(f"Modified files: {modified_files}")
            print(f"Deploy app called: {deploy_app_called}")
            # 2. Build the System Evidence Report
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

            # 3. Prepare the Judge's input
            # Use include_actions=True so the judge sees tool names/args (ground truth for claims vs evidence).
            rich_history = goal.get_conversation_with_swapped_roles(include_actions=False)

            assessment_request = (
                "Please assess the SRE Agent's performance based on the following data.\n\n"
                f"**Fault Description:**\n{episode['fault_md']}\n\n"
                f"**Run Timed Out:**\n{'yes' if timed_out else 'no'}\n\n"
                f"**Metrics Recovery Report:**\n{focused_metrics_report}\n\n"
                f"{evidence_report}\n\n"
                "Return the assessment in this JSON format:\n"
                "```json\n"
                "{\n"
                "    \"root_cause_analysis\": 0 or 1,\n"
                "    \"successful_fix\": 0 or 1,\n"
                "    \"system_recovery_visible\": 0 or 1\n"
                "}\n"
                "Add also constructive feedback for the agent to improve its performance. This should be in markdown format."
                "```markdown\n"
                "{constructive_feedback}\n"
                "```"
            )

            judge_messages = rich_history + [{"role": "user", "content": assessment_request}]

            # Do not pass the root `goal` as `task`: incident_commander already exhausted
            # goal.iterations_count against goal.iterations_limit. Reusing the same Task makes
            # call_llm hit the iteration hard-stop immediately and return a stub message instead
            # of real judge output.
            shared_judge = {
                "messages": judge_messages,
                # "task": goal  # Allow judge to see task context if needed
            }

            # 4. Run the Judge Agent
            judge_agent = create_judge_agent()
            await judge_agent.call(shared_judge)

            # Final save
            goal.conversation.append(
                {
                    "role": "user",
                    "content": shared_judge["messages"][-1]["content"]
                }
            )
            # print final judgement
            print(f"Final judgement: {goal.conversation[-1]['content']}")
            total_usage = goal.get_total_usage()
            print("Total usage:")
            print(total_usage)
            goal.usage = total_usage
            if timed_out:
                goal.status = TaskStatus.DISCARDED
            goal.save()
    finally:
        clean_all_containers()
        await restore_eks_node_group()
        delete_chaos_mesh_all_experiments()
        cleanup_keep_initial_services(NAMESPACE, baseline_pods)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single SRE-agent experiment episode."
    )
    parser.add_argument(
        "--db",
        default="./agent.db",
        help="Path to the target SQLite database (default: ./agent.db).",
    )
    learning_group = parser.add_mutually_exclusive_group()
    learning_group.add_argument(
        "--learning",
        dest="learning",
        action="store_true",
        help="Enable learning: may run ACE pipeline and use latest playbook (default).",
    )
    learning_group.add_argument(
        "--no-learning",
        dest="learning",
        action="store_false",
        help="Disable learning: skip ACE pipeline and pin playbook to revision 1.",
    )
    parser.set_defaults(learning=True)
    parser.add_argument(
        "--provider",
        default="minimax",
        choices=["minimax", "groq", "gemini", "anthropic", "openai", "openai_responses", "openrouter", "ovh"],
        help="LLM provider for all agents (SRE team, ACE reflector/curator, judge). Default: minimax.",
    )
    parser.add_argument(
        "--model",
        dest="model_id",
        default=None,
        help=(
            "Explicit model id (e.g. 'openai/gpt-oss-120b' for Groq/OpenRouter, "
            "'gpt-oss-120b' for OVH, 'MiniMax-M2.5' for MiniMax). "
            "If omitted, the provider's default model is used."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        run_experiment(
            db_path=args.db,
            learning=args.learning,
            provider=args.provider,
            model_id=args.model_id,
        )
    )
