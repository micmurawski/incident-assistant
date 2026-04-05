from typing import Any

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.parsers import (extract_loki_results,
                                          group_by_similarity)


async def count_error_logs(
    client: GrafanaClient,
    namespace: str,
    app: str,
    from_time: str = "now-1h",
    to_time: str = "now",
    pod_selector: str | None = None,
) -> int:
    """
    Count error logs for an app: |= "ERROR" or |= "error".

    Args:
        client: GrafanaClient instance
        namespace: K8s namespace
        app: App label (microservice name)
        from_time, to_time: Time window
        pod_selector: Optional LogQL pod filter, e.g. ~"sample-app.*"

    Returns:
        Number of matching log lines
    """
    labels = f'namespace="{namespace}", app="{app}"'
    if pod_selector:
        labels += f", pod={pod_selector}"
    expr = f'{{{labels}}} |~ "(?i)error"'
    logs = extract_loki_results(await client.query_loki(expr, from_time=from_time, to_time=to_time))
    return len(logs)


async def fetch_error_logs(
    client: GrafanaClient,
    namespace: str,
    app: str,
    from_time: str = "now-1h",
    to_time: str = "now",
    limit: int = 5000,
    pod_selector: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch error logs for an app.

    Returns:
        [{"timestamp": float, "message": str, "labels": dict}, ...]
    """
    labels = f'namespace="{namespace}", app="{app}"'
    if pod_selector:
        labels += f", pod={pod_selector}"
    expr = f'{{{labels}}} |~ "(?i)error"'
    return extract_loki_results(await client.query_loki(expr, from_time=from_time, to_time=to_time, limit=limit))


async def get_error_counts_by_app(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    from_time: str = "now-1h",
    to_time: str = "now",
    pod_selector: str | None = None,
) -> dict[str, int]:
    """Count error logs per app in namespace."""
    counts: dict[str, int] = {}
    for app in apps:
        counts[app] = await count_error_logs(
            client, namespace, app, from_time, to_time, pod_selector
        )
    return counts


async def get_grouped_errors_by_app(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    from_time: str = "now-1h",
    to_time: str = "now",
    similarity_threshold: float = 0.5,
    pod_selector: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Fetch error logs per app, group by similarity, return one representative per group.

    Returns:
        { "app_name": [{"message": str, "count": int, "labels": dict}, ...], ... }
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for app in apps:
        logs = await fetch_error_logs(
            client, namespace, app, from_time, to_time, 5000, pod_selector
        )
        result[app] = group_by_similarity(logs, threshold=similarity_threshold)
    return result
