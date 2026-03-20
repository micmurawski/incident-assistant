from typing import Annotated, List, Literal, Optional

import yaml

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.parsers import prase_to_table
from agent.grafana_client.report import (build_status_report)
from agent.tooling.cli import bash
from agent.tooling.decorators import Hidden, ToolResult, Tools, tool

TimeWindow = Literal["1m", "5m", "15m", "30m"]


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

Resources = Literal[
    "cronjobs",
    "daemonsets",
    "deployments",
    "jobs",
    "pods",
    "replicasets",
    "replicationcontrollers",
    "statefulsets",
]

RouteResources = Literal[
    "deployment",
    "service",
    "pod",
]


NAMESPACE = "application"
LINKERD_NAMESPACE = "bastion"


@tool(tags=["metrics"])
async def get_app_summary(
    grafana_client: Hidden[GrafanaClient],
    apps: Annotated[Optional[AvailableApps], "The list of app names to get a summary for"] = APPS,
    window: Annotated[Optional[TimeWindow], "The apps summary from the last X minutes"] = "5m",
    env: Hidden[Optional[dict[str, str]]] = None,
    cwd: Hidden[Optional[str]] = None,
) -> ToolResult:
    """Get a summary of the application's metric and logs."""
    report = await build_status_report(
        grafana_client, NAMESPACE, apps, window, env=env, cwd=cwd
    )
    return ToolResult(result=report, error=None)


@tool(tags=["metrics"])
async def query_loki(
    grafana_client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m"
) -> ToolResult:
    f"""Query the Loki logs. Remember to use correct namespace ({NAMESPACE}) and app names ({', '.join(APPS)}).
    Schema:
     - timestamp: float - the timestamp of the log line in seconds
     - message: str - the log line content
     - labels: map - key-value pairs attached to each log line
     - fields: map - key-value pairs parsed from the log line
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    logs = await grafana_client.query_loki(query, from_time, to_time)
    result = prase_to_table(logs, exclude_fields=["tsNs", "id"])
    return ToolResult(result=result, error=None)
    # result = yaml.dump(result)
    # logs = extract_loki_results(logs)
    # entries = []
    # for log in logs:
    #    # parse timestamp to datetime utc
    #    time_utc = datetime.fromtimestamp(log.get("timestamp", 0), tz=timezone.utc).isoformat()
    #    entries.append(
    #        {
    #            "datetime": time_utc,
    #            "message": log.get("message", ""),
    #            "labels": log.get("labels", {}),
    #            "fields": log.get("fields", {}),
    #        }
    #    )
    # return ToolResult(result=yaml.dump(entries), error=None)


@tool(tags=["metrics"])
async def query_prometheus(
    grafana_client: Hidden[GrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m",
    range_query: Annotated[Optional[bool], "If True, use range query"] = True,
) -> ToolResult:
    """
    Query the Prometheus metrics as a range query. Remember to use correct namespace and app names.
    Handles both simple vector and timeseries matrix responses.
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    result = await grafana_client.query_prometheus(query, from_time, to_time, instant=not range_query)
    return ToolResult(result=prase_to_table(result), error=None)


@tool(tags=["metrics"])
async def get_edges_summary(
    resource: Annotated[Optional[Resources],
                        "The resource to get the edges summary for (e.g., deployments, pods, etc.)"] = "deployments",
    env: Hidden[Optional[dict[str, str]]] = None,
    cwd: Hidden[Optional[str]] = None,
) -> ToolResult:
    """
    Get a summary of network edges (connections and communications) between resources 
    in the given namespace using Linkerd. The output includes information about which 
    services are communicating with each other in the service mesh.
    """
    cmd = f"linkerd viz edges {resource} --namespace {NAMESPACE} --linkerd-namespace {LINKERD_NAMESPACE}"
    return await bash(command=cmd, env=env, cwd=cwd)


@tool(tags=["metrics"])
async def get_resource_routes(
    resource_type: Annotated[Optional[RouteResources],
                             "The resource to get the routes for (e.g., deployments, pods, etc.)"] = "deployment",
    resource_id: Annotated[str, "The id of the resource to get the routes for"] = None,
    env: Hidden[Optional[dict[str, str]]] = None,
    cwd: Hidden[Optional[str]] = None,
) -> ToolResult:
    """Get the routes for a specific resource from the Linkerd instance."""
    if resource_id:
        resource_slug = f"{resource_type}/{resource_id}"
    else:
        resource_slug = resource_type

    cmd = f"linkerd viz routes {resource_slug} --namespace {NAMESPACE} --linkerd-namespace {LINKERD_NAMESPACE}"
    return await bash(command=cmd, env=env, cwd=cwd)


