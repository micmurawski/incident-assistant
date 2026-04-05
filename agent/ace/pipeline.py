import asyncio
import json

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
    reflections: dict[str, list[dict]] = {}
    for task in tasks:
        playbook = Playbook.load_last_revision_of(agent_name)
        shared = {
            "messages": [{"role": "user", "content": "proceed with reflection on task"}],
            "playbook": playbook
        }
        with create_reflector_agent(agent_name, task, playbook) as reflector_agent:
            await reflector_agent.call(shared)

        reflections[task.id] = get_reflections(shared["messages"])
    return {
        "reflections": reflections
    }


@node
async def create_curator_prompt(reflections: dict[str, list[dict]], agent_name: str):
    print("These are reflections:")
    for task_id, task_reflections in reflections.items():
        for reflection in task_reflections:
            print(json.dumps(reflection, indent=4))
        print({"task_id": task_id, "reflections": task_reflections})
    playbook = Playbook.load_last_revision_of(agent_name)
    for task_id, task_reflections in reflections.items():
        with create_curator_agent(agent_name, task_reflections, playbook) as curator_agent:
            shared = {
                "messages": [{"role": "user", "content": "proceed with curation of reflections"}],
                "playbook": playbook,
            }
            await curator_agent.call(shared)
    return {}


gather_tasks >> reflect_on_tasks >> create_curator_prompt
ACEPipeline = AsyncFlow(start=gather_tasks)


async def run_ace_pipeline(number_of_tasks: int, agent_name: str):
    return await ACEPipeline.run_async({
        "number_of_tasks": number_of_tasks,
        "agent_name": agent_name
    })

if __name__ == "__main__":
    playbook = Playbook.load_last_revision_of("incident_commander")
    data = playbook.model_dump()
    print(json.dumps(data, indent=4))
    Playbook.from_dict(data)
    print(playbook.to_markdown(without_bullets_ids=False, positive_only=False, without_points=False))
    asyncio.run(run_ace_pipeline(1, "incident_commander"))
