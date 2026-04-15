import asyncio
import os
import uuid

import yaml

from ace.pipeline import run_ace_pipeline
from ace.playbook_core import Playbook
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
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

# Max wall time for the SRE agent flow; override with env SRE_AGENT_TIMEOUT_SEC.
SRE_AGENT_CALL_TIMEOUT_SEC = float(os.environ.get("SRE_AGENT_TIMEOUT_SEC", "3600"))
ACE_ASSIGNEES = ["incident_commander", "monitoring_agent", "devops_agent", "coder_agent"]

JUDGE_SYSTEM_PROMPT = """
You are a Senior SRE Judge. Your role is to evaluate if an SRE Agent successfully resolved an incident.
You have access to:
1. The conversation history (including text-based representations of tool actions).
2. System metrics before and after the attempt.
3. System Execution Evidence (Ground Truth of which tools were actually executed by the framework).

Your evaluation must be grounded in evidence. If the agent claims to have fixed a file or deployed a change, but the "System Execution Evidence" does not show the corresponding tool call, you must consider the action as not performed.

Criteria:
- root_cause_analysis: 1 if the agent correctly identified the specific failure (e.g., the exact bug in a file or the misconfigured parameter), 0 otherwise.
- successful_fix: 1 if the agent applied a correct fix AND triggered a deployment (deploy_app), 0 otherwise.
    - assess files changes, if correct file was modified in correct place it needs to be correct fix, but not exactly the same code as before the incident, if not it needs to be 0.
    - assess deployment, if deployment was triggered and it was successful, 0 otherwise.
- system_recovery_visible: 1 if the metrics report clearly shows the system returned to a healthy state, 0 otherwise.
    - if 5XX are visible in metrics put it as 0.
    - assess all metrics, if CPU, memory usage or any other metric is lower than before the incident, 0 otherwise.
    
    
Return your final assessment in the requested JSON format.
"""


def create_judge_agent(provider: str = "minimax"):
    configure_settings("sre-agent", provider)
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


async def run_experiment():
    init_db()
    # Every 5 episodes, run ACE pipeline only if revision floor is not reached.
    episode_count = get_episode_count()
    if _should_run_ace_pipeline(episode_count):
        print(f"Running ACE pipeline for episode {episode_count}")
        await run_ace_pipeline()
    else:
        print(f"Skipping ACE pipeline for episode {episode_count}")

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

    sre_agent: LLMAgent
    with create_sre_agent(name) as sre_agent:
        try:
            await asyncio.wait_for(
                sre_agent.call(shared),
                timeout=SRE_AGENT_CALL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            print(f"SRE agent exceeded {SRE_AGENT_CALL_TIMEOUT_SEC}s timeout")
            # ... (timeout handling remains similar but simplified for brevity)
            goal.status = TaskStatus.DISCARDED
            goal.save()
            return
        goal.conversation = shared["messages"]
        goal.attempt_complete(force=True)
        # Wait for recovery
        live_timer(5*60)
        metrics_after_fixing = await get_metrics_summary()
        diff = detect_differences(episode["metrics_after"], metrics_after_fixing)
        focused_metrics_report = format_diff_status_report(diff, "recovery attempt")

        # 1. Collect all meaningful tool actions from the entire task tree
        meaningful_actions, modified_files, deploy_app_called = collect_meaningful_actions(goal)
        # 2. Build the System Evidence Report
        evidence_report = "### System Execution Evidence (Ground Truth):\n"
        if deploy_app_called:
            evidence_report += "- [VERIFIED] `deploy_app` was called.\n"
        else:
            evidence_report += "- [MISSING] `deploy_app` was NOT called. The agent might have forgotten to deploy.\n"

        if modified_files:
            evidence_report += f"- Files modified during session: {', '.join(modified_files)}\n"
            for action in meaningful_actions:
                evidence_report += f"  {action}\n"
        else:
            evidence_report += "- No file modification tools were detected in the execution logs.\n"

        # 3. Prepare the Judge's input
        # Use include_actions=True so the judge sees tool names/args (ground truth for claims vs evidence).
        rich_history = goal.get_conversation_with_swapped_roles(include_actions=False)

        assessment_request = (
            "Please assess the SRE Agent's performance based on the following data.\n\n"
            f"**Fault Description:**\n{episode['fault_md']}\n\n"
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
        goal.save()

    clean_all_containers()
    await restore_eks_node_group()
    delete_chaos_mesh_all_experiments()


if __name__ == "__main__":
    asyncio.run(run_experiment())
