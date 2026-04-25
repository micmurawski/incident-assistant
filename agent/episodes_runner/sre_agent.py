# Create Judge agent to evaluate the SRE Agent's performance


import asyncio
import json
import uuid
from contextlib import contextmanager

from ace.playbook_core import Playbook
from agent.grafana_client.client import AsyncGrafanaClient
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.repo_paths import get_repo_root
from agent.tasks.tasks import Task
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app
from agent.tooling.eks import EksReadTools, EksWriteTools
from agent.tooling.ecr import EcrReadTools
from agent.tooling.kubectl import (KubectlReadTools, KubectlWriteTools,
                                   kubectl_get_resources)
from agent.tooling.metrics import MetricsSummaryTools
from agent.tooling.planning import PlanningTools
from agent.tooling.rlm_metrics import REPLTools
from episodes_runner.utils import configure_settings

JUDGE_SYSTEM_PROMPT = """
You are a judge agent that evaluates the performance of the SRE Agent.
"""


@contextmanager
def create_sre_agent(
    name: str,
    provider: str | None = None,
    model_id: str | None = None,
    project_name: str = "sre-agent",
    playbook_revision: int | None = None,

) -> LLMAgent:
    """Create the SRE multi-agent team.

    Args:
        provider: LLM provider (e.g. ``"minimax"``, ``"groq"``). When ``None``,
            ``configure_settings`` falls back to ``EXPERIMENT_PROVIDER`` env var
            or ``"minimax"``.
        model_id: Explicit model id (e.g. ``"openai/gpt-oss-120b"``). When
            ``None``, ``configure_settings`` falls back to ``EXPERIMENT_MODEL``
            env var or the provider's default.
        playbook_revision: When ``None`` (default) use the latest revision.
            Pass an int (1-based) to pin every agent to a specific revision
            (e.g. ``1`` for the initial/empty playbook).

    """

    tracer = configure_settings(
        project_name,
        provider=provider,
        model_id=model_id,
    )

    def _load_playbook(assignee: str) -> str:
        if playbook_revision is not None:
            pb = Playbook.load_nth_revision_of(assignee, playbook_revision)
        else:
            pb = Playbook.load_last_revision_of(assignee)
        return pb.to_markdown(
            without_bullets_ids=True, positive_only=False, without_points=True
        )

    playbooks = {
        "incident_commander": _load_playbook("incident_commander"),
        "monitoring_agent": _load_playbook("monitoring_agent"),
        "devops_agent": _load_playbook("devops_agent"),
        "coder_agent": _load_playbook("coder_agent"),
    }
    repo_root = get_repo_root()
    api_key_path = repo_root / "api_key.json"
    workspace_path = repo_root / "workspace"
    GRAFANA_API_KEY = json.load(open(api_key_path))["grafana_api_token"]
    GRAFANA_URL = json.load(open(api_key_path))["grafana_url"]
    SRE_AGENT_AWS_ACCESS_KEY_ID = json.load(open(api_key_path))["incident-assistant"]["access_key_id"]
    SRE_AGENT_AWS_SECRET_ACCESS_KEY = json.load(open(api_key_path))["incident-assistant"]["secret_access_key"]
    SRE_AGENT_AWS_REGION = "us-east-1"
    SRE_AGENT_ENV = {
        "AWS_ACCESS_KEY_ID": SRE_AGENT_AWS_ACCESS_KEY_ID,
        "AWS_SECRET_ACCESS_KEY": SRE_AGENT_AWS_SECRET_ACCESS_KEY,
        "AWS_REGION": SRE_AGENT_AWS_REGION,
        "GRAFANA_API_KEY": GRAFANA_API_KEY,
        "GRAFANA_URL": GRAFANA_URL,
    }
    shared_context = {
        "cwd": str(workspace_path),
        "grafana_client": AsyncGrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY),
        "env": SRE_AGENT_ENV,
    }

    incident_commander_tools = PlanningTools | deploy_app | CodebaseReadTools
    metrics_tools = REPLTools | PlanningTools | MetricsSummaryTools | kubectl_get_resources | CodebaseReadTools

    devops_read_tools = CliTools | CodebaseReadTools | KubectlReadTools | EksReadTools | PlanningTools | EcrReadTools
    devops_write_tools = CodebaseWriteTools | CliTools | KubectlWriteTools | EksWriteTools | PlanningTools

    coder_tools = CodebaseReadTools | CodebaseWriteTools | CliTools | PlanningTools

    devops_tools = devops_read_tools | devops_write_tools

    incident_commander = LLMAgent(
        name="incident_commander",
        system_prompt=playbooks["incident_commander"],
        tools=incident_commander_tools,
        shared_context={
            **shared_context,
            "deploy_script_path": str(workspace_path / "k8s" / "deploy.sh"),
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    incident_commander.register()

    monitoring_agent = LLMAgent(
        name="monitoring_agent",
        system_prompt=playbooks["monitoring_agent"],
        tools=metrics_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    monitoring_agent.register()

    devops_agent = LLMAgent(
        name="devops_agent",
        system_prompt=playbooks["devops_agent"],
        tools=devops_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    devops_agent.register()

    coder_agent = LLMAgent(
        name="coder_agent",
        system_prompt=playbooks["coder_agent"],
        tools=coder_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    coder_agent.register()

    incident_commander.get_flow_graph_png("incident_commander.png")
    # return incident_commander
    with tracer.start_as_current_span(name):
        yield incident_commander


if __name__ == "__main__":
    init_db()

    async def main():
        SESSION_ID = str(uuid.uuid4())
        sre_agent: LLMAgent
        with create_sre_agent(
            name="sre-agent-testing-" + SESSION_ID,
            provider="openai_responses",
            model_id="gpt-5-nano"
        ) as sre_agent:
            goal = Task.create_root_task(
                id=SESSION_ID,
                assignee="incident_commander",
                assigner="human",
                #content="hello how are you?"
                content="Please ask coder_agent to give you list of tools and their capabilities, can you also make sure that coder_agent will ask devops_agent to give you list of tools and their capabilities? At the end I want you to use previous coder_agent session and ask him what was his last task."
                #content="Please ask your deputies to list their tools and their capabilities. And show me the report about their capabilities. You may achieve this by assigning tasks to them. Do not make list_metrics tool call."
            )
            goal.save()
            shared = {
                "task": goal,
                "messages": goal.conversation,
                "depth": 0
            }
            result = await sre_agent.call(shared)
            goal.conversation = shared["messages"]
            goal.feedback(
                {"role": "user", "content": "Task was completed. But your deputies also have deputies under them. And we are missing their list of tools."})
            print(result)
    asyncio.run(main())
