"""RLM metrics sandbox tools: Python code execution against Grafana data via GrafanaPandasClient.

Full LLM-facing analysis guidance (workflow, APIs, examples) lives in:
``agent/agent/grafana_client/README_PANDAS.md`` (GrafanaPandasClient / SRE data science prompt).
Tool descriptions below summarize that contract for runtime tool selection and code generation.
"""

from pathlib import Path
from typing import Annotated

import yaml

from agent.rlm.container import ContainerRLMSandbox, ContainersResourceManager
from agent.tasks.tasks import Task
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

DEFAULT_IMAGE = "python:3.12-slim"


async def ensure_container_running(env: dict, task_id: str, session_id: str, cwd: str):
    # Container is scoped to the specific task
    container_id = f"rlm-metrics-{task_id}"
    if not ContainersResourceManager.does_container_exist(container_id, image=DEFAULT_IMAGE, env=env):
        container: ContainerRLMSandbox = ContainersResourceManager.get_container(
            container_id, image=DEFAULT_IMAGE, env=env)

        # Handover directory: shared across all tasks in the same session (root task hierarchy)
        handover_dir = Path(cwd) / "handover" / session_id
        handover_dir.mkdir(parents=True, exist_ok=True)

        agent_dir = Path(__file__).resolve().parent.parent
        volumes = {
            str(agent_dir): {"bind": "/app/agent", "mode": "ro"},
            str(handover_dir): {"bind": "/app/handover", "mode": "rw"},
        }
        container.start(volumes=volumes)
        await container.pip_install(["pandas", "httpx"])
        init_script = """
import os
import pandas as pd
from agent.grafana_client import GrafanaClient, GrafanaPandasClient

url = os.getenv("GRAFANA_URL")
token = os.getenv("GRAFANA_API_KEY")

# Initialize the SYNC client
pd_client = GrafanaPandasClient(url, token)
print(f"Successfully initialized GrafanaPandasClient in container under variable name 'pd_client', and imported pandas as pd")
        """
        result = await container.execute_code(init_script)
        print("--------------------------------")
        print("INIT SCRIPT RESULT:")
        print(result)
        print("--------------------------------")
    else:
        container: ContainerRLMSandbox = ContainersResourceManager.get_container(
            container_id, image=DEFAULT_IMAGE, env=env)
    return container


@tool(tags=["rlm_metrics"])
async def execute_code(
    env: Hidden[dict],
    cwd: Hidden[str],
    task: Hidden[Task],
    code: Annotated[
        str,
        "Python 3 snippet run in the metrics sandbox. Globals include pd (pandas) and pd_client "
        "(sync GrafanaPandasClient; do not await). Use it to query and analyze logs/metrics; prefer "
        "print(), str(), and tabular output. See tool description for API and workflow.",
    ],
) -> ToolResult:
    """Run Python in an isolated container to analyze Grafana logs and Prometheus metrics as DataFrames.

    **Purpose:** SRE-style data analysis at runtime—discover label values, pull time-series or logs into
    pandas, aggregate and pattern-match to support incident/root-cause reasoning.

    **Environment & Continuity:**
    - Each task has its own isolated container. State (variables) is NOT shared between parent and child tasks.
    - However, all tasks in the same session share a **handover volume** at `/app/handover/`. You can share
      DataFrames between different agents or sub-tasks by saving them as CSVs to this path.
    - ``pd`` — pandas.
    - ``pd_client`` — ``GrafanaPandasClient`` (synchronous; call methods directly, no ``await``).
    - Grafana URL/token come from the container env (``GRAFANA_URL``, ``GRAFANA_TOKEN``).

    **Discovery (narrow what to query):**
    - ``pd_client.list_loki_label_values(label_name, query='{namespace="app"}')`` — distinct Loki label values.
    - ``pd_client.list_metrics(match='{namespace="prod"}')`` — metric names.
    - ``pd_client.get_label_values(label_name, match='metric_name')`` — Prometheus label values.

    **Query (load data):**
    - ``pd_client.query_prometheus(expr, from_time='now-1h')`` — columns include ``timestamp``, ``metric``,
      ``value`` and labels.
    - ``pd_client.query_loki(expr, from_time='now-1h')`` — columns include ``timestamp``,
      ``message`` and ``label_*``.

    **Suggested workflow:** (1) Discover labels. (2) Fetch data. (3) Analyze. (4) Save results to
    `/app/handover/stage2.csv` and hand over to another agent.
    """

    container: ContainerRLMSandbox = await ensure_container_running(env, task.id, task.root.id, cwd)
    result = await container.execute_code(code)
    print("--------------------------------")
    print(result)
    print("--------------------------------")
    return ToolResult(result=result, error=None)


@tool(tags=["rlm_metrics"])
async def export_dataframe(
    env: Hidden[dict],
    task: Hidden[Task],
    cwd: Hidden[str],
    name: Annotated[str, "The name of the DataFrame variable to export."],
    path: Annotated[str, "The target filename in the handover directory (e.g., 'stage2.csv')."],
) -> ToolResult:
    """Exports a pandas DataFrame from the task's sandbox to the shared handover volume.
    The file will be available to all tasks in this session at `/app/handover/<path>`.
    """
    handover_path = Path("app/handover") / task.id / path
    code = f"import pandas as pd\n{name}.to_csv('{handover_path}', index=False)\nprint(f\"Exported '{name}' to '{handover_path}'\")"
    container: ContainerRLMSandbox = await ensure_container_running(env, task.id, task.root.id, cwd)
    await container.execute_code(code)
    return ToolResult(result=f"{name} exported to {handover_path}", error=None)


@tool(tags=["rlm_metrics"])
async def execution_history(
    env: Hidden[dict],
    task: Hidden[Task],
    cwd: Hidden[str],
    limit: Annotated[int, "The number of history entries to return"] = 10,
) -> ToolResult:
    """Return prior code snippets and outputs from this task's metrics sandbox as YAML text.
    Use when you need to review what you've already done in this specific task.
    """

    container: ContainerRLMSandbox = await ensure_container_running(env, task.id, task.root.id, cwd)
    history = await container.get_history(limit=limit)
    history_str = yaml.dump(history)
    return ToolResult(result=history_str, error=None)


REPLTools = Tools(tools=[execute_code, execution_history])
