import asyncio

from ace.agents import create_curator_agent, create_reflector_agent
from ace.playbook_core import Playbook
from ace.utils import get_reflections
from agent.persistence.task_queries import fetch_last_root_tasks
from agent.tasks.tasks import Task
from framework import AsyncFlow
from framework.decorators import node


@node
async def gather_tasks(number_of_tasks: int, agent_name: str):
    last_tasks: list[Task] = fetch_last_root_tasks(number_of_tasks)
    return {
        "tasks": last_tasks,
        "agent_name": agent_name
    }


@node
async def reflect_on_tasks(tasks: list[Task], agent_name: str):
    reflections = {}
    for task in tasks:
        shared = {"messages": task.messages_history}
        reflector_agent = create_reflector_agent(agent_name, task)
        await reflector_agent.call(shared)

        reflections[task.id] = get_reflections(reflector_agent.get_shared()["messages"])
    return {
        "reflections": reflections
    }


@node
async def create_curator_prompt(reflections: list[dict], agent_name: str):
    playbook = Playbook.load_last_revision_of(agent_name)
    for task_id, reflections in reflections.items():
        print(f"Creating curator prompt for task {task_id}")
        curator_agent = create_curator_agent(agent_name, reflections)
        shared = {"playbook": playbook}
        await curator_agent.call(shared)


gather_tasks >> reflect_on_tasks >> create_curator_prompt
ACEPipeline = AsyncFlow(start=gather_tasks)


async def run_ace_pipeline(number_of_tasks: int, agent_name: str):
    return await ACEPipeline.run_async({
        "number_of_tasks": number_of_tasks,
        "agent_name": agent_name
    })

if __name__ == "__main__":
    asyncio.run(run_ace_pipeline(1, "test"))
