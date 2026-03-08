

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
from agent.tooling.kubectl import (KubectlTools)
from agent.tooling.metrics import MetricsTools
from agent.tooling.planning import PlanningTools
from agent.tracing import trace_flow

T = TypeVar('T')


os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

SESSION_ID = str(uuid.uuid4())
tracer_provider = register(project_name="agent-tracing")
provider: Literal["anthropic", "openai", "google", "ollama", "minimax"] = "minimax"
# Get a tracer for your application
tracer = trace.get_tracer(__name__)

settings = SettingsManager.get_instance()


settings.set("api.provider", provider)

if provider in ["anthropic", "minimax"]:
    if provider == "minimax":
        API_KEY = os.getenv("MINIMAX_API_KEY")
    else:
        API_KEY = os.getenv("ANTHROPIC_API_KEY")
    settings.set("api.api_key", API_KEY)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider == "openai":
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
elif provider == "google":
    API_KEY = os.getenv("GEMINI_API_KEY")
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

    ):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.name = name

        @trace_flow(f"agent-{name}-flow")
        class _TracedFlow(AsyncFlow):
            def __init__(self, start):
                super().__init__(start=start)
        self.flow = _TracedFlow(start=self.call_llm)
        
        
        # create re-act agent with summarization
        


async def main():
    with tracer.start_as_current_span("agent-execution-flow-session-" + SESSION_ID):
        with using_attributes(session_id=SESSION_ID):

            agent_manager = Agent(
                name="agent_manager",
                system_prompt="You are a manager of agents. "
                "You are responsible for assigning tasks to agents and ensuring they are completed.",
            )
            devops_agent = Agent(
                name="devops",
                system_prompt="You are a devops helper. You know the codebase and the devops tasks."
                "You are responsible for helping with the devops tasks.",
            )

            Agent(
                name="metrics",
                system_prompt="You are a metrics helper. You know the codebase and the metrics."
                "You are responsible for helping with the metrics.",
            )

            goal = Task(
                id="123",
                assignee="agent_manager",
                assigner="human",
                conversation=[
                    {"role": "user", "content": "Can you ask your team to check if we are using java in the codebase?"}],
            )

            shared = {
                "shared_context": {
                    "cwd": "/Users/micmur/GITHUB/o8s/services/robot-shop",
                },
                "cwd": "/Users/micmur/GITHUB/o8s/services/robot-shop",
                "session_id": SESSION_ID,
                "messages": goal.conversation,
                "task": goal,
            }
            update_todo_tools = PlanningTools.select({"update_todo"})

            manager_tools = PlanningTools
            devops_tools = CliTools | CodebaseReadTools | KubectlTools | update_todo_tools
            MetricsTools | CliTools | update_todo_tools
            CodebaseWriteTools | CodebaseReadTools | update_todo_tools

            devops_agent.bind_tools(devops_tools, shared)
            devops_agent.call_llm - "tools" >> devops_tools
            devops_tools >> devops_agent.summarize_context
            devops_agent.summarize_context >> devops_agent.call_llm

            devops_agent.register()

            # define behavior
            agent_manager.bind_tools(manager_tools, {**shared, "available_agents": "devops"})
            agent_manager.call_llm - "tools" >> manager_tools
            manager_tools >> agent_manager.summarize_context
            agent_manager.summarize_context >> agent_manager.call_llm
            # agent_manager.call_llm - "default" >> end

            # register agent
            agent_manager.register()
            print(agent_manager.get_flow_graph())
            agent_manager.get_flow_graph_png("agent_manager.png")
            await agent_manager.call(shared)
            # span.set_status(StatusCode.OK)

if __name__ == "__main__":

    asyncio.run(main())
