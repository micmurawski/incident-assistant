# Create Judge agent to evaluate the SRE Agent's performance


import asyncio
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from ace.playbook_core import Playbook
from agent.grafana_client.client import AsyncGrafanaClient
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.tasks.tasks import Task
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app
from agent.tooling.eks import EksReadTools, EksWriteTools
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
    provider: str = "minimax",
    project_name: str = "sre-agent"
) -> LLMAgent:

    tracer = configure_settings(project_name, provider)

    playbooks = {
        "incident_commander": Playbook.load_last_revision_of("incident_commander").to_markdown(
            without_bullets_ids=True, positive_only=False, without_points=True
        ),
        "monitoring_agent": Playbook.load_last_revision_of("monitoring_agent").to_markdown(
            without_bullets_ids=True, positive_only=False, without_points=True
        ),
        "devops_agent": Playbook.load_last_revision_of("devops_agent").to_markdown(
            without_bullets_ids=True, positive_only=False, without_points=True
        ),
        "coder_agent": Playbook.load_last_revision_of("coder_agent").to_markdown(
            without_bullets_ids=True, positive_only=False, without_points=True
        ),
    }
    api_key_path = Path("/Users/micmur/GITHUB/o8s/api_key.json")
    workspace_path = Path("/Users/micmur/GITHUB/o8s/workspace")
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

    incident_commander_tools = PlanningTools | deploy_app
    metrics_tools = REPLTools | PlanningTools | MetricsSummaryTools | kubectl_get_resources

    devops_read_tools = CliTools | CodebaseReadTools | KubectlReadTools | EksReadTools | PlanningTools
    devops_write_tools = CodebaseWriteTools | CliTools | KubectlWriteTools | EksWriteTools | PlanningTools

    coder_tools = CodebaseReadTools | CodebaseWriteTools | CliTools | PlanningTools

    devops_tools = devops_read_tools | devops_write_tools

    incident_commander = LLMAgent(
        name="incident_commander",
        system_prompt=playbooks["incident_commander"],
        tools=incident_commander_tools,
        shared_context={
            **shared_context,
            "deploy_script_path": "/Users/micmur/GITHUB/o8s/workspace/k8s/deploy.sh",
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
        with create_sre_agent(name="sre-agent-testing-" + SESSION_ID) as sre_agent:
            goal = Task.create_root_task(
                id=SESSION_ID,
                assignee="incident_commander",
                assigner="human",
                #content="Please ask coder_agent to give you list of tools and their capabilities, can you also make sure that coder_agent will ask devops_agent to give you list of tools and their capabilities? At the end I want you to use previous coder_agent session and ask him what was his last task."
                content="Please ask your deputies to list their tools and their capabilities. And show me the report about their capabilities. You may achieve this by assigning tasks to them. Do not make list_metrics tool call."
            )
            goal.save()
            shared = {
                "task": goal,
                "messages": goal.conversation,
                "depth": 0
            }
            result = await sre_agent.call(shared)
            goal.feedback(
                {"role": "user", "content": "Task was completed. But your deputies also have deputies under them. And we are missing their list of tools."})
            print(result)
    asyncio.run(main())