@tool(tags=["metrics"])
async def get_metric_metadata(
    grafana_client: Hidden[GrafanaClient],
    metric_name: Annotated[str, "The name of the metric to get the metadata for"],
) -> ToolResult:
    """Get the metadata for a specific metric from the Grafana instance."""
    metadata = await grafana_client.get_prometheus_metric_metadata(metric_name)
    if not metadata:
        return ToolResult(result="No metadata found for the metric", error=None)
    data = yaml.dump(metadata)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_metric_labels(
    grafana_client: Hidden[GrafanaClient],
    metric_name: Annotated[str, "The name of the metric to get the labels for"],
) -> ToolResult:
    """Get the labels for a specific metric from the Grafana instance."""
    labels = await grafana_client.list_prometheus_label_names(match=metric_name)
    data = yaml.dump(labels)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_metric_label_values(
    grafana_client: Hidden[GrafanaClient],
    label_name: Annotated[str, "The name of the label to get the values for"],
    metric_name: Annotated[str, "The name of the metric to get the values for"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m",
) -> ToolResult:
    """Get the values for a specific label from the Grafana instance."""
    from_time = f"now-{time_window}"
    to_time = "now"
    values = await grafana_client.list_prometheus_label_values(label_name=label_name, match=metric_name, from_time=from_time, to_time=to_time)
    data = yaml.dump(values)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_metrics(
    grafana_client: Hidden[GrafanaClient],
) -> ToolResult:
    """List all metrics from the Grafana instance."""
    metrics = await grafana_client.list_prometheus_metrics()

    def filter_unwanted_metrics(metrics: list[str]) -> list[str]:
        unwanted_prefixes = ("prometheus", "container_", "go_", "tokio_", "opentelemetry_")
        return [metric for metric in metrics if not any(metric.startswith(prefix) for prefix in unwanted_prefixes)]
    metrics = filter_unwanted_metrics(metrics)
    data = yaml.dump(metrics)
    return ToolResult(result=data, error=None)


MetricsTools = Tools(
    tools=[
        get_app_summary,
        query_loki,
        query_prometheus,
        get_edges_summary,
        get_resource_routes,
        get_metric_metadata,
        list_metric_label_values,
        list_metric_labels,
        list_metrics,
    ]
)


if __name__ == "__main__":
    import asyncio
    import os
    GRAFANA_URL = os.environ.get("GRAFANA_URL")
    GRAFANA_API_KEY = os.environ.get("GRAFANA_API_KEY")

    async def main():
        grafana_client = GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY)
        
        
        print("Testing get_app_summary...")
        result = await get_app_summary(grafana_client=grafana_client)
        print(result.result)
        exit()
        
        print("Testing query_loki...")
        # For demo purposes - parameters may need to be replaced with real ones that make sense for your environment.
        result = await query_loki(grafana_client=grafana_client, query='{app="shipping"}', time_window="1m")
        print(result.result)

        print("Testing get_resource_routes...")
        result = await get_resource_routes(resource_type="deployment", resource_id="cart")
        print(result.result)

        print("Testing get_edges_summary...")
        result = await get_edges_summary(resource="deployments")
        print(result.result)

        print("Testing range_query_prometheus...")
        result = await query_prometheus(grafana_client=grafana_client, query='sum(rate(up[5m]))', time_window="60m")
        print(result.result)

        # Test all metric tooling functions
        print("Testing get_metric_metadata...")
        result = await get_metric_metadata(grafana_client=grafana_client, metric_name="request_total")
        print(result.result)

        print("Testing list_metric_label_values...")
        result = await list_metric_label_values(grafana_client=grafana_client, label_name="instance", metric_name="up")
        print(result.result)

        print("Testing list_metric_labels...")
        result = await list_metric_labels(grafana_client=grafana_client, metric_name="up")
        print(result.result)

        print("Testing list_metrics...")
        result = await list_metrics(grafana_client=grafana_client)
        print(result.result)


    asyncio.run(main())
