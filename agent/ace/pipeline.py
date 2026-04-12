import asyncio

from ace.agents import create_curator_agent, create_reflector_agent
from ace.playbook_core import Playbook
from ace.utils import get_reflections
from agent.persistence.task_queries import fetch_tasks_by_assignee
from agent.tasks.tasks import Task
from framework import AsyncFlow
from framework.decorators import node


@node
async def gather_tasks(n: int = 5, last: bool = True):
    tasks_map = fetch_tasks_by_assignee(n, last)
    items = []
    for assignee, tasks in tasks_map.items():
        if assignee != "incident_commander":
            continue
        print(f"Assignee: {assignee}")
        for task in tasks:
            print(f"Task: {task.id}")
        items.append({"assignee": assignee, "tasks": tasks})
    return {
        "items": items[:1]
    }


@node(batch=True)
async def reflect_on_tasks(assignee: str, tasks: list[Task]):
    reflections: list[dict] = []
    playbook = Playbook.load_last_revision_of(assignee)

    for task in tasks:
        shared = {
            "messages": [{"role": "user", "content": "proceed with reflection on task"}],
            "playbook": playbook
        }
        with create_reflector_agent(assignee, task, playbook) as reflector_agent:
            await reflector_agent.call(shared)
        reflections.extend(get_reflections(shared["messages"]))

    return {
        "assignee": assignee,
        "reflections": reflections
    }


@node
async def create_curator_prompt(results: list[dict] | None = None):
    for r in results or []:
        assignee = r["assignee"]
        reflections = r["reflections"]
        playbook = Playbook.load_last_revision_of(assignee)
        with create_curator_agent(assignee, reflections, playbook) as curator_agent:
            shared = {
                "messages": [{"role": "user", "content": "proceed with curation of reflections"}],
                "playbook": playbook,
            }
            await curator_agent.call(shared)
    return {}


gather_tasks >> reflect_on_tasks >> create_curator_prompt
ACEPipeline = AsyncFlow(start=gather_tasks)


async def run_ace_pipeline(n: int = 5, last: bool = False):
    return await ACEPipeline.run_async({
        "n": n,
        "last": last
    })

if __name__ == "__main__":
    asyncio.run(run_ace_pipeline())
