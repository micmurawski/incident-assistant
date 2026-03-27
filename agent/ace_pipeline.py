import glob
import json
import os
from datetime import datetime
from platform import node
from typing import Annotated, Literal, TypedDict

from agent.llm import LLMAgent
from agent.tasks.tasks import Task
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool
from framework import AsyncFlow
from typing import Optional

PossibleActions = Literal["ADD", "UPDATE", "DELETE", "NONE"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK_DIR = os.path.join(BASE_DIR, "playbooks")


class Operation(TypedDict):
    action: Annotated[PossibleActions, "The action to perform on the playbook"]
    section: Annotated[str, "The section of the playbook to perform the action on"]
    content: Annotated[str, "The content to perform the action on"]


class BulletTag(TypedDict):
    id: Annotated[str, "The id of the bulletpoint"]
    tag: Annotated[Literal["helpful", "harmful", "neutral"], "The tag for the bulletpoint"]


class Reflection(TypedDict):
    reasoning: Annotated[str, "Your chain of thought / reasoning / thinking process, detailed analysis and calculations"]
    error_identification: Annotated[str, "What specifically went wrong in the reasoning?"]
    root_cause_analysis: Annotated[str, "Why did this error occur? What concept was misunderstood?"]
    correct_approach: Annotated[str, "What should the model have done instead?"]
    key_insights: Annotated[list[str], "What strategy, formula, or principle should be remembered to avoid this error?"]
    bullet_tags: Annotated[list[BulletTag], "The tags for the bulletpoints"]


class Playbook:
    _instances: dict[str, "Playbook"] = {}

    @classmethod
    def get_instance(cls, playbook_id: str = "default") -> "Playbook":
        if playbook_id not in cls._instances:
            cls._instances[playbook_id] = cls.restore_latest(playbook_id)
        return cls._instances[playbook_id]

    def __init__(self, playbook_id: str = "default"):
        self.playbook_id = playbook_id
        self.iteration = 0
        self.playbook = {}
        self.storage_dir = os.path.join(PLAYBOOK_DIR, self.playbook_id)
        os.makedirs(self.storage_dir, exist_ok=True)

    def dump(self) -> str:
        data = {
            "playbook_id": self.playbook_id,
            "iteration": self.iteration,
            "playbook": self.playbook
        }
        file_path = os.path.join(self.storage_dir, f"playbook-{self.iteration}.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        return f"Playbook dumped to {file_path}"

    def dump_changes(self, change: dict) -> str:
        file_path = os.path.join(self.storage_dir, f"playbook-change-{change['iteration']}.json")
        with open(file_path, "w") as f:
            json.dump(change, f, indent=4)
        return f"Changes dumped to {file_path}"

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        instance = cls(data.get("playbook_id", "default"))
        instance.iteration = data["iteration"]
        instance.playbook = data["playbook"]
        return instance

    @classmethod
    def restore_latest(cls, playbook_id: str = "default") -> "Playbook":
        storage_dir = os.path.join(PLAYBOOK_DIR, playbook_id)
        if not os.path.exists(storage_dir):
            return cls(playbook_id)
        files = glob.glob(os.path.join(storage_dir, "playbook-*.json"))
        # Exclude change files from being restored as the main playbook
        playbook_files = [f for f in files if "playbook-change-" not in os.path.basename(f)]
        if not playbook_files:
            return cls(playbook_id)
        latest_file = max(playbook_files, key=lambda x: os.path.getctime(x))
        with open(latest_file, "r") as f:
            return cls.from_dict(json.load(f))

    def apply_operations(self, reasoning: str, operations: list[Operation]):
        change = {
            "iteration": self.iteration,
            "playbook_id": self.playbook_id,
            "playbook": self.playbook,
            "timestamp": datetime.now().isoformat(),
            "reasoning": reasoning,
            "operations": operations
        }
        self.dump_changes(change)
        for operation in operations:
            if operation["action"] == "ADD":
                self.playbook[operation["section"]] = operation["content"]
            elif operation["action"] == "UPDATE":
                self.playbook[operation["section"]] = operation["content"]
            elif operation["action"] == "DELETE":
                if operation["section"] in self.playbook:
                    del self.playbook[operation["section"]]
            elif operation["action"] == "NONE":
                pass
        self.iteration += 1
        self.dump()


@tool(tags=["ace", "curator"])
async def update_playbook(
    playbook: Hidden[Playbook],
    reasoning: Annotated[str, "The reasoning for the operations"],
    operations: Annotated[list[Operation], "The operations to perform on the playbook"],
    playbook_id: Annotated[Optional[str], "The ID of the playbook to update. If not provided, updates the current injected playbook."] = None,
) -> ToolResult:
    """
    Update a playbook with new insights or corrections.
    If playbook_id is provided, it will update that specific playbook instance.
    """
    target_playbook = playbook
    if playbook_id and playbook_id != playbook.playbook_id:
        target_playbook = Playbook.get_instance(playbook_id)

    target_playbook.apply_operations(reasoning, operations)
    return ToolResult(result=target_playbook.playbook, error=None)


@tool(tags=["ace", "reflector"])
async def reflect_on_playbook(
    reflections: Annotated[list[Reflection], "The reflection on the playbook"],
) -> ToolResult:
    return ToolResult(result=reflections, error=None)

ReflectorTools = Tools(tools=[reflect_on_playbook])
CuratorTools = Tools(tools=[update_playbook])


REFLECTOR_SYSTEM_PROMPT = """
You are an expert AppWorld coding agent and educator. Your job is to diagnose the current trajectory: identify what went wrong (or could be better), grounded in execution
feedback, API usage, unit test report, and ground truth when applicable.
Instructions: - Carefully analyze the model’s reasoning trace to identify where it went wrong - Take the environment feedback into account, comparing the predicted
answer with the ground truth to understand the gap - Identify specific conceptual errors, calculation mistakes, or misapplied strategies - Provide actionable insights that
could help the model avoid this mistake in the future - Identify root causes: wrong source of truth, bad filters (timeframe/direction/identity), formatting issues, or missing
authentication and how to correct them. - Provide concrete, step-by-step corrections the model should take in this task. - Be specific about what the model should have done
differently - You will receive bulletpoints that are part of playbook that’s used by the generator to answer the question. - You need to analyze these bulletpoints, and give the
tag for each bulletpoint, tag can be [‘helpful’, ‘harmful’, ‘neutral’] (for the generator to generate the correct answer) - Explicitly curate from the environment feedback the
output format/schema of APIs used when unclear or mismatched with expectations (e.g., apis.blah.show_contents() returns a list of content_ids (strings), not content
objects)

<Tasks>
{tasks}
</Tasks>

<Playbook>
{playbook}
</Playbook>
"""


CURATOR_SYSTEM_PROMPT = """
You are a master curator of knowledge. Your job is to identify what new insights should be added to an existing playbook based on a reflection from a previous attempt.
Context: - The playbook you created will be used to help answering similar questions. - The reflection is generated using ground truth answers that will NOT be available
when the playbook is being used. So you need to come up with content that can aid the playbook user to create predictions that likely align with ground truth.
Instructions: - Review the existing playbook and the reflection from the previous attempt - Identify ONLY the NEW insights, strategies, or mistakes that are MISSING from
the current playbook - Avoid redundancy - if similar advice already exists, only add new content that is a perfect complement to the existing playbook - Do NOT regenerate
the entire playbook - only provide the additions needed - Focus on quality over quantity - a focused, well-organized playbook is better than an exhaustive one - Format your
response as a PURE JSON object with specific sections - For any operation if no new content to add, return an empty list for the operations field - Be concise and specific -
each addition should be actionable - For coding tasks, explicitly curate from the reflections the output format/schema of APIs used when unclear or mismatched with
expectations (e.g., apis.blah.show_contents() returns a list of content_ids (strings), not content objects)
"""


class ReflectorAgent(LLMAgent):
    def __init__(self, name: str = "reflector", system_prompt: str = REFLECTOR_SYSTEM_PROMPT, **kwargs):
        super().__init__(name=name, system_prompt=system_prompt, **kwargs)


class CuratorAgent(LLMAgent):
    def __init__(self, name: str = "curator", system_prompt: str = CURATOR_SYSTEM_PROMPT, **kwargs):
        super().__init__(name=name, system_prompt=system_prompt, **kwargs)


reflector_agent = ReflectorAgent()
curator_agent = CuratorAgent()


reflector_agent.call_llm - "tools" >> ReflectorTools
ReflectorTools >> reflector_agent.call_llm


curator_agent.call_llm - "tools" >> CuratorTools
CuratorTools >> curator_agent.call_llm


@node
async def gather_last_tasks():
    last_tasks: list[Task] = []
    return {
        "tasks": last_tasks
    }


@node
async def create_curator_prompt(tasks: list[Task], reflections: list[Reflection]):
    return {
        "messages": []
    }

gather_last_tasks >> reflector_agent >> create_curator_prompt >> curator_agent
ACEPipeline = AsyncFlow(start=gather_last_tasks)


if __name__ == "__main__":
    ACEPipeline.run_async({})
