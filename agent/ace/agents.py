import os
from contextlib import contextmanager
from typing import Generator

from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from ace.playbook_core import Playbook
from ace.prompts import (CURATOR_SYSTEM_PROMPT_TEMPLATE_V2,
                         REFLECTOR_SYSTEM_PROMPT_TEMPLATE_V2,
                         format_tools_for_prompt, save_execution_prompt)
from ace.tools import CuratorTools, ReflectorTools
from ace.utils import (format_reflector_task_data_for_task,
                       format_reflector_task_data_for_tasks)
from ace.yaml_dump import dump_yaml_multiline
from agent.llm import LLMAgent
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling.cli import CliTools
from agent.tooling.codebase_read import CodebaseReadTools
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app
from agent.tooling.eks import EksReadTools, EksWriteTools
from agent.tooling.kubectl import (KubectlReadTools, KubectlWriteTools,
                                   kubectl_get_resources)
from agent.tooling.metrics import MetricsSummaryTools
from agent.tooling.planning import PlanningTools
from agent.tooling.rlm_metrics import REPLTools

incident_commander_tools = PlanningTools | deploy_app  # |CliTools
metrics_tools = REPLTools | PlanningTools | MetricsSummaryTools | kubectl_get_resources

devops_read_tools = CliTools | CodebaseReadTools | KubectlReadTools | EksReadTools | PlanningTools
devops_write_tools = CodebaseWriteTools | CliTools | KubectlWriteTools | EksWriteTools | PlanningTools

coder_tools = CodebaseReadTools | CodebaseWriteTools | CliTools | PlanningTools

devops_tools = devops_read_tools | devops_write_tools

TOOLS_MAP = {
    "incident_commander": incident_commander_tools,
    "monitoring_agent": metrics_tools,
    "devops_agent": devops_tools,
    "coder_agent": coder_tools,
}


def configure_settings(project_name: str, provider: str = "minimax") -> trace.Tracer:
    settings = SettingsManager.get_instance()
    settings.set("api.provider", provider)
    settings.set("api.api_key", os.environ["MINIMAX_API_KEY"])
    tracer_provider = register(project_name=project_name)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    return trace.get_tracer(__name__)


@contextmanager
def create_reflector_agent(
    agent_name: str,
    tasks: list[Task] | Task,
    playbook: Playbook,
    user_message: str = "proceed with reflection on task",
) -> Generator[LLMAgent, None, None]:
    name = f"{agent_name}-reflector"
    tracer = configure_settings(project_name=name)
    if isinstance(tasks, list):
        details = format_reflector_task_data_for_tasks(tasks)
    else:
        details = format_reflector_task_data_for_task(tasks)

    system_prompt = REFLECTOR_SYSTEM_PROMPT_TEMPLATE_V2.format(
        details=details,
        agent_name=agent_name,
        playbook=playbook.to_markdown(without_points=True),
        agent_tools=format_tools_for_prompt(TOOLS_MAP[agent_name]),
    )
    save_execution_prompt("reflector", agent_name, system_prompt, user_message)

    agent = LLMAgent(
        name=name,
        system_prompt=system_prompt,
        tools=ReflectorTools,
    )

    with tracer.start_as_current_span(name):
        yield agent


@contextmanager
def create_curator_agent(
    agent_name: str,
    reflections: list[dict],
    playbook: Playbook,
    user_message: str = "proceed with curation of reflections",
) -> Generator[LLMAgent, None, None]:
    name = f"{agent_name}-curator"
    tracer = configure_settings(project_name=name)
    reflections_yaml = dump_yaml_multiline(reflections, indent=4, sort_keys=False)
    system_prompt = CURATOR_SYSTEM_PROMPT_TEMPLATE_V2.format(
        reflections=reflections_yaml,
        playbook=playbook.to_markdown(),
        agent_name=agent_name,
        agent_tools=format_tools_for_prompt(TOOLS_MAP[agent_name]),
    )
    save_execution_prompt("curator", agent_name, system_prompt, user_message)
    print("SYSTEM PROMPT:")
    print(system_prompt)
    print("--------------------------------")
    agent = LLMAgent(
        name=f"{agent_name}-curator",
        system_prompt=system_prompt,
        tools=CuratorTools,
    )
    with tracer.start_as_current_span(name):
        yield agent
