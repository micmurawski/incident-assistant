# Create Judge agent to evaluate the SRE Agent's performance


import json
from pathlib import Path

from agent.grafana_client.client import GrafanaClient
from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.eks import EksTools
from agent.tooling.kubectl import (KubectlReadTools, KubectlWriteTools,
                                   kubectl_get_resources)
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools

init_db()

JUDGE_SYSTEM_PROMPT = """
You are a judge agent that evaluates the performance of the SRE Agent.
"""


SYSTEM_PROMPTS = {
    "incident_commander": """
    You are a incident commander.
    You are responsible for commanding the incident response team.
    You are allowed to delegate tasks to your deputies, that are experts in their respective domains.
    Your deputies are:
    metrics_agent: is responsible for collecting/interpreting metrics from the cluster.
    devops_agent: is responsible for managing the cluster resources.
    """,
    "metrics_agent": """
    You are a metrics agent. You are responsible for collecting metrics from the kubernetes cluster.
    You are allowed to delegate tasks/subtasks if assign_task tool is present in the tools list.
    metrics_agent: is responsible for collecting/interpreting metrics from the cluster.
    devops_agent: is responsible for managing the cluster resources.
    """,
    "devops_agent": """
    You are a devops agent. You are responsible for managing the kubernetes cluster.
    You are allowed to delegate tasks/subtasks if assign_task tool is present in the tools list.
    metrics_agent: is responsible for collecting/interpreting metrics from the cluster.
    devops_agent: is responsible for managing the cluster resources.
    """,
}

def create_sre_agent(
    playbooks: dict[str, str] = None
) -> LLMAgent:
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

    incident_commander_tools = PlanningTools | CliTools
    metrics_tools = MetricsTools | kubectl_get_resources | PlanningTools | CliTools
    devops_tools = CliTools | CodebaseReadTools | KubectlReadTools | KubectlWriteTools | EksTools | PlanningTools

    incident_commander = LLMAgent(
        name="incident_commander",
        system_prompt=SYSTEM_PROMPTS["incident_commander"] + "\n" + playbooks.get("incident_commander", ""),
        tools=incident_commander_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,metrics_agent",
        }
    )
    incident_commander.register()

    metrics_agent = LLMAgent(
        name="metrics_agent",
        system_prompt=SYSTEM_PROMPTS["metrics_agent"] + "\n" + playbooks.get("metrics_agent", ""),
        tools=metrics_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,metrics_agent",
        }
    )
    metrics_agent.register()

    devops_agent = LLMAgent(
        name="devops_agent",
        system_prompt=SYSTEM_PROMPTS["devops_agent"] + "\n" + playbooks.get("devops_agent", ""),
        tools=devops_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent,metrics_agent",
        }
    )
    devops_agent.register()

    return incident_commander


if __name__ == "__main__":
    import asyncio
    import os
    import uuid

    from openinference.instrumentation import using_attributes
    from openinference.instrumentation.anthropic import AnthropicInstrumentor
    from opentelemetry import trace
    from phoenix.otel import register

    from agent.settings import SettingsManager
    from agent.tasks.tasks import Task

    provider = "minimax"
    tracer = trace.get_tracer(__name__)
    settings = SettingsManager.get_instance()
    settings.set("api.provider", provider)
    settings.set("api.api_key", os.environ["MINIMAX_API_KEY"])
    tracer_provider = register(project_name="sre-agent-testing-tracing")
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)

    async def main():
        SESSION_ID = str(uuid.uuid4())
        with tracer.start_as_current_span("sre-agent-testing-tracing-" + SESSION_ID):
            with using_attributes(session_id=SESSION_ID):

                goal = Task(
                    id=SESSION_ID,
                    assignee="incident_commander",
                    assigner="human",
                    conversation=[
                        {
                            "role": "user",
                            "content": "Can you ask metrics_agent to make a report about the application, and app node state?"
                        }
                    ]
                )
                goal.save()
                sre_agent = create_sre_agent()
                shared = {
                    "task": goal,
                    "messages": goal.conversation,
                    "depth": 0
                }
                result = await sre_agent.call(shared)
                goal.save()
                print(result)
    asyncio.run(main())
