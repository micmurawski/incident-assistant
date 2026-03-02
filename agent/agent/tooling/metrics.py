from typing import Annotated, Literal, Optional

import yaml

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.report import build_status_report
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

TimeWindow = Literal["5m", "15m", "30m"]

APPS = ["sample-app"]
NAMESPACE = "application"


@tool(tags=["metrics"])
async def get_app_summary(
    client: Hidden[GrafanaClient],
    apps: Annotated[Optional[list[str]], "The list of app names to get a summary for"] = APPS,
    window: Annotated[Optional[TimeWindow], "The apps summary from the last X minutes"] = "5m"
) -> ToolResult:
    """Get a summary of the application's metric and logs."""
    report = build_status_report(client, NAMESPACE, apps, window)
    return ToolResult(result=report, error=None)


@tool(tags=["metrics"])
async def query_loki(
    client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m"
) -> ToolResult:
    f"""Query the Loki logs. Remember to use correct namespace ({NAMESPACE}) and app names ({', '.join(APPS)})."""
    from_time = f"now-{time_window}"
    to_time = "now"
    logs = client.query_loki(query, from_time, to_time)
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
    client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m"
) -> ToolResult:
    f"""Query the Prometheus metrics. Remember to use correct namespace ({NAMESPACE}) and app names ({', '.join(APPS)})."""
    from_time = f"now-{time_window}"
    to_time = "now"
    metrics = client.query_prometheus(query, from_time, to_time)
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
