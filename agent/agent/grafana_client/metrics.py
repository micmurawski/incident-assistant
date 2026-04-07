from typing import Any

from agent.grafana_client.client import AsyncGrafanaClient as GrafanaClient
from agent.grafana_client.parsers import extract_prometheus_results

# Linkerd proxy metrics job name
LINKERD_JOB = "linkerd-proxy"

# Valid time windows
WINDOWS = ("5m", "15m", "1h")


def _get_rate_selector(namespace: str, apps: list[str] | None, direction: str = "inbound") -> str:
    """Build label selector for linkerd metrics in a namespace."""
    sel = f'job="{LINKERD_JOB}", namespace="{namespace}", direction="{direction}"'
    if apps:
        # Match deployment or app label
        app_re = "|".join([f'{app}.*' for app in apps])
        sel += f', pod=~"{app_re}"'
    return sel


async def get_latency_percentiles(
    client: GrafanaClient,
    namespace: str,
    apps: list[str] | None = None,
    window: str = "5m",
) -> dict[str, dict[str, float]]:
    """
    Get p50, p95, p99 latency (ms) per app (by pod, then aggregated by app).

    Returns:
        { "app_name": {"p50": 10.5, "p95": 50.2, "p99": 120.0}, ... }
    """
    sel = _get_rate_selector(namespace, apps)
    # Use pod so StatefulSets (e.g. redis) are included; Deployments have pod too
    base = f'sum(rate(response_latency_ms_bucket{{{sel}}}[{window}])) by (le, pod)'

    # Collect (app, percentile) -> list of values for averaging across pods
    app_percentile_values: dict[str, dict[str, list[float]]] = {}
    app_list = apps or []

    for q, p in [("0.50", "p50"), ("0.95", "p95"), ("0.99", "p99")]:
        expr = f"histogram_quantile({q}, {base})"
        results = await client.query_prometheus(expr, from_time=f"now-{window}", to_time="now")
        for frame in extract_prometheus_results(results):
            for pod_name, val in _extract_series_by_pod(frame):
                if val is None:
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                for app in app_list:
                    if pod_name == app or pod_name.startswith(app + "-"):
                        if app not in app_percentile_values:
                            app_percentile_values[app] = {}
                        app_percentile_values[app].setdefault(p, []).append(num)
                        break

    # Average per app per percentile (so one value per app)
    result: dict[str, dict[str, float]] = {}
    for app in app_list:
        result[app] = {}
        for p in ("p50", "p95", "p99"):
            vals = (app_percentile_values.get(app) or {}).get(p, [])
            result[app][p] = sum(vals) / len(vals) if vals else 0.0
    return result


async def get_http_error_counts(
    client: GrafanaClient,
    namespace: str,
    apps: list[str] | None = None,
    window: str = "5m",
) -> dict[str, dict[str, float]]:
    """
    Get 4XX and 5XX response counts per app (by pod, then aggregated by app).

    Returns:
        { "app_name": {"4xx": 10, "5xx": 2}, ... }
    """
    sel = _get_rate_selector(namespace, apps)
    result: dict[str, dict[str, float]] = {}
    app_list = apps or []

    for status_pattern, key in [("4..", "4xx"), ("5..", "5xx")]:
        expr = f'sum(increase(response_total{{{sel}, status_code=~"{status_pattern}"}}[{window}])) by (pod)'
        results = await client.query_prometheus(expr, from_time=f"now-{window}", to_time="now")
        for frame in extract_prometheus_results(results):
            for pod_name, val in _extract_series_by_pod(frame):
                if val is None:
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                for app in app_list:
                    if pod_name == app or pod_name.startswith(app + "-"):
                        if app not in result:
                            result[app] = {"4xx": 0.0, "5xx": 0.0}
                        result[app][key] = result[app].get(key, 0.0) + num
                        break

    for app in app_list:
        result.setdefault(app, {"4xx": 0.0, "5xx": 0.0})
        result[app].setdefault("4xx", 0.0)
        result[app].setdefault("5xx", 0.0)
    return result


async def get_request_rate(
    client: GrafanaClient,
    namespace: str,
    apps: list[str] | None = None,
    window: str = "5m",
) -> dict[str, float]:
    """
    Get request rate (req/s) per app (summed over all pods for each app).

    Returns:
        { "app_name": 12.5, ... }
    """
    sel = _get_rate_selector(namespace, apps)
    expr = f'sum(rate(response_total{{{sel}}}[{window}])) by (pod)'
    results = await client.query_prometheus(expr, from_time=f"now-{window}", to_time="now")
    pod_rates: dict[str, float] = {}
    for frame in extract_prometheus_results(results):
        for pod_name, val in _extract_series_by_pod(frame):
            pod_rates[pod_name] = float(val) if val is not None else 0.0

    # Aggregate by app: pod "redis-0" -> app "redis", "cart-7b8f9c-xyz" -> "cart"
    result: dict[str, float] = {}
    app_list = apps or []
    for pod_name, rate in pod_rates.items():
        for app in app_list:
            if pod_name == app or pod_name.startswith(app + "-"):
                result[app] = result.get(app, 0.0) + rate
                break
    return result


