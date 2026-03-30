import yaml

from ace.prompts import (CURATOR_SYSTEM_PROMPT_TEMPLATE,
                         REFLECTOR_SYSTEM_PROMPT_TEMPLATE)
from ace.tools import CuratorTools, ReflectorTools
from ace.utils import create_details_for_reflector
from agent.llm import LLMAgent
from agent.tasks.tasks import Task


def create_reflector_agent(agent_name: str, task: Task) -> LLMAgent:
    system_prompt = REFLECTOR_SYSTEM_PROMPT_TEMPLATE.format(
        details=create_details_for_reflector(task), agent_name=agent_name)
    return LLMAgent(
        name=f"{agent_name}-reflector",
        system_prompt=system_prompt,
        tools=ReflectorTools,
    )


def create_curator_agent(agent_name: str, reflections: list[dict]) -> LLMAgent:
    reflections_yaml = yaml.dump(reflections, indent=4, sort_keys=False)
    system_prompt = CURATOR_SYSTEM_PROMPT_TEMPLATE.format(
        reflections=reflections_yaml)
    return LLMAgent(
        name=f"{agent_name}-reflector",
        system_prompt=system_prompt,
        tools=CuratorTools,
    )
