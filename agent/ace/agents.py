import os
from contextlib import contextmanager
from typing import Generator

import yaml
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from ace.playbook_core import Playbook
from ace.prompts import (CURATOR_SYSTEM_PROMPT_TEMPLATE,
                         REFLECTOR_SYSTEM_PROMPT_TEMPLATE)
from ace.tools import CuratorTools, ReflectorTools
from ace.utils import create_details_for_reflector
from agent.llm import LLMAgent
from agent.settings import SettingsManager
from agent.tasks.tasks import Task


def configure_settings(project_name: str, provider: str = "minimax") -> trace.Tracer:
    settings = SettingsManager.get_instance()
    settings.set("api.provider", provider)
    settings.set("api.api_key", os.environ["MINIMAX_API_KEY"])
    tracer_provider = register(project_name=project_name)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    return trace.get_tracer(__name__)


@contextmanager
def create_reflector_agent(agent_name: str, task: Task, playbook: Playbook) -> Generator[LLMAgent, None, None]:
    name = f"{agent_name}-reflector"
    tracer = configure_settings(project_name=name)
    system_prompt = REFLECTOR_SYSTEM_PROMPT_TEMPLATE.format(
        details=create_details_for_reflector(task, playbook), agent_name=agent_name)
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("--------------------------------")
    agent = LLMAgent(
        name=name,
        system_prompt=system_prompt,
        tools=ReflectorTools,
    )

    with tracer.start_as_current_span(name):
        yield agent


@contextmanager
def create_curator_agent(agent_name: str, reflections: list[dict], playbook: Playbook) -> Generator[LLMAgent, None, None]:
    name = f"{agent_name}-curator"
    tracer = configure_settings(project_name=name)
    reflections_yaml = yaml.dump(reflections, indent=4, sort_keys=False)
    system_prompt = CURATOR_SYSTEM_PROMPT_TEMPLATE.format(
        reflections=reflections_yaml,
        playbook=playbook.to_markdown(),
    )
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("--------------------------------")
    agent = LLMAgent(
        name=f"{agent_name}-reflector",
        system_prompt=system_prompt,
        tools=CuratorTools,
    )
    with tracer.start_as_current_span(name):
        yield agent
