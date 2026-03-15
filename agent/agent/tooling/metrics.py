from typing import Annotated, List, Literal, Optional

import yaml

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.report import build_status_report
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool
from agent.tooling.kubectl import get_pod_resource_limits

TimeWindow = Literal["5m", "15m", "30m"]


APPS = [
    "cart",
    "catalogue",
    "dispatch",
    "mongodb",
    "mysql",
    "payment",
    "shipping",
    "user",
    "web",
    "rabbitmq",
    "ratings",
    "redis",
]
# Explicit Literal so the type is valid and works with get_origin/get_args in decorators
AvailableApps = List[
    Literal[
        "cart", "catalogue", "dispatch", "mongodb", "mysql", "payment",
        "shipping", "user", "web", "rabbitmq", "ratings", "redis",
    ]
]
NAMESPACE = "application"


@tool(tags=["metrics"])
async def get_app_summary(
    grafana_client: Hidden[GrafanaClient],
    apps: Annotated[Optional[AvailableApps], "The list of app names to get a summary for"] = APPS,
    window: Annotated[Optional[TimeWindow], "The apps summary from the last X minutes"] = "5m",
    cwd: Hidden[Optional[str]] = None,
    env: Hidden[Optional[dict[str, str]]] = None,
) -> ToolResult:
    """Get a summary of the application's metric and logs."""
    cpu_limits: Optional[dict[str, float]] = None
    memory_limits: Optional[dict[str, float]] = None
    if cwd:
        cpu_limits, memory_limits = await get_pod_resource_limits(NAMESPACE, list(apps), cwd, env)
    report = build_status_report(
        grafana_client, NAMESPACE, list(apps), window,
        cpu_limits=cpu_limits, memory_limits=memory_limits,
    )
    return ToolResult(result=report, error=None)


@tool(tags=["metrics"])
async def query_loki(
    grafana_client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m"
) -> ToolResult:
    f"""Query the Loki logs. Remember to use correct namespace ({NAMESPACE}) and app names ({', '.join(APPS)})."""
    from_time = f"now-{time_window}"
    to_time = "now"
    logs = grafana_client.query_loki(query, from_time, to_time)
    entries = []
    for log in logs:
        msg = log.get("message", "")
        entries.append(
            {
                "timestamp": log.get("timestamp", ""),
                "message": msg,
                "labels": log.get("labels", {}),
            }
        )
    return ToolResult(result=yaml.dump(entries), error=None)


@tool(tags=["metrics"])
async def query_prometheus(
    grafana_client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m"
) -> ToolResult:
    f"""Query the Prometheus metrics. Remember to use correct namespace ({NAMESPACE}) and app names ({', '.join(APPS)})."""
    from_time = f"now-{time_window}"
    to_time = "now"
    metrics = grafana_client.query_prometheus(query, from_time, to_time)
    entries = []
    for metric in metrics:
        value = metric.get("value", [None, None])
        if value[0] is None or value[1] is None:
            continue
        timestamp = value[0]
        value = value[1]
        entries.append(
            {
                "timestamp": timestamp,
                "value": value,
                "labels": metric.get("labels", {}),
            }
        )
    return ToolResult(result=yaml.dump(entries), error=None)


MetricsTools = Tools(tools=[get_app_summary, query_loki, query_prometheus])
