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

    metric_rows: list[tuple[str, list[str]]] = [
        ("CPU (cores, % of limit)", []),
        ("Memory (MB, % of limit)", []),
        ("Latency p50 (ms)", []),
        ("Latency p95 (ms)", []),
        ("Latency p99 (ms)", []),
        ("Request rate (req/s)", []),
        ("Success rate", []),
        ("4XX count", []),
        ("5XX count", []),
        ("Error log count", []),
    ]

    for app in apps:
        lat = latency.get(app, {})
        err = http_errors.get(app, {})
        rate = request_rate.get(app, 0)
        succ = success_rate.get(app, 0)
        cpu = cpu_usage.get(app, 0)
        mem_mb = memory_usage.get(app, 0) / (1024 * 1024)

        cpu_limit_cores = cpu_limits.get(app, 0.0) if cpu_limits else 0.0
        mem_limit_bytes = memory_limits.get(app, 0.0) if memory_limits else 0.0
        mem_limit_mb = mem_limit_bytes / (1024 * 1024) if mem_limit_bytes else 0.0
        cpu_pct = (cpu / cpu_limit_cores * 100) if cpu_limit_cores > 0 else 0.0
        mem_pct = (mem_mb / mem_limit_mb * 100) if mem_limit_mb > 0 else 0.0

        metric_rows[0][1].append(f"{cpu:.3f} ({cpu_pct:.1f}%)")
        metric_rows[1][1].append(f"{mem_mb:.1f} ({mem_pct:.1f}%)")
        metric_rows[2][1].append(f"{lat.get('p50', 0):.1f}")
        metric_rows[3][1].append(f"{lat.get('p95', 0):.1f}")
        metric_rows[4][1].append(f"{lat.get('p99', 0):.1f}")
        metric_rows[5][1].append(f"{rate:.2f}")
        metric_rows[6][1].append(f"{succ:.2%}")
        metric_rows[7][1].append(f"{err.get('4xx', 0):.0f}")
        metric_rows[8][1].append(f"{err.get('5xx', 0):.0f}")
        metric_rows[9][1].append(f"{error_counts.get(app, 0)}")

    lines.extend(_build_fixed_width_table(apps, metric_rows))

    lines.append("")

    # Keep grouped errors split by app for readability.
    for app in apps:
        groups = grouped_errors.get(app, [])
        lines.append(f"## {app} Error Samples")
        lines.append("")
        if groups:
            for g in groups[:10]:  # max 10 groups
                lines.append(f"- [{g.get('count', 1)}x] `{_truncate(g.get('message', ''), 120)}`")
        else:
            lines.append("- none")
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


