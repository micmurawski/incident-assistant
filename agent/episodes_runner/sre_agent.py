# Create Judge agent to evaluate the SRE Agent's performance


import json
from pathlib import Path


from agent.grafana_client.client import GrafanaClient
from agent.llm import LLMAgent
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.eks import EksTools
from agent.tooling.kubectl import (KubectlReadTools, KubectlWriteTools)
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools

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
    
    incident_commander_tools = PlanningTools
    metrics_tools = MetricsTools
    devops_tools = CliTools | CodebaseReadTools | KubectlReadTools | KubectlWriteTools | EksTools
    

    incident_commander = LLMAgent(
        name="incident_commander",
        system_prompt="You are a incident commander. You are responsible for commanding the incident response team.",
        tools=incident_commander_tools,
        shared_context={
            **shared_context,
            "available_agents": "devops_agent",
        }
    )
    
    metrics_agent = LLMAgent(
        name="metrics_agent",
        system_prompt="You are a metrics agent. You are responsible for collecting metrics from the kubernetes cluster.",
        tools=metrics_tools,
        shared_context=shared_context,
    )
    metrics_agent.register()

    devops_agent = LLMAgent(
        name="devops_agent",
        system_prompt="You are a devops agent. You are responsible for managing the kubernetes cluster.",
        tools=devops_tools,
        shared_context=shared_context,
    )
    devops_agent.register()
    
