from typing import Any, Optional

import yaml

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.kubectl import get_pod_resource_limits
from agent.grafana_client.logs import (get_error_counts_by_app,
                                       get_grouped_errors_by_app)
from agent.grafana_client.metrics import (WINDOWS, get_cpu_usage,
                                          get_http_error_counts,
                                          get_latency_percentiles,
                                          get_memory_usage, get_request_rate,
                                          get_success_rate)


def format_status_report(
    namespace: str,
    apps: list[str],
    window: str,
    latency: dict[str, dict[str, float]],
    http_errors: dict[str, dict[str, float]],
    request_rate: dict[str, float],
    success_rate: dict[str, float],
    cpu_usage: dict[str, float],
    memory_usage: dict[str, float],
    error_counts: dict[str, int],
    grouped_errors: dict[str, list[dict[str, Any]]],
    cpu_limits: Optional[dict[str, float]] = None,
    memory_limits: Optional[dict[str, float]] = None,
) -> str:
    """
    Format a concise MD report of app status for LLM context when an alert fires.

    Args:
        namespace: K8s namespace
        apps: List of app names
        window: Time window (e.g. 5m, 1h)
        latency: {app: {p50, p95, p99}} in ms
        http_errors: {app: {4xx, 5xx}}
        request_rate: {app: req/s}
        success_rate: {app: 0-1}
        cpu_usage: {app: cores}
        memory_usage: {app: bytes}
        error_counts: {app: count}
        grouped_errors: {app: [{message, count}, ...]}

    Returns:
        Markdown string
    """
    lines = [
        "# App Status Report",
        f"**Namespace:** `{namespace}` | **Window:** {window}",
        "",
    ]

    for app in apps:
        lines.append(f"## {app}")
        lines.append("")

        # Metrics
        lat = latency.get(app, {})
        err = http_errors.get(app, {})
        rate = request_rate.get(app, 0)
        succ = success_rate.get(app, 0)
        cpu = cpu_usage.get(app, 0)
        mem_mb = memory_usage.get(app, 0) / (1024 * 1024)

        # Use limits from cluster (kubectl) when provided, else fallback defaults
        cpu_limit_cores = cpu_limits[app]
        mem_limit_bytes = memory_limits[app]
        mem_limit_mb = mem_limit_bytes / (1024 * 1024)
        cpu_pct = (cpu / cpu_limit_cores * 100) if cpu_limit_cores > 0 else 0.0
        mem_pct = (mem_mb / mem_limit_mb * 100) if mem_limit_mb > 0 else 0.0

        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| CPU (cores, % of limit) | {cpu:.3f} ({cpu_pct:.1f}%) |")
        lines.append(f"| Memory (MB, % of limit) | {mem_mb:.1f} ({mem_pct:.1f}%) |")
        lines.append(f"| Latency p50 (ms) | {lat.get('p50', 0):.1f} |")
        lines.append(f"| Latency p95 (ms) | {lat.get('p95', 0):.1f} |")
        lines.append(f"| Latency p99 (ms) | {lat.get('p99', 0):.1f} |")
        lines.append(f"| Request rate (req/s) | {rate:.2f} |")
        lines.append(f"| Success rate | {succ:.2%} |")
        lines.append(f"| 4XX count | {err.get('4xx', 0):.0f} |")
        lines.append(f"| 5XX count | {err.get('5xx', 0):.0f} |")
        lines.append(f"| Error log count | {error_counts.get(app, 0)} |")
        lines.append("")

        # Grouped error samples
        groups = grouped_errors.get(app, [])
        if groups:
            lines.append("**Error log samples (grouped by similarity):**")
            lines.append("")
            for i, g in enumerate(groups[:10], 1):  # max 10 groups
                lines.append(f"- [{g.get('count', 1)}x] `{_truncate(g.get('message', ''), 120)}`")
            lines.append("")
        else:
            lines.append("**Error logs:** none")
            lines.append("")

    return "\n".join(lines)


def format_status_report_yaml(
    namespace: str,
    apps: list[str],
    window: str,
    latency: dict[str, dict[str, float]],
    http_errors: dict[str, dict[str, float]],
    request_rate: dict[str, float],
    success_rate: dict[str, float],
) -> str:
    """
    Format a YAML report of app status for LLM context when an alert fires.
    """
    report = {
        "namespace": namespace,
        "apps": apps,
        "window": window,
        "latency": latency,
        "http_errors": http_errors,
        "request_rate": request_rate,
        "success_rate": success_rate,
    }
    return yaml.dump(report)


def _truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