def format_status_report_from_dict(
    metrics: dict[str, Any],
    title: str = "# App Status Report",
    report_scope: Optional[str] = None,
) -> str:
    """
    Format markdown report from build_status_report_dict-like payload.
    """
    namespace = str(metrics.get("namespace", "unknown"))
    window = str(metrics.get("window", "5m"))
    services = metrics.get("services", {}) or {}
    apps = list(services.keys())

    lines = [title, f"**Namespace:** `{namespace}` | **Window:** {window}"]
    if report_scope:
        lines.append(f"**Scope:** {report_scope}")
    lines.append("")

    metric_rows: list[tuple[str, list[str]]] = [
        ("CPU (cores, % of limit)", []),
        ("Memory (MB, % of limit)", []),
        ("Latency p50 (ms)", []),
        ("Latency p95 (ms)", []),
        ("Latency p99 (ms)", []),
        ("Request rate (req/s)", []),
        ("Success rate", []),
        ("4XX count", []),
        ("5XX count", []),
        ("Error log count", []),
    ]

    for app in apps:
        m = services.get(app, {}) or {}
        metric_rows[0][1].append(
            f"{float(m.get('cpu_cores', 0.0)):.3f} ({float(m.get('cpu_cores_percent_of_limit', 0.0)):.1f}%)"
        )
        metric_rows[1][1].append(
            f"{float(m.get('memory_mb', 0.0)):.1f} ({float(m.get('memory_percent_of_limit', 0.0)):.1f}%)"
        )
        metric_rows[2][1].append(f"{float(m.get('latency_p50_ms', 0.0)):.1f}")
        metric_rows[3][1].append(f"{float(m.get('latency_p95_ms', 0.0)):.1f}")
        metric_rows[4][1].append(f"{float(m.get('latency_p99_ms', 0.0)):.1f}")
        metric_rows[5][1].append(f"{float(m.get('request_rate_rps', 0.0)):.2f}")
        metric_rows[6][1].append(f"{float(m.get('success_rate', 0.0)):.2%}")
        metric_rows[7][1].append(f"{float(m.get('http_4xx', 0.0)):.0f}")
        metric_rows[8][1].append(f"{float(m.get('http_5xx', 0.0)):.0f}")
        metric_rows[9][1].append(f"{int(m.get('error_log_count', 0))}")

    lines.extend(_build_fixed_width_table(apps, metric_rows))
    lines.append("")

    for app in apps:
        groups = (services.get(app, {}) or {}).get("error_logs_samples", []) or []
        lines.append(f"## {app} Error Samples")
        lines.append("")
        if groups:
            for g in groups[:10]:
                lines.append(f"- [{g.get('count', 1)}x] `{_truncate(str(g.get('truncated_message', '')), 120)}`")
        else:
            lines.append("- none")
        lines.append("")

    return "\n".join(lines)


def format_diff_status_report(diff_payload: dict[str, Any], cause_of_incident: str) -> str:
    """
    Build a focused report for services whose before/after metrics differ enough
    to count as significant (same rules and default threshold as detect_differences).

    This keeps the same style as format_status_report but limits output size and
    puts healthy (before) and unhealthy (after) views side by side as two tables.
    """
    changed_services = list((diff_payload or {}).get("changed_services", []) or [])
    metrics_before = {
        "namespace": diff_payload.get("namespace", "unknown"),
        "window": diff_payload.get("window", "5m"),
        "services": (diff_payload.get("services_before", {}) or {}),
    }
    metrics_after = {
        "namespace": diff_payload.get("namespace", "unknown"),
        "window": diff_payload.get("window", "5m"),
        "services": (diff_payload.get("services_after", {}) or {}),
    }

    # Backward compatibility with older diff shape:
    # {"service-a": {...after metrics...}, "service-b": {...}}
    if not changed_services and "services_after" not in (diff_payload or {}):
        changed_services = list((diff_payload or {}).keys())
        metrics_after["services"] = diff_payload or {}

    if not changed_services:
        namespace = str(metrics_after.get("namespace") or metrics_before.get("namespace") or "unknown")
        window = str(metrics_after.get("window") or metrics_before.get("window") or "5m")
        return "\n".join(
            [
                "# Focused App Status Report",
                f"**Namespace:** `{namespace}` | **Window:** {window}",
                "**Scope:** changed services only",
                "",
                "No significant service-level differences detected.",
            ]
        )

    before_services = metrics_before.get("services", {}) or {}
    after_services = metrics_after.get("services", {}) or {}

    focused_before = {
        "namespace": metrics_before.get("namespace", metrics_after.get("namespace", "unknown")),
        "window": metrics_before.get("window", metrics_after.get("window", "5m")),
        "services": {s: before_services.get(s, {}) for s in changed_services},
    }
    focused_after = {
        "namespace": metrics_after.get("namespace", metrics_before.get("namespace", "unknown")),
        "window": metrics_after.get("window", metrics_before.get("window", "5m")),
        "services": {s: after_services.get(s, {}) for s in changed_services},
    }

    before_report = format_status_report_from_dict(
        focused_before,
        title=f"# Metrics Before - {cause_of_incident}",
        report_scope="changed services only",
    )
    after_report = format_status_report_from_dict(
        focused_after,
        title=f"# Metrics After - {cause_of_incident}",
        report_scope="changed services only",
    )
    return f"{before_report}\n\n---\n\n{after_report}"


