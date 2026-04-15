from typing import Annotated, List, Literal, Optional

import yaml

from agent.grafana_client.client import (AsyncGrafanaClient,
                                         GrafanaBadRequestError)
from agent.grafana_client.parsers import (extract_labels, extract_loki_results,
                                          group_by_similarity, prase_to_table)
from agent.grafana_client.report import build_status_report
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


def _grafana_bad_request_result(exc: GrafanaBadRequestError) -> ToolResult:
    return ToolResult(result=None, error=exc.message)


def _ensure_namespace_in_query(query: str | None) -> str:
    if query is None:
        return f"{{namespace=\"{NAMESPACE}\"}}"
    else:
        extracted_labels = extract_labels(query)
        extracted_labels.update({"namespace": NAMESPACE})
        return f"{{{','.join([f'{k}="{v}"' for k, v in extracted_labels.items()])}}}"


async def _loki_label_validation_message(
    grafana_client: AsyncGrafanaClient,
    query: str,
    from_time: str,
    to_time: str,
) -> str | None:
    """If stream-selector label names are unknown for the time range, return a warning line."""
    labels = extract_labels(query)
    if not labels:
        return None
    issues: list[str] = []
    try:
        known_names = set(await grafana_client.list_loki_labels(from_time, to_time, query=None))
    except GrafanaBadRequestError:
        raise
    for name in labels.keys():
        if name not in known_names:
            issues.append(f'label name {name!r} is not present in Loki for this time range')
    if not issues:
        return None
    return 'NOTE: ' + '; '.join(issues) + '. Use tool list_loki_labels to get the available labels.'


async def _prometheus_label_validation_message(
    grafana_client: AsyncGrafanaClient,
    query: str,
    from_time: str,
    to_time: str,
) -> str | None:
    """If selector label names are unknown for the time range, return a warning line."""
    labels = extract_labels(query)
    if not labels:
        return None
    issues: list[str] = []
    known_names = set(await grafana_client.get_label_names(match=None, from_time=from_time, to_time=to_time))
    for name in labels.keys():
        if name not in known_names:
            issues.append(f'label name {name!r} is not present in Prometheus for this time range')
    if not issues:
        return None
    return 'NOTE: ' + '; '.join(issues) + '. Use tool list_metric_labels to get the available labels.'


@tool(tags=["metrics"])
async def get_app_summary(
    grafana_client: Hidden[AsyncGrafanaClient],
    apps: Annotated[Optional[AvailableApps], "The list of app names to get a summary for"] = APPS,
    window: Annotated[Optional[TimeWindow], "The apps summary from the last X minutes"] = "5m",
    env: Hidden[Optional[dict[str, str]]] = None,
    cwd: Hidden[Optional[str]] = None,
) -> ToolResult:
    """Get a summary of the application's metric and logs."""
    try:
        report = await build_status_report(
            grafana_client, NAMESPACE, apps, window, env=env, cwd=cwd
        )
        return ToolResult(result=report, error=None)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)


