import asyncio
import os
from typing import Any, TypeVar

from framework import AsyncFlow
from framework.decorators import noop_async as end

from agent.file_ops import FileOpsManager
from agent.llm import LLMAgent
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools
from agent.tooling.cli import CliTools

T = TypeVar('T')


class Agent(LLMAgent):
    def __init__(self, name: str, system_prompt: str, api_settings: dict[str, Any] | None = None):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        self.cwd = settings.get("workspace.path") or os.getcwd()
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.file_ops_manager = FileOpsManager(cwd=self.cwd)
        self.name = name
        self.flow = AsyncFlow(start=self.call_llm)


async def main():
    settings = SettingsManager.get_instance()
    # memory_service = MemoryService()
    from agent.tooling.planning import PlanningTools
    tools = PlanningTools | CodebaseReadTools
    settings.get("workspace.path") or os.getcwd()
    settings.set("api.provider", "gemini")
    settings.set("api.model_id", "gemini-2.5-flash:thinking")
    settings.set("api.api_key", "AIzaSyAmNJmXdpejo2LQWDowsqsK3bvMhZSXfII")

    # settings.set("api.provider", "anthropic")
    # settings.set("api.model_id", "claude-sonnet-4-5:thinking")
    # settings.set("api.api_key", "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")

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
        conversation=[{"role": "user", "content": "Hey, may ask devops if we are using java in our production services?"}],
    )

    shared = {
        "messages": goal.conversation,
        "file_ops_manager": agent_manager.file_ops_manager,
        "task": goal,
        "llm": agent_manager,
    }

    devops_tools = CliTools | CodebaseReadTools | PlanningTools.select({"update_todo"})
    devops_agent.bind_tools(devops_tools, {"cwd": devops_agent.cwd})
    devops_agent.call_llm - "tools" >> devops_tools
    devops_agent.call_llm - "default" >> end
    devops_tools >> devops_agent.call_llm

    devops_agent.register()

    # define behavior
    agent_manager.bind_tools(tools, {"cwd": agent_manager.cwd, "available_agents": "coder, devops"})
    agent_manager.call_llm - "tools" >> tools
    agent_manager.call_llm - "default" >> end
    tools >> agent_manager.call_llm

    # register agent
    agent_manager.register()

    await agent_manager.call(shared)

if __name__ == "__main__":
    asyncio.run(main())
