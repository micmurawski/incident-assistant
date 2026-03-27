# Create Judge agent to evaluate the SRE Agent's performance


import asyncio
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.grafana_client.client import GrafanaClient
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app
from agent.tooling.eks import EksReadTools, EksWriteTools
from agent.tooling.kubectl import (KubectlReadTools, KubectlWriteTools,
                                   kubectl_get_resources)
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools

JUDGE_SYSTEM_PROMPT = """
You are a judge agent that evaluates the performance of the SRE Agent.
"""


SYSTEM_PROMPTS = {
    "incident_commander": """
    You are a incident commander.
    You are responsible for commanding the incident response team.
    You are allowed to delegate tasks to your deputies, that are experts in their respective domains.
    You are responsible running deploy_app tool once fix is ready to be deployed.
    Your deputies are:
    - coder_agent: is responsible for coding the application.
    - monitoring_agent: is responsible for collecting/interpreting logs/metrics from the cluster.
    - devops_agent: is responsible for managing the cluster resources.
    """,
    "monitoring_agent": """
    You are a monitoring agent. You are responsible for collecting logs/metrics from the kubernetes cluster.
    You are allowed to delegate tasks/subtasks if assign_task tool is present in the tools list.
    You are able to delegate tasks/subtasks to the following agents:
    - coder_agent: is responsible for coding the application.
    - monitoring_agent: - you (you may call yourself recursively)
    - devops_agent: is responsible for managing the cluster resources.
    """,
    "devops_agent": """
    You are a devops agent. You are responsible for managing the kubernetes cluster.
    You are allowed to delegate tasks/subtasks if assign_task tool is present in the tools list.
    You are able to delegate tasks/subtasks to the following agents:
    
    Focus on application namespace where the application is running.
    - monitoring_agent: is responsible for collecting/interpreting logs/metrics from the cluster.
    - devops_agent: - you (you may call yourself recursively)
    """,
    "coder_agent": """
    You are a coder agent. You are responsible for coding the application.
    You are allowed to delegate tasks/subtasks if assign_task tool is present in the tools list.
    You are able to delegate tasks/subtasks to the following agents:
    - coder_agent: - you (you may call yourself recursively)
    - monitoring_agent: is responsible for collecting/interpreting logs/metrics from the cluster.
    - devops_agent: is responsible for managing the cluster resources.
    """,
}


def configure_settings(project_name: str, provider: str = "minimax") -> None:
    settings = SettingsManager.get_instance()
    settings.set("api.provider", provider)
    settings.set("api.api_key", os.environ["MINIMAX_API_KEY"])
    tracer_provider = register(project_name=project_name)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    return trace.get_tracer(__name__)


@contextmanager
def create_sre_agent(
    name: str,
    playbooks: dict[str, str] = None,
    provider: str = "minimax",
    project_name: str = "sre-agent"
) -> LLMAgent:

    tracer = configure_settings(project_name, provider)

    if playbooks is None:
        playbooks = {}
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
    }
    shared_context = {
        "cwd": str(workspace_path),
        "grafana_client": GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY),
        "env": SRE_AGENT_ENV,
    }

    incident_commander_tools = PlanningTools | deploy_app
    metrics_tools = MetricsTools | kubectl_get_resources | PlanningTools
    
    devops_read_tools = CliTools | CodebaseReadTools | KubectlReadTools | EksReadTools | PlanningTools
    devops_write_tools = CodebaseWriteTools | CliTools  | KubectlWriteTools | EksWriteTools | PlanningTools
    
    coder_tools = CodebaseReadTools | CodebaseWriteTools | CliTools | PlanningTools
    
    devops_tools = devops_read_tools | devops_write_tools

    incident_commander = LLMAgent(
        name="incident_commander",
        system_prompt=SYSTEM_PROMPTS["incident_commander"] + "\n" + playbooks.get("incident_commander", ""),
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
        system_prompt=SYSTEM_PROMPTS["monitoring_agent"] + "\n" + playbooks.get("monitoring_agent", ""),
        tools=metrics_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    monitoring_agent.register()

    devops_agent = LLMAgent(
        name="devops_agent",
        system_prompt=SYSTEM_PROMPTS["devops_agent"] + "\n" + playbooks.get("devops_agent", ""),
        tools=devops_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,monitoring_agent,coder_agent",
        }
    )
    devops_agent.register()
    
    coder_agent = LLMAgent(
        name="coder_agent",
        system_prompt=SYSTEM_PROMPTS["coder_agent"] + "\n" + playbooks.get("coder_agent", ""),
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

                goal = Task(
                    id=SESSION_ID,
                    assignee="incident_commander",
                    assigner="human",
                    conversation=[
                        {
                            "role": "user",
                            "content": "Please ask coder_agent, monitoring_agent and devops_agent to list their tools and their capabilities. And show me the report about their capabilities. You may achieve this by assigning tasks to them."
                        }
                    ]
                )
                goal.save()
                shared = {
                    "task": goal,
                    "messages": goal.conversation,
                    "depth": 0
                }
                result = await sre_agent.call(shared)
                goal.save()
                print(result)
    asyncio.run(main())
