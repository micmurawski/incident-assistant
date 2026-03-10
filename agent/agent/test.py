

import asyncio
import os
import uuid
from typing import Any, Literal, TypeVar

from framework import AsyncFlow
from openinference.instrumentation import using_attributes
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.llm import LLMAgent
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling import CodebaseReadTools, CodebaseWriteTools
from agent.tooling.cli import CliTools
from agent.tooling.kubectl import KubectlTools
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools
from agent.tracing import trace_flow
import json
from agent.grafana_client.client import GrafanaClient
T = TypeVar('T')


os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

SESSION_ID = str(uuid.uuid4())
tracer_provider = register(project_name="agent-tracing")

provider: Literal["anthropic", "openai", "google", "ollama", "minimax"] = "minimax"
tracer = trace.get_tracer(__name__)

api_keys = json.load(open("api_keys.json"))

AGENT_ENV = {
    "AWS_ACCESS_KEY_ID": api_keys["incident-assistant"]["access_key_id"],
    "AWS_SECRET_ACCESS_KEY": api_keys["incident-assistant"]["secret_access_key"],
    "AWS_REGION": "us-east-1",
}

GRAFANA_URL = api_keys["grafana_url"]
GRAFANA_API_KEY = api_keys["grafana_api_key"]

settings = SettingsManager.get_instance()
settings.set("api.provider", provider)


if provider in ["anthropic", "minimax"]:
    if provider == "minimax":
        API_KEY = api_keys["minimax_api_key"]
    else:
        API_KEY = api_keys["anthropic_api_key"]
    settings.set("api.api_key", API_KEY)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider == "openai":
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider == "google":
    API_KEY = api_keys["gemini_api_key"]
    settings.set("api.api_key", API_KEY)
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
else:
    raise ValueError(f"Unknown provider: {provider}")


class Agent(LLMAgent):
    def __init__(
        self,
        name: str,
        system_prompt: str,
        api_settings: dict[str, Any] | None = None,
        cwd: str | None = None,
        tools: Any | None = None,
        shared_context: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
    ):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        self.system_prompt = system_prompt
        self.cwd = cwd
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.name = name

        @trace_flow(f"agent-{name}-flow")
        class _TracedFlow(AsyncFlow):
            def __init__(self, start):
                super().__init__(start=start)
        self.flow = _TracedFlow(start=self.call_llm)

        self.shared_context = {**shared_context, "cwd": cwd, "env": env}
        # create re-act agent with summarization
        self.bind_tools(tools, self.get_shared())
        self.call_llm - "tools" >> tools
        tools >> self.summarize_context
        self.summarize_context >> self.call_llm

        # from framework.decorators import end
        # self.call_llm - "default" >> end


async def main():
    with tracer.start_as_current_span("agent-execution-flow-session-" + SESSION_ID):
        with using_attributes(session_id=SESSION_ID):
            cwd = "/Users/micmur/GITHUB/o8s/services/robot-shop"
            update_todo_tools = PlanningTools.select({"update_todo"})

            manager_tools = PlanningTools
            devops_tools = CliTools | CodebaseReadTools | KubectlTools | update_todo_tools
            metrics_tools = MetricsTools | CliTools | update_todo_tools
            coder_tools = CodebaseWriteTools | CodebaseReadTools | update_todo_tools

            agent_manager = Agent(
                name="agent_manager",
                system_prompt="You are a manager of agents. "
                "You are responsible for assigning tasks to agents and ensuring they are completed."
                "You have the following agents available: devops, metrics, coder"
                "devops: is able to manage kubernetes cluster running apps"
                "metrics: is able to collect metrics from the kubernetes cluster"
                "coder: is able to code the application",
                cwd=cwd,
                tools=manager_tools,
                shared_context={"available_agents": "devops,metrics,coder"},
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

            Agent(
                name="metrics",
                system_prompt="You are a metrics helper. You know the codebase and the metrics."
                "You are responsible for helping with the metrics.",
                cwd=cwd,
                tools=metrics_tools,
                env=AGENT_ENV,
            ).register()

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
                        "content": "Can you ask your team to check if we are using java in the codebase?"
                    }
                ],
            )

            shared = {
                "cwd": "/Users/micmur/GITHUB/o8s/services/robot-shop",
                "session_id": SESSION_ID,
                "messages": goal.conversation,
                "task": goal,
                "grafana_client": GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY),
            }

            print(agent_manager.get_flow_graph())
            agent_manager.get_flow_graph_png("agent_manager.png")
            await agent_manager.call(shared)
            # span.set_status(StatusCode.OK)

if __name__ == "__main__":

    asyncio.run(main())