def _truncate(s: str, max_len: int) -> str:
    s = s.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _build_fixed_width_table(
    apps: list[str],
    metric_rows: list[tuple[str, list[str]]],
) -> list[str]:
    """
    Build an ASCII table with fixed column widths for terminal readability.
    """
    if not apps:
        return ["(no apps)"]

    metric_col_width = max(
        len("Metric"),
        *(len(metric_name) for metric_name, _ in metric_rows),
    )
    service_col_width = len("Service")
    for app in apps:
        service_col_width = max(service_col_width, len(app))
    for _, values in metric_rows:
        for value in values:
            service_col_width = max(service_col_width, len(value))

    # Keep table reasonably compact in terminals while preserving alignment.
    service_col_width = min(service_col_width, 36)

    def fmt_cell(value: str, width: int) -> str:
        return f" {_truncate(value, width):<{width}} "

    sep = "+" + "-" * (metric_col_width + 2)
    for _ in apps:
        sep += "+" + "-" * (service_col_width + 2)
    sep += "+"

    lines = [sep]
    header = "|" + fmt_cell("Metric", metric_col_width)
    for app in apps:
        header += "|" + fmt_cell(app, service_col_width)
    header += "|"
    lines.append(header)
    lines.append(sep)

    for metric_name, values in metric_rows:
        row = "|" + fmt_cell(metric_name, metric_col_width)
        for value in values:
            row += "|" + fmt_cell(value, service_col_width)
        row += "|"
        lines.append(row)
    lines.append(sep)
    return lines


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


def detect_differences(metrics_before: dict, metrics_after: dict, threshold: float = 5.0) -> dict:
    """
    Compare before/after service metrics and return a focused diff payload.

    Returned shape:
    {
      "namespace": str,
      "window": str,
      "threshold": float,
      "changed_services": [service...],
      "services_before": {service: metrics...},
      "services_after": {service: metrics...}
    }
    """
    services_before_diff: dict[str, Any] = {}
    services_after_diff: dict[str, Any] = {}

    services_before = metrics_before.get("services", {})
    services_after = metrics_after.get("services", {})

    for service_name, after_metrics in services_after.items():
        before_metrics = services_before.get(service_name)

        if not before_metrics:
            # If the service wasn't present before, it's considered a difference
            services_before_diff[service_name] = {}
            services_after_diff[service_name] = after_metrics
            continue

        has_significant_change = False
        for key, after_val in after_metrics.items():
            if key == "error_logs_samples":
                continue

            before_val = before_metrics.get(key, 0.0)

            # Some metrics need scaling or special handling
            if key == "success_rate":
                # success_rate is 0-1, convert to 0-100 for threshold comparison
                current_diff = abs(after_val - before_val) * 100.0
            else:
                # Most other metrics are already in reasonable units (ms, cores%, MB, counts)
                current_diff = abs(after_val - before_val)

            if current_diff >= threshold:
                has_significant_change = True
                break

        if has_significant_change:
            services_before_diff[service_name] = before_metrics
            services_after_diff[service_name] = after_metrics

    changed_services = list(services_after_diff.keys())
    return {
        "namespace": metrics_after.get("namespace", metrics_before.get("namespace", "unknown")),
        "window": metrics_after.get("window", metrics_before.get("window", "5m")),
        "threshold": threshold,
        "changed_services": changed_services,
        "services_before": services_before_diff,
        "services_after": services_after_diff,
    }