async def get_cpu_usage(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    window: str = "5m",
    pod_selector: str | None = None,
) -> dict[str, float]:
    """
    Get CPU usage (cores) per app from container metrics.

    Returns:
        { "app_name": 0.15, ... }  # cores
    """
    result: dict[str, float] = {}
    for app in apps:
        pod_filter = pod_selector if pod_selector else f'~"{app}.*"'
        expr = (
            f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}", '
            f'container!="", container!="POD", pod={pod_filter}}}[{window}]))'
        )
        results = await client.query_prometheus(expr, from_time=f"now-{window}", to_time="now")
        val = _extract_single_value(extract_prometheus_results(results))
        result[app] = float(val) if val is not None else 0.0
    return result


async def get_memory_usage(
    client: GrafanaClient,
    namespace: str,
    apps: list[str],
    pod_selector: str | None = None,
) -> dict[str, float]:
    """
    Get memory usage (bytes) per app from container metrics.

    Returns:
        { "app_name": 52428800, ... }  # bytes
    """
    result: dict[str, float] = {}
    for app in apps:
        pod_filter = pod_selector if pod_selector else f'~"{app}.*"'
        # container_memory_working_set_bytes is what k8s uses for eviction
        expr = (
            f'sum(container_memory_working_set_bytes{{namespace="{namespace}", '
            f'container!="", container!="POD", pod={pod_filter}}})'
        )
        results = await client.query_prometheus(expr, from_time="now-5m", to_time="now")
        val = _extract_single_value(extract_prometheus_results(results))
        if val is None:
            # Fallback to container_memory_usage_bytes if working_set not available
            expr = (
                f'sum(container_memory_usage_bytes{{namespace="{namespace}", '
                f'container!="", container!="POD", pod={pod_filter}}})'
            )
            results = await client.query_prometheus(expr, from_time="now-5m", to_time="now")
            val = _extract_single_value(extract_prometheus_results(results))
        result[app] = float(val) if val is not None else 0.0
    return result


async def get_success_rate(
    client: GrafanaClient,
    namespace: str,
    apps: list[str] | None = None,
    window: str = "5m",
) -> dict[str, float]:
    """
    Get success rate (0-1) per app (by pod, then aggregated by app).

    Returns:
        { "app_name": 0.98, ... }
    """
    sel = _get_rate_selector(namespace, apps)
    total = f'sum(rate(response_total{{{sel}}}[{window}])) by (pod)'
    success = f'sum(rate(response_total{{{sel}, classification="success"}}[{window}])) by (pod)'
    expr = f"({success}) / ({total})"
    results = await client.query_prometheus(expr, from_time=f"now-{window}", to_time="now")
    pod_rates: dict[str, float] = {}
    for frame in extract_prometheus_results(results):
        for pod_name, val in _extract_series_by_pod(frame):
            if val is not None and val == val:  # skip NaN
                pod_rates[pod_name] = float(val)

    # Aggregate by app: average success rate across pods
    app_rates: dict[str, list[float]] = {}
    app_list = apps or []
    for pod_name, rate in pod_rates.items():
        for app in app_list:
            if pod_name == app or pod_name.startswith(app + "-"):
                app_rates.setdefault(app, []).append(rate)
                break
    result = {
        app: sum(vals) / len(vals) if (vals := app_rates.get(app)) else 0.0
        for app in app_list
    }
    return result


def _extract_single_value(frames: list[dict[str, Any]]) -> float | None:
    """Extract first numeric value from Prometheus frames (for single-value queries)."""
    for frame in frames:
        for dep, val in _extract_series_by_deployment(frame):
            if val is not None:
                return val
    return None


def _extract_series_by_pod(frame: dict[str, Any]) -> list[tuple[str, float | None]]:
    """
    Extract (pod, value) pairs from a Prometheus/Grafana frame.
    Handles instant query format: value field with labels, values in data.values.
    """
    out: list[tuple[str, float | None]] = []
    schema = frame.get("schema", {})
    fields = schema.get("fields", [])
    col_vals = frame.get("data", {}).get("values", [])

    if not fields or not col_vals:
        return out

    for i, f in enumerate(fields):
        ftype = str(f.get("type", "")).lower()
        if "time" in ftype:
            continue
        labels = f.get("labels") or {}
        pod = labels.get("pod", "unknown")
        if i >= len(col_vals):
            continue
        val_list = col_vals[i]
        if not isinstance(val_list, list):
            val_list = [val_list]
        for v in val_list:
            try:
                num = float(v) if v is not None else None
            except (TypeError, ValueError):
                num = None
            out.append((pod, num))
    return out


def _extract_series_by_deployment(frame: dict[str, Any]) -> list[tuple[str, float | None]]:
    """
    Extract (deployment, value) pairs from a Prometheus/Grafana frame.
    Handles instant query format: value field with labels, values in data.values.
    """
    out: list[tuple[str, float | None]] = []
    schema = frame.get("schema", {})
    fields = schema.get("fields", [])
    col_vals = frame.get("data", {}).get("values", [])

    if not fields or not col_vals:
        return out

    for i, f in enumerate(fields):
        ftype = str(f.get("type", "")).lower()
        if "time" in ftype:
            continue
        labels = f.get("labels") or {}
        deployment = labels.get("deployment", "unknown")
        if i >= len(col_vals):
            continue
        val_list = col_vals[i]
        if not isinstance(val_list, list):
            val_list = [val_list]
        for v in val_list:
            try:
                num = float(v) if v is not None else None
            except (TypeError, ValueError):
                num = None
            out.append((deployment, num))
    return out
