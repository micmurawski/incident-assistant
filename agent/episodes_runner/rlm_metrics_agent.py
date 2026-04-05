import asyncio
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from agent.llm import LLMAgent
from agent.persistence.settings import init_db
from agent.tasks.tasks import Task
from agent.tooling.rlm_metrics import REPLTools
from episodes_runner.utils import configure_settings

SYSTEM_PROMPT = """
You are in a Python 3 environment where a `pd_client` (of type `GrafanaPandasClient`) is already initialized and available in your global context. 
Your goal is to "fish" for root causes in the cluster.

**Environment Capabilities:**
- **Pre-loaded Client**: Use `pd_client` directly (Sync, no `await` needed).
- **No Graphics**: Do not attempt to use `plt.show()` or `.plot()`. Always output insights as text, tables, or `print()` statements.
- **Auto-Flattening**: Loki logs are already expanded into `label_<name>` columns.

**Available Discovery Methods:**
- `pd_client.list_loki_label_values(label_name, query='{namespace="app"}')` -> Series of distinct label values.
- `pd_client.list_metrics(match='{namespace="prod"}')` -> Series of metric names.
- `pd_client.get_label_values(label_name, match='metric_name')` -> Series of Prometheus label values.

**Available Query Methods:**
- `pd_client.query_prometheus(expr, from_time='now-1h')` -> DataFrame with: `timestamp`, `metric`, `value`, and all labels.
- `pd_client.query_loki(expr, from_time='now-1h', limit=5000)` -> DataFrame with: `timestamp`, `message`, `label_<name>`.

**Your Analysis Workflow:**
1. **Discover**: Use `list_loki_label_values` to find which apps are throwing errors.
2. **Fetch**: Pull logs or metrics into a DataFrame using `query_loki` or `query_prometheus`.
3. **Analyze**: Use `df.value_counts()`, `df.groupby()`, or string manipulation to identify the most common error patterns or temporal spikes.
4. **Report**: Summarize your findings based on the data patterns you've uncovered.

**Example Task:** "Analyze the distribution of error messages for the 'payment' app over the last hour."
```python
# Example of what the Agent should write:
df_logs = pd_client.query_loki('{app="payment"} |= "error"', from_time="now-10m")
# Group by normalized message (remove digits/IDs)
patterns = df_logs['message'].str.replace(r'\d+', 'N', regex=True).value_counts().head(10)
print("Top 10 Error Patterns for 'payment':")
print(patterns)
```
YOUR APPLICATION NAMESPACE IS "application"
"""


@contextmanager
def create_rlm_metrics_agent(
    name: str,
    provider: str = "minimax",
    project_name: str = "rlm-metrics-agent"
) -> LLMAgent:
    tracer = configure_settings(project_name, provider)
    workspace_path = Path("/Users/micmur/GITHUB/o8s/workspace")
    api_key_path = Path("/Users/micmur/GITHUB/o8s/api_key.json")
    with open(api_key_path) as f:
        data = json.load(f)
        GRAFANA_URL = data["grafana_url"]
        GRAFANA_API_KEY = data["grafana_api_token"]
    shared_context = {
        "cwd": str(workspace_path),
        "env": {
            "AWS_ACCESS_KEY_ID": data["incident-assistant"]["access_key_id"],
            "AWS_SECRET_ACCESS_KEY": data["incident-assistant"]["secret_access_key"],
            "GRAFANA_URL": GRAFANA_URL,
            "GRAFANA_API_KEY": GRAFANA_API_KEY,
            "AWS_REGION": "us-east-1",
        },
    }
    with tracer.start_as_current_span(name):
        yield LLMAgent(
            name=name,
            system_prompt=SYSTEM_PROMPT,
            tools=REPLTools,
            shared_context=shared_context,
        )


async def main():
    init_db()
    agent: LLMAgent
    with create_rlm_metrics_agent("rlm-metrics-agent") as agent:
        SESSION_ID = str(uuid.uuid4())
        goal = Task.create_root_task(
            id=SESSION_ID,
            assignee="rlm-metrics-agent",
            assigner="human",
            content="Can you analyze metrics and logs and tell me if there is any issue with the cluster?",
        )
        shared = {
            "task": goal,
            "messages": goal.conversation
        }
        result = await agent.call(shared=shared)
        print(result)
        goal.save()

if __name__ == "__main__":
    asyncio.run(main())