if __name__ == "__main__":
    # Quick local smoke tests with mock data:
    #   python -m agent.grafana_client.report
    #
    # `shipping` has only tiny before/after deltas (all < default threshold), so it must
    # not appear in focused diff output — only services with visible metric changes show.
    mock_metrics_before = {
        "namespace": "robot-shop",
        "window": "5m",
        "services": {
            "cart": {
                "latency_p50_ms": 20,
                "latency_p95_ms": 80,
                "latency_p99_ms": 120,
                "cpu_cores": 0.120,
                "cpu_cores_percent_of_limit": 24,
                "memory_mb": 180,
                "memory_percent_of_limit": 36,
                "request_rate_rps": 52,
                "success_rate": 0.998,
                "http_4xx": 2,
                "http_5xx": 0,
                "error_log_count": 1,
                "error_logs_samples": [
                    {"count": 1, "truncated_message": "timeout while reading cache"}
                ],
            },
            "user": {
                "latency_p50_ms": 35,
                "latency_p95_ms": 110,
                "latency_p99_ms": 180,
                "cpu_cores": 0.180,
                "cpu_cores_percent_of_limit": 36,
                "memory_mb": 240,
                "memory_percent_of_limit": 48,
                "request_rate_rps": 31,
                "success_rate": 0.996,
                "http_4xx": 5,
                "http_5xx": 1,
                "error_log_count": 2,
                "error_logs_samples": [],
            },
            "shipping": {
                "latency_p50_ms": 12,
                "latency_p95_ms": 45,
                "latency_p99_ms": 78,
                "cpu_cores": 0.080,
                "cpu_cores_percent_of_limit": 16,
                "memory_mb": 140,
                "memory_percent_of_limit": 28,
                "request_rate_rps": 22,
                "success_rate": 0.999,
                "http_4xx": 0,
                "http_5xx": 0,
                "error_log_count": 0,
                "error_logs_samples": [],
            },
        },
    }

    mock_metrics_after = {
        "namespace": "robot-shop",
        "window": "5m",
        "services": {
            "cart": {
                "latency_p50_ms": 28,
                "latency_p95_ms": 92,
                "latency_p99_ms": 130,
                "cpu_cores": 0.140,
                "cpu_cores_percent_of_limit": 28,
                "memory_mb": 190,
                "memory_percent_of_limit": 38,
                "request_rate_rps": 50,
                "success_rate": 0.992,
                "http_4xx": 3,
                "http_5xx": 1,
                "error_log_count": 4,
                "error_logs_samples": [
                    {"count": 2, "truncated_message": "db retry exhausted for cart lookup"}
                ],
            },
            "user": {
                "latency_p50_ms": 95,
                "latency_p95_ms": 360,
                "latency_p99_ms": 700,
                "cpu_cores": 0.650,
                "cpu_cores_percent_of_limit": 130,
                "memory_mb": 510,
                "memory_percent_of_limit": 102,
                "request_rate_rps": 18,
                "success_rate": 0.82,
                "http_4xx": 9,
                "http_5xx": 42,
                "error_log_count": 37,
                "error_logs_samples": [
                    {"count": 20, "truncated_message": "sql timeout talking to userdb"},
                    {"count": 8, "truncated_message": "circuit breaker open for user profile calls"},
                ],
            },
            "shipping": {
                "latency_p50_ms": 13,
                "latency_p95_ms": 46,
                "latency_p99_ms": 79,
                "cpu_cores": 0.082,
                "cpu_cores_percent_of_limit": 16,
                "memory_mb": 141,
                "memory_percent_of_limit": 29,
                "request_rate_rps": 21,
                "success_rate": 0.998,
                "http_4xx": 0,
                "http_5xx": 0,
                "error_log_count": 1,
                "error_logs_samples": [],
            },
        },
    }

    mock_diff = detect_differences(mock_metrics_before, mock_metrics_after, threshold=10.0)

    print("\n=== FULL REPORT (MOCK AFTER) ===\n")
    print(format_status_report_from_dict(mock_metrics_after))

    print("\n=== FOCUSED DIFF REPORT (detect_differences — no sub-threshold services) ===\n")
    print(format_diff_status_report(mock_diff, "incident"))