

import asyncio
import json
import os
import uuid
from typing import Literal, TypeVar

from openinference.instrumentation import using_attributes
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.grafana_client.client import GrafanaClient
from agent.llm import LLMAgent
from agent.repo_paths import robot_shop_dir
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling import CodebaseReadTools, CodebaseWriteTools
from agent.tooling.cli import CliTools
from agent.tooling.kubectl import KubectlReadTools
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools

T = TypeVar('T')


os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

SESSION_ID = str(uuid.uuid4())
tracer_provider = register(project_name="agent-tracing")

provider: Literal["anthropic", "openai", "google", "ollama", "minimax"] = "minimax"
tracer = trace.get_tracer(__name__)

api_keys = json.load(open("api_key.json"))

AGENT_ENV = {
    "AWS_ACCESS_KEY_ID": api_keys["incident-assistant"]["access_key_id"],
    "AWS_SECRET_ACCESS_KEY": api_keys["incident-assistant"]["secret_access_key"],
    "AWS_REGION": "us-east-1",
}

GRAFANA_URL = api_keys["grafana_url"]
GRAFANA_API_KEY = api_keys["grafana_api_token"]

settings = SettingsManager.get_instance()
settings.set("api.provider", provider)


if provider in ["anthropic", "minimax"]:
    if provider == "minimax":
        API_KEY = api_keys["minimax_api_key"]
    else:
        API_KEY = api_keys["anthropic_api_key"]
    settings.set("api.api_key", API_KEY)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider in ["openai", "groq"]:
    if provider == "groq":
        API_KEY = api_keys["groq_api_key"]
        settings.set("api.api_key", API_KEY)
        settings.set("api.base_url", "https://api.groq.com/openai/v1")
    else:
        API_KEY = api_keys["openai_api_key"]
        settings.set("api.api_key", API_KEY)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider == "google":
    API_KEY = api_keys["gemini_api_key"]
    settings.set("api.api_key", API_KEY)
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
else:
    raise ValueError(f"Unknown provider: {provider}")


class Agent(LLMAgent):
    pass


async def main():
    with tracer.start_as_current_span("agent-execution-flow-session-" + SESSION_ID):
        with using_attributes(session_id=SESSION_ID):
            cwd = str(robot_shop_dir())
            update_todo_tools = PlanningTools.select({"update_todo"})

            manager_tools = PlanningTools | MetricsTools
            devops_tools = CliTools | CodebaseReadTools | KubectlReadTools | update_todo_tools
            # metrics_tools = MetricsTools | CliTools | update_todo_tools
            coder_tools = CodebaseWriteTools | CodebaseReadTools | update_todo_tools

            agent_manager = Agent(
                name="agent_manager",
                system_prompt="You are a manager of agents. "
                "You are responsible for assigning tasks to agents and ensuring they are completed."
                "You have the following agents available: devops, coder"
                "devops: is able to manage kubernetes cluster running apps"
                # "metrics: is able to collect metrics from the kubernetes cluster"
                "coder: is able to code the application",
                cwd=cwd,
                tools=manager_tools,
                shared_context={"available_agents": "devops,coder"},
                env=AGENT_ENV,
            )
            agent_manager.register()
            Agent(
                name="devops",
                system_prompt="You are a devops helper. You know the codebase and the devops tasks."
                "You are responsible for helping with the devops tasks.",
                cwd=cwd,
                tools=devops_tools,
                env=AGENT_ENV,
            ).register()

            # Agent(
            #    name="metrics",
            #    system_prompt="You are a metrics helper. You know the codebase and the metrics."
            #    "You are responsible for helping with the metrics.",
            #    cwd=cwd,
            #    tools=metrics_tools,
            #    env=AGENT_ENV,
            # ).register()

            Agent(
                name="coder",
                system_prompt="You are a coder helper. You know the codebase and the coder tasks."
                "You are responsible for helping with the coder tasks.",
                cwd=cwd,
                tools=coder_tools,
                env=AGENT_ENV,
            ).register()

            goal = Task(
                id="123",
                assignee="agent_manager",
                assigner="human",
                conversation=[
                    {
                        "role": "user",
                        "content": "Can you check if our application is running correctly?"
                    }
                ],
            )

            shared = {
                "cwd": cwd,
                "session_id": SESSION_ID,
                "messages": goal.conversation,
                "task": goal,
                "grafana_client": GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY),
                "env": AGENT_ENV,
            }

            print(agent_manager.get_flow_graph())
            agent_manager.get_flow_graph_png("agent_manager.png")
            await agent_manager.call(shared)
            goal.conversation = shared["messages"]
            # span.set_status(StatusCode.OK)

if __name__ == "__main__":

    asyncio.run(main())
