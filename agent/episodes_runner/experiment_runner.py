import asyncio
import os
import uuid

from agent.llm import ChunkProxyIterator, LLMAgent
from agent.persistence.settings import init_db
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.tasks.tasks import Task
from episodes_runner.episode_runner import (detect_differences,
                                            format_diff_status_report,
                                            get_metrics_summary, run_episode)
from episodes_runner.sre_agent import create_sre_agent
from episodes_runner.utils import live_timer

# Max wall time for the SRE agent flow; override with env SRE_AGENT_TIMEOUT_SEC.
SRE_AGENT_CALL_TIMEOUT_SEC = float(os.environ.get("SRE_AGENT_TIMEOUT_SEC", "1800"))

JUDGE_SYSTEM_PROMPT = """
You are a judge agent that evaluates the performance of the SRE Agent.
"""


def swap_roles(conversation: list[dict]) -> list[dict]:
    return [
        {
            "role": "assistant" if message["role"] == "user" else "user",
            "content": message["content"]
        }
        for message in conversation
    ]


async def run_experiment():
    init_db()
    api_handler: ApiHandler = build_api_handler(
        provider="minimax",
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url="https://api.minimax.io/v1"
    )

    episode = await run_episode(selected_fault="fault-2-catalogue-4ec7ce7e-13e8-4297-9ee0-4944d617e35b")
    goal = Task(
        id=episode["fault_id"],
        assignee="incident_commander",
        assigner="human",
        conversation=[
            {
                "role": "user",
                "content": episode["agent_prompt"]
            }
        ]
    )

    shared = {
        "task": goal,
        "messages": goal.conversation,
        "depth": 0
    }
    name = "sre-agent-experiment-" + episode["fault_id"] + "-" + str(uuid.uuid4())

    sre_agent: LLMAgent
    with create_sre_agent(name) as sre_agent:
        try:
            result = await asyncio.wait_for(
                sre_agent.call(shared),
                timeout=SRE_AGENT_CALL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            print(f"SRE agent exceeded {SRE_AGENT_CALL_TIMEOUT_SEC}s timeout")
            goal.conversation = goal.conversation + [
                {
                    "role": "user",
                    "content": f"SRE agent exceeded {SRE_AGENT_CALL_TIMEOUT_SEC}s timeout"
                    "\n"
                    "```json\n"
                    "{"
                    "    \"root_cause_analysis\": 0,"
                    "    \"successful_fix\": 0,"
                    "    \"system_recovery_visible\": 0,"
                    "    \"timed_out\": 1"
                    "}\n"
                    "```"
                }
            ]
            goal.save()
            return

    live_timer()  # wait for 5 minutes after the fix is deployed
    metrics_after_fixing = await get_metrics_summary()
    diff = detect_differences(episode["metrics_after"], metrics_after_fixing)
    focused_metrics_report = format_diff_status_report(diff, "recovery attempt")
    conversation = goal.conversation + result["messages"]
    conversation = conversation + [
        {
            "role": "user",
            "content": "Please assess the result of the previous conversation. That was made between you and the SRE Agent."
            "set root_cause_analysis to 0 if the root cause is not correct, 1 if it is correct."
            "set successful_fix to 0 if the successful fix is not correct, 1 if it is correct."
            "set if system recovery is visible in metrics to 0 if it is not visible, 1 if it is visible."
            "\n"
            "Here is the fault description that SRE attempted to fix:"
            f"{episode['fault_md']}"
            "\n"
            "Here is focused metrics report of the system before and after the recovery attempt:"
            f"{focused_metrics_report}"
            "\n"
            "return the result in the following structure: \n"
            "```json\n"
            "{"
            "    \"root_cause_analysis\": 1,"
            "    \"successful_fix\": 1,"
            "    \"system_recovery_visible\": 1"
            "}\n"
            "```"
        }
    ]
    iter: ChunkProxyIterator = await api_handler.create_message(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        messages=conversation,
    )

    async for _ in iter:
        pass

    conversation = conversation + iter.get_response()
    goal.conversation = conversation
    goal.save()
    return result


if __name__ == "__main__":
    asyncio.run(run_experiment())