@tool(tags=["metrics", "logs"])
async def list_loki_logs_labels(
    grafana_client: Hidden[AsyncGrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m",
) -> ToolResult:
    """List all labels for the Loki logs query. Optionally filter by query.
    
    Examples:
       - list_loki_logs_labels('{app="mysql"}') - get all labels for the mysql app
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    query = _ensure_namespace_in_query(query)
    try:
        labels = await grafana_client.list_loki_labels(from_time, to_time, query=query)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    data = yaml.dump(labels)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics", "logs"])
async def list_loki_label_values(
    grafana_client: Hidden[AsyncGrafanaClient],
    label_name: Annotated[str, "The name of the label to get the values for"],
    query: Annotated[Optional[str], "The query to execute"] = None,
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m",
) -> ToolResult:
    """List all values for a specific label for the Loki logs query.
    
    Examples:
       - list_loki_label_values('app', '{app="mysql"}') - get all values for the app label for the mysql app
    """
    from_time = f"now-{time_window}"
    to_time = "now"

    query = _ensure_namespace_in_query(query)
    try:
        values = await grafana_client.list_loki_label_values(label_name, from_time, to_time, query=query)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    data = yaml.dump(values)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics", "logs"])
async def query_loki_logs(
    grafana_client: Hidden[AsyncGrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m"
) -> ToolResult:
    """Query Loki logs. Remember to use correct namespace (application) and app names (mysql, catalogue, dispatch, mongodb, mysql, payment, shipping, user, web, rabbitmq, ratings, redis).
    Examples:
       - query_loki_logs('{app="mysql"}', time_window="1m") - get all logs for the mysql app
       - query_loki_logs('{app="catalogue"} |~ "(?i)error"', time_window="1m") - get all logs for the catalogue app with error
       - query_loki_logs('{app="dispatch"} |~ "(?i)error" |~ "(?i)timeout"', time_window="1m") - get all logs for the dispatch app with error and timeout
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    try:
        note = await _loki_label_validation_message(grafana_client, query, from_time, to_time)
        logs = await grafana_client.query_loki(query, from_time, to_time)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    result = prase_to_table(logs, exclude_fields=["tsNs", "id"])
    if note:
        result = f"{result}\n\n{note}"
    return ToolResult(result=result, error=None)


@tool(tags=["metrics", "logs"])
async def query_loki_groups(
    grafana_client: Hidden[AsyncGrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get logs from the last X minutes"] = "5m",
    similarity_threshold: Annotated[Optional[float], "The similarity threshold for grouping logs (0-1)"] = 0.5,
) -> ToolResult:
    """Query logs from Loki and group them by similarity. Remember to use correct namespace (application) and app names (mysql, catalogue, dispatch, mongodb, mysql, payment, shipping, user, web, rabbitmq, ratings, redis).
    Returns a list of Loki log groups, each with a representative message and a count of occurrences.
    
    Examples:
       - query_loki_groups('{app="mysql"}', time_window="1m") - get all logs for the mysql app
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    try:
        logs = await grafana_client.query_loki(query, from_time, to_time)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    extracted_logs = extract_loki_results(logs)
    grouped_logs = group_by_similarity(extracted_logs, threshold=similarity_threshold)
    return ToolResult(result=yaml.dump(grouped_logs), error=None)


@tool(tags=["metrics"])
async def query_prometheus_metrics(
    grafana_client: Hidden[AsyncGrafanaClient],
    query: Annotated[str, "The query to execute"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m",
    range_query: Annotated[Optional[bool], "If True, use range query"] = True,
) -> ToolResult:
    """
    Query metrics from Prometheus as a range query. Remember to use correct namespace (application) and app names (mysql, catalogue, dispatch, mongodb, mysql, payment, shipping, user, web, rabbitmq, ratings, redis).
    
    Examples:
       - query_prometheus_metrics('sum(rate(up[5m]))', time_window="1m") - get the request rate for the last 5 minutes
    """
    from_time = f"now-{time_window}"
    to_time = "now"
    try:
        note = await _prometheus_label_validation_message(grafana_client, query, from_time, to_time)
        result = await grafana_client.query_prometheus(query, from_time, to_time, instant=not range_query)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    out = prase_to_table(result)
    if note:
        out = f"{out}\n\n{note}"
    return ToolResult(result=out, error=None)


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
    grafana_client: Hidden[AsyncGrafanaClient],
    metric_name: Annotated[str, "The name of the metric to get the metadata for"],
) -> ToolResult:
    """Get the metadata for a specific metric from the Grafana instance."""
    try:
        metadata = await grafana_client.get_metric_metadata(metric_name)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    if not metadata:
        return ToolResult(result="No metadata found for the metric", error=None)
    data = yaml.dump(metadata)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_prometheus_metric_labels(
    grafana_client: Hidden[AsyncGrafanaClient],
    metric_name: Annotated[str, "The name of the metric to get the labels for"],
) -> ToolResult:
    """Get the labels for a specific metric from the Grafana instance.
    
    Examples:
       - list_prometheus_metric_labels('request_total') - get all labels for the request_total metric
    """
    try:
        labels = await grafana_client.get_label_names(match=metric_name)
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    data = yaml.dump(labels)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_prometheus_metric_label_values(
    grafana_client: Hidden[AsyncGrafanaClient],
    label_name: Annotated[str, "The name of the label to get the values for"],
    metric_name: Annotated[str, "The name of the metric to get the values for"],
    time_window: Annotated[Optional[TimeWindow], "Get metrics from the last X minutes"] = "5m",
) -> ToolResult:
    """Get the values for a specific label from the Grafana instance.
    
    Examples:
       - list_prometheus_metric_label_values('dst_service', 'request_total') - get all values for the dst_service label for the request_total metric
    """
    grafana_client: AsyncGrafanaClient
    from_time = f"now-{time_window}"
    to_time = "now"
    try:
        values = await grafana_client.get_label_values(
            label_name=label_name, match=metric_name, from_time=from_time, to_time=to_time
        )
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)
    data = yaml.dump(values)
    return ToolResult(result=data, error=None)


@tool(tags=["metrics"])
async def list_metrics(
    grafana_client: Hidden[AsyncGrafanaClient],
) -> ToolResult:
    """List all metrics from the Grafana instance."""
    try:
        metrics = await grafana_client.list_metrics()
    except GrafanaBadRequestError as e:
        return _grafana_bad_request_result(e)

    def filter_unwanted_metrics(metrics: list[str]) -> list[str]:
        unwanted_prefixes = ("prometheus", "container_", "go_", "tokio_", "opentelemetry_")
        return [metric for metric in metrics if not any(metric.startswith(prefix) for prefix in unwanted_prefixes)]
    metrics = filter_unwanted_metrics(metrics)
    data = yaml.dump(metrics)
    return ToolResult(result=data, error=None)


MetricsTools = Tools(
    tools=[
        get_app_summary,
        get_edges_summary,
        get_resource_routes,
        query_loki_logs,
        query_loki_groups,
        list_loki_logs_labels,
        list_loki_label_values,
        query_prometheus_metrics,
        get_metric_metadata,
        list_prometheus_metric_label_values,
        list_prometheus_metric_labels,
        list_metrics,
    ]
)

MetricsSummaryTools = Tools(
    tools=[
        get_app_summary,
        get_edges_summary,
        get_resource_routes
    ]
)


if __name__ == "__main__":
    import asyncio
    import os
    GRAFANA_URL = os.environ.get("GRAFANA_URL")
    GRAFANA_API_KEY = os.environ.get("GRAFANA_API_KEY")

    async def main():
        grafana_client = AsyncGrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY)

        result = await get_app_summary(grafana_client=grafana_client)
        if result.error:
            print(result.error, flush=True)
        print(result.result or "", flush=True)
        exit()
        #result = await query_loki_logs(grafana_client=grafana_client, query='{app="shipping",bleh="bleh"}', time_window="1m")
        #print(result.result)
        #exit()

        print("Testing list_metric_labels...")
        result = await list_prometheus_metric_labels(grafana_client=grafana_client, metric_name="request_total")
        print(result.result)

        print("Testing list_metric_label_values...")
        result = await list_prometheus_metric_label_values(grafana_client=grafana_client, label_name="dst_service", metric_name="request_total")
        print(result.result)

        # print("Testing list_metric_label_values...")
        # result = await list_metric_label_values(grafana_client=grafana_client, label_name="dst_service", metric_name="request_total")
        # print(result.result)

        exit()

        print("Testing get_app_summary...")
        result = await get_app_summary(grafana_client=grafana_client)
        print(result.result)

        print("Testing query_loki_groups...")
        result = await query_loki_groups(grafana_client=grafana_client, query='{app="shipping"}', time_window="1m", similarity_threshold=0.5)
        print(result.result)

        print("Testing get_resource_routes...")
        result = await get_resource_routes(resource_type="deployment", resource_id="cart")
        print(result.result)

        print("Testing query_loki...")
        # For demo purposes - parameters may need to be replaced with real ones that make sense for your environment.
        result = await query_loki_logs(grafana_client=grafana_client, query='{app="shipping"}', time_window="1m")
        print(result.result)

        print("Testing get_edges_summary...")
        result = await get_edges_summary(resource="deployments")
        print(result.result)

        print("Testing range_query_prometheus...")
        result = await query_prometheus_metrics(grafana_client=grafana_client, query='sum(rate(up[5m]))', time_window="60m")
        print(result.result)

        # Test all metric tooling functions
        print("Testing get_metric_metadata...")
        result = await get_metric_metadata(grafana_client=grafana_client, metric_name="request_total")
        print(result.result)

        print("Testing list_metric_label_values...")
        result = await list_prometheus_metric_label_values(grafana_client=grafana_client, label_name="instance", metric_name="up")
        print(result.result)

        print("Testing list_metric_labels...")
        result = await list_prometheus_metric_labels(grafana_client=grafana_client, metric_name="up")
        print(result.result)

        print("Testing list_metrics...")
        result = await list_metrics(grafana_client=grafana_client)
        print(result.result)

    asyncio.run(main())