async def build_status_report(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    window: str = "5m",
    similarity_threshold: float = 0.5,
    pod_selector: str | None = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> str:
    """
    Build a concise MD status report for LLM consumption.

    Fetches Linkerd metrics (latency, 4XX/5XX, request rate, success rate),
    CPU/memory usage, error log counts, and grouped error samples per app.

    Args:
        client: GrafanaClient with url + api_key
        namespace: K8s namespace (e.g. "application")
        apps: List of microservice names (deployment/app labels)
        window: Time window - "5m", "15m", or "1h"
        similarity_threshold: Threshold for grouping similar errors (0-1)
        pod_selector: PromQL pod filter, e.g. ~"sample-app.*" for CPU/memory and logs

    Returns:
        Markdown string
    """
    cpu_limits, memory_limits = get_pod_resource_limits(namespace=namespace, apps=apps, env=env, cwd=cwd)
    if window not in WINDOWS:
        window = "5m"

    from_time = f"now-{window}"
    to_time = "now"

    latency = await get_latency_percentiles(client, namespace, apps, window)
    http_errors = await get_http_error_counts(client, namespace, apps, window)
    request_rate = await get_request_rate(client, namespace, apps, window)
    success_rate = await get_success_rate(client, namespace, apps, window)
    cpu_usage = await get_cpu_usage(client, namespace, apps, window, pod_selector)
    memory_usage = await get_memory_usage(client, namespace, apps, pod_selector)
    error_counts = await get_error_counts_by_app(
        client, namespace, apps, from_time, to_time, pod_selector=pod_selector
    )
    grouped_errors = await get_grouped_errors_by_app(
        client, namespace, apps, from_time, to_time,
        similarity_threshold=similarity_threshold,
        pod_selector=pod_selector,
    )
    return format_status_report(
        namespace=namespace,
        apps=apps,
        window=window,
        latency=latency,
        http_errors=http_errors,
        request_rate=request_rate,
        success_rate=success_rate,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        error_counts=error_counts,
        grouped_errors=grouped_errors,
        cpu_limits=cpu_limits,
        memory_limits=memory_limits,
    )


async def build_status_report_dict(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    window: str = "5m",
    pod_selector: str | None = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> dict:
    """
    Build a dictionary status report for LLM consumption.
    """
    cpu_limits, memory_limits = get_pod_resource_limits(namespace=namespace, apps=apps, env=env, cwd=cwd)
    if window not in WINDOWS:
        window = "5m"

    from_time = f"now-{window}"
    to_time = "now"
    latency = await get_latency_percentiles(client, namespace, apps, window)
    http_errors = await get_http_error_counts(client, namespace, apps, window)
    request_rate = await get_request_rate(client, namespace, apps, window)
    success_rate = await get_success_rate(client, namespace, apps, window)
    cpu_usage = await get_cpu_usage(client, namespace, apps, window, pod_selector)
    memory_usage = await get_memory_usage(client, namespace, apps, pod_selector)
    error_counts = await get_error_counts_by_app(
        client, namespace, apps, from_time, to_time, pod_selector=pod_selector
    )
    grouped_errors = await get_grouped_errors_by_app(
        client, namespace, apps, from_time, to_time,
        similarity_threshold=0.5,
        pod_selector=pod_selector,
    )

    services: dict[str, dict[str, Any]] = {}
    for app in apps:
        lat = latency.get(app, {})
        err = http_errors.get(app, {})
        rate = request_rate.get(app, 0.0)
        succ = success_rate.get(app, 0.0)
        cpu = cpu_usage.get(app, 0.0)
        mem_bytes = memory_usage.get(app, 0.0)
        mem_mb = mem_bytes / (1024 * 1024) if mem_bytes else 0.0

        cpu_limit_cores = cpu_limits.get(app, 0.0) if cpu_limits else 0.0
        mem_limit_bytes = memory_limits.get(app, 0.0) if memory_limits else 0.0
        mem_limit_mb = mem_limit_bytes / (1024 * 1024) if mem_limit_bytes else 0.0

        cpu_pct = (cpu / cpu_limit_cores * 100.0) if cpu_limit_cores > 0 else 0.0
        mem_pct = (mem_mb / mem_limit_mb * 100.0) if mem_limit_mb > 0 else 0.0

        groups = grouped_errors.get(app, []) or []
        error_samples = [
            {
                "count": int(g.get("count", 1)),
                "truncated_message": _truncate(str(g.get("message", "")), 120),
            }
            for g in groups[:10]
        ]

        services[app] = {
            "latency_p50_ms": int(lat.get("p50", 0.0)),
            "latency_p95_ms": int(lat.get("p95", 0.0)),
            "latency_p99_ms": int(lat.get("p99", 0.0)),
            "cpu_cores": float("{:.3f}".format(cpu)),
            "cpu_cores_percent_of_limit": int(cpu_pct),
            "memory_mb": int(mem_mb),
            "memory_percent_of_limit": int(mem_pct),
            "request_rate_rps": int(rate),
            "success_rate": succ,
            "http_4xx": int(err.get("4xx", 0)),
            "http_5xx": int(err.get("5xx", 0)),
            "error_log_count": int(error_counts.get(app, 0)),
            "error_logs_samples": error_samples,
        }

    report = {
        "namespace": namespace,
        "window": window,
        "services": services,
    }

    return report


async def build_status_report_yaml(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    window: str = "5m",
    pod_selector: str | None = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> str:
    """
    Build a YAML status report for LLM consumption.

    The structure is:

    ```yaml
    namespace: <namespace>
    window: <window>
    services:
      <service-name>:
        latency_p50_ms: <float>
        latency_p95_ms: <float>
        latency_p99_ms: <float>
        cpu_cores: <float>
        cpu_cores_percent_of_limit: <float>
        memory_mb: <float>
        memory_percent_of_limit: <float>
        request_rate_rps: <float>
        success_rate: <float>  # 0-1
        http_4xx: <float>
        http_5xx: <float>
        error_log_count: <int>
    ```
    """
    data = await build_status_report_dict(client, namespace, apps, window, pod_selector, env, cwd)
    return yaml.dump(data, sort_keys=False)
