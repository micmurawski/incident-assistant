import asyncio
from typing import Any

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
    return {"tasks_map": tasks_map}


@node
async def reflect_on_tasks(tasks_map: dict[str, list[Task]]):
    result: dict[str, dict[str, Any]] = {}
    playbooks: dict[str, Playbook] = {}
    
    for assignee in tasks_map.keys():
        playbooks[assignee] = Playbook.load_last_revision_of(assignee)
        playbooks[assignee].auto_save = False
            
    for assignee, tasks in tasks_map.items():
        result[assignee] = {
            "assignee": assignee,
            # Finalize this after reflector tool calls mutate scores.
            "playbook_snapshot": None,
            "rev_number": playbooks[assignee].number_of_revisions,
            "reflections": [],
        }

        for task in tasks:
            reflection_shared = {
                "messages": [{"role": "user", "content": "proceed with reflection on task"}],
            }
            with create_reflector_agent(assignee, task, playbooks) as reflector_agent:
                await reflector_agent.call(reflection_shared)

            reflections = get_reflections(reflection_shared["messages"])
            for reflection in reflections:
                assignee_ref = reflection.get("assignee") or assignee
                result[assignee_ref]["reflections"].append(reflection)
        result[assignee]["playbook_snapshot"] = playbooks[assignee].to_dict()

    return {"reflections_by_assignee": result}


@node
async def create_curator_prompt(reflections_by_assignee: dict[str, dict[str, Any]]):
    for assignee, data in reflections_by_assignee.items():
        playbook = Playbook.from_dict(
            data["playbook_snapshot"],
            rev_number=data["rev_number"],
            auto_save=False,
        )
        with create_curator_agent(assignee, data["reflections"], playbook) as curator_agent:
            curator_shared = {
                "messages": [{"role": "user", "content": "proceed with curation of reflections"}],
            }
            await curator_agent.call(curator_shared)
        playbook.commit()
    return {}


gather_tasks >> reflect_on_tasks >> create_curator_prompt
ACEPipeline = AsyncFlow(start=gather_tasks)


async def run_ace_pipeline(n: int = 5, last: bool = True):
    return await ACEPipeline.run_async({
        "n": n,
        "last": last
    })

if __name__ == "__main__":
    asyncio.run(run_ace_pipeline())
