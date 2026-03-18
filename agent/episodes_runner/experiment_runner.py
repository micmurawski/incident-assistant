# Create Judge agent to evaluate the SRE Agent's performance


import json
from pathlib import Path

from openinference.instrumentation import using_attributes
from opentelemetry import trace

from agent.grafana_client.client import GrafanaClient
from agent.llm import LLMAgent
from agent.tasks.tasks import Task

JUDGE_SYSTEM_PROMPT = """
You are a judge agent that evaluates the performance of the SRE Agent.
"""


def create_sre_agent():
    api_key_path = Path("/Users/micmur/GITHUB/o8s/agent/api_key.json")
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


async def run_experiment(task: Task, sre_agent: LLMAgent):
    shared = {
        "cwd": "/Users/micmur/GITHUB/o8s/services/robot-shop",
        "session_id": task.id,
        "messages": task.conversation,
        "task": task,
        # "grafana_client": GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY),
        # "env": AGENT_ENV,
    }
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("experiment-runner-session-" + task.id):
        with using_attributes(session_id=task.id):
            sre_agent.submit_task(task)

    task.save()
