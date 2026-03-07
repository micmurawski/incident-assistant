

import asyncio
import os
import uuid
from typing import Any, TypeVar

from framework import AsyncFlow
from openinference.instrumentation import using_attributes
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.file_ops import FileOpsManager
from agent.llm import LLMAgent
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools
from agent.tooling.cli import CliTools
from agent.tracing import trace_flow

T = TypeVar('T')


os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

SESSION_ID = str(uuid.uuid4())
tracer_provider = register(project_name="agent-tracing")

# Get a tracer for your application
tracer = trace.get_tracer(__name__)


#OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
#GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

class Agent(LLMAgent):
    def __init__(self, name: str, system_prompt: str, api_settings: dict[str, Any] | None = None):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        self.cwd = settings.get("workspace.path") or os.getcwd()
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.file_ops_manager = FileOpsManager(cwd=self.cwd)
        self.name = name

        @trace_flow(flow_name=name)
        class _TracedFlow(AsyncFlow):
            def __init__(self, start):
                super().__init__(start=start)
        self.flow = _TracedFlow(start=self.call_llm)


async def main():
    with tracer.start_as_current_span("agent-execution-flow-session-" + SESSION_ID):
        with using_attributes(session_id=SESSION_ID):
            settings = SettingsManager.get_instance()
            # memory_service = MemoryService()
            from agent.tooling.planning import PlanningTools
            tools = PlanningTools | CodebaseReadTools
            settings.get("workspace.path") or os.getcwd()
            #settings.set("api.provider", "gemini")
            #settings.set("api.model_id", "gemini-2.5-flash")
            #settings.set("api.api_key", "AIzaSyAmNJmXdpejo2LQWDowsqsK3bvMhZSXfII")
            settings.set("api.provider", "minimax")
            settings.set("api.model_id", "MiniMax-M2.5")
            settings.set("api.api_key", os.getenv("MINIMAX_API_KEY"))

            agent_manager = Agent(
                name="agent manager",
                system_prompt="You are a manager of agents. You are responsible for assigning tasks to agents and ensuring they are completed.",
            )

            devops_agent = Agent(
                name="devops",
                system_prompt="You are a devops helper. You are responsible for helping with the devops tasks.",
            )

            from agent.tasks.tasks import Task

            goal = Task(
                id="123",
                assignee="helpful_agent",
                assigner="human",
                conversation=[
                    {"role": "user", "content": "Can you list files in the current directory?"}],
            )

            shared = {
                "session_id": SESSION_ID,
                "messages": goal.conversation,
                "file_ops_manager": agent_manager.file_ops_manager,
                "task": goal,
                "llm": agent_manager,
                "cwd": agent_manager.cwd,
            }

            devops_tools = CliTools | CodebaseReadTools | PlanningTools.select({"update_todo"})
            devops_agent.bind_tools(devops_tools, {"cwd": devops_agent.cwd})
            devops_agent.call_llm - "tools" >> devops_tools
            devops_tools >> devops_agent.summarize_context
            devops_agent.summarize_context >> devops_agent.call_llm

            devops_agent.register()

            # define behavior
            agent_manager.bind_tools(tools, {"cwd": agent_manager.cwd, "available_agents": "coder, devops"})
            agent_manager.call_llm - "tools" >> tools
            tools >> agent_manager.summarize_context
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
