import json
import os
import time

from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app

WRITE_TOOLS = [f.name for f in CodebaseWriteTools.tools]
DEPLOY_TOOLS = [deploy_app.name]


def configure_settings(project_name: str, provider: str = "minimax") -> None:
    settings = SettingsManager.get_instance()
    settings.set("api.provider", provider)
    settings.set("api.api_key", os.environ["MINIMAX_API_KEY"])
    tracer_provider = register(project_name=project_name)
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
    return trace.get_tracer(__name__)


def collect_tasks(t: Task) -> list[Task]:
    all_tasks = []
    all_tasks.append(t)
    for child in t.children:
        all_tasks.extend(collect_tasks(child))
    return all_tasks


def collect_meaningful_actions(goal: Task) -> tuple[list[str], set[str], bool]:
    all_tasks = collect_tasks(goal)
    deploy_app_called = False
    meaningful_actions = []
    modified_files = set()
    for t in all_tasks:
        for tu in t.get_tool_usage():
            name = tu.get("name")
            if name in DEPLOY_TOOLS:
                deploy_app_called = True
                meaningful_actions.append("- Action: `deploy_app` was executed.")
            elif name in WRITE_TOOLS:
                # Try to extract file path from various possible input schemas
                inp: dict = tu.get("input", {})
                path = (
                    inp.pop("path", None)
                    or inp.pop("filename", None)
                    or inp.pop("file_path", None)
                )
                if path:
                    modified_files.add(path)
                    meaningful_actions.append(f"- Action: `{name}` modified \n `{json.dumps(inp, indent=4)}`")
    return meaningful_actions, modified_files, deploy_app_called


def live_timer(seconds: int | float):
    start_time = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= seconds:
                break
            print(f"\rElapsed time: {elapsed:.0f} seconds", end="", flush=True)

            time.sleep(0.5)  # Update frequently for a smooth look
    except KeyboardInterrupt:
        print("\nTimer stopped.")
