import re
from typing import Any

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.parsers import extract_loki_results


def _normalize_for_similarity(text: str) -> str:
    """Normalize log line for comparison: strip IDs, numbers, timestamps."""
    t = text.strip()
    # Replace UUIDs, hex hashes, numeric IDs
    t = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "<UUID>", t)
    t = re.sub(r"\b[0-9a-fA-F]{16,}\b", "<HEX>", t)
    t = re.sub(r"\b\d{10,}\b", "<NUM>", t)  # long numbers
    t = re.sub(r"\b\d+\.\d+\b", "<FLOAT>", t)  # floats
    t = re.sub(r"\b\d+\b", "<N>", t)  # short integers
    # ISO timestamps
    t = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?", "<TS>", t)
    t = re.sub(r"\b[A-Z][a-z]{2} \d{1,2},? \d{4}", "<TS>", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower()


def _text_to_tokens(text: str) -> set[str]:
    """Simple tokenization for TF-IDF style similarity."""
    t = _normalize_for_similarity(text)
    return set(w for w in re.split(r"\W+", t) if len(w) > 1)


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


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
    logs = extract_loki_results(await client.query_loki(expr, from_time=from_time, to_time=to_time, limit=5000))
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


def group_by_similarity(
    logs: list[dict[str, Any]],
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Group similar error logs and return one representative per group.

    Uses Jaccard similarity on normalized tokens. Logs with similarity >= threshold
    are grouped together; one representative (first in group) is returned.

    Args:
        logs: List of {"message": str, ...}
        threshold: Minimum similarity (0-1) to group two logs

    Returns:
        List of group representatives: [{"message": str, "count": int, "labels": dict}, ...]
    """
    if not logs:
        return []

    # Build token sets
    entries = []
    for log in logs:
        msg = log.get("message", "")
        entries.append(
            {
                "message": msg,
                "labels": log.get("labels", {}),
                "tokens": _text_to_tokens(msg),
            }
        )

    # Greedy clustering: merge if any pair in group has sim >= threshold
    groups: list[list[int]] = []
    used = [False] * len(entries)

    for i in range(len(entries)):
        if used[i]:
            continue
        group = [i]
        used[i] = True
        for j in range(i + 1, len(entries)):
            if used[j]:
                continue
            sim = _jaccard_similarity(entries[i]["tokens"], entries[j]["tokens"])
            if sim >= threshold:
                group.append(j)
                used[j] = True
        groups.append(group)

    result = []
    for g in groups:
        idx = g[0]
        rep = entries[idx]
        result.append(
            {
                "message": rep["message"],
                "count": len(g),
                "labels": rep["labels"],
            }
        )
    return result


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
