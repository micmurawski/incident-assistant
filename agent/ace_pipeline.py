from datetime import datetime
from platform import node
from agent.tooling.decorators import Hidden, ToolResult, tool, Tools
from agent.llm import LLMAgent
from typing import TypedDict, Literal, Annotated
import json
import os
import glob
from framework import AsyncFlow
from agent.tasks.tasks import Task


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
    @classmethod
    def get_instance(cls) -> "Playbook":
        if not hasattr(cls, "instance"):
            cls.instance = cls.restore_latest()
        return cls.instance

    def __init__(self):
        self.iteration = 0
        self.playbook = {}
        os.makedirs(PLAYBOOK_DIR, exist_ok=True)

    def dump(self) -> str:
        with open(os.path.join(PLAYBOOK_DIR, f"playbook-{self.iteration}.json"), "w") as f:
            json.dump(self.playbook, f, indent=4)
        return f"Playbook dumped to {os.path.join(PLAYBOOK_DIR, f'playbook-{self.iteration}.json')}"

    @staticmethod
    def dump_changes(change: dict) -> str:
        with open(os.path.join(PLAYBOOK_DIR, f"playbook-change-{change['iteration']}.json"), "w") as f:
            json.dump(change, f, indent=4)
        return f"Changes dumped to {os.path.join(PLAYBOOK_DIR, f'playbook-change-{change['iteration']}.json')}"

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        instance = cls()
        instance.iteration = data["iteration"]
        instance.playbook = data["playbook"]
        return instance

    @classmethod
    def restore_latest(cls) -> "Playbook":
        files = glob.glob(os.path.join(PLAYBOOK_DIR, "playbook-*.json"))
        if not files:
            return cls()
        latest_file = max(files, key=lambda x: os.path.getctime(x))
        with open(latest_file, "r") as f:
            return cls.from_dict(json.load(f))

    def apply_operations(self, reasoning: str, operations: list[Operation]):
        change = {
            "iteration": self.iteration,
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
) -> ToolResult:
    playbook.apply_operations(reasoning, operations)
    return ToolResult(result=playbook.playbook, error=None)


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
    pass


class CuratorAgent(LLMAgent):
    pass


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
