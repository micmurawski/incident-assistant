import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Datasource:
    """Grafana datasource info."""

    uid: str
    type: str
    name: str


class GrafanaClient:
    """
    Client for Grafana API.
    Authorizes with API key and queries Prometheus/Loki datasources.
    """

    def __init__(self, url: str, api_key: str, *, timeout_s: float = 60.0):
        """
        Args:
            url: Grafana base URL (e.g. http://host/)
            api_key: Grafana API key for Bearer auth
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        # Async HTTP client for Grafana API.
        self._client = httpx.AsyncClient(
            base_url=self.url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout_s),
        )
        self._datasources: dict[str, Datasource] | None = None
        self._datasources_lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close underlying HTTP session."""
        await self._client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with exponential backoff retry."""
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                r = await self._client.request(
                    method, path, json=json, params=params, timeout=timeout
                )
                r.raise_for_status()
                return r
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                # Only retry on 5xx or network errors
                is_server_error = (
                    isinstance(e, httpx.HTTPStatusError)
                    and e.response.status_code >= 500
                )
                is_network_error = isinstance(e, httpx.RequestError)

                if (is_server_error or is_network_error) and attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise
        raise RuntimeError("Retry loop exhausted")

    async def get_datasources(self) -> list[Datasource]:
        """Fetch all configured datasources."""
        r = await self._request_with_retry("GET", "/api/datasources", timeout=30)
        return [
            Datasource(uid=ds["uid"], type=ds["type"], name=ds.get("name", ""))
            for ds in r.json()
        ]

    async def _ensure_datasource(self, ds_type: str) -> Datasource:
        """Get datasource object for a given type, caching after first fetch."""
        if self._datasources is None:
            async with self._datasources_lock:
                if self._datasources is None:
                    sources = await self.get_datasources()
                    self._datasources = {ds.type: ds for ds in sources}
        ds = self._datasources.get(ds_type)
        if not ds:
            raise ValueError(f"No {ds_type} datasource found in Grafana")
        return ds

    async def _ensure_datasource_uid(self, ds_type: str) -> str:
        """Get UID for Prometheus or Loki, caching after first fetch."""
        return (await self._ensure_datasource(ds_type)).uid

    def _parse_time(self, t: str) -> int:
        """Convert 'now', 'now-5m', 'now-1h' to ms epoch."""
        now_ms = int(time.time() * 1000)
        if t == "now":
            return now_ms
        if t.startswith("now-"):
            rest = t[4:]
            if rest.endswith("m"):
                sec = int(rest[:-1]) * 60
            elif rest.endswith("h"):
                sec = int(rest[:-1]) * 3600
            elif rest.endswith("s"):
                sec = int(rest[:-1])
            else:
                sec = int(rest)  # assume seconds
            return now_ms - sec * 1000
        return int(t)

    async def query_prometheus(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        instant: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Run a PromQL query via Grafana datasource API.

        Args:
            expr: PromQL expression
            from_time: Start time (e.g. 'now-5m', 'now-1h')
            to_time: End time (e.g. 'now')
            instant: If True, use instant query; if False, range query

        Returns:
            Parsed frames from Grafana response
        """
        uid = await self._ensure_datasource_uid("prometheus")
        from_ms = self._parse_time(from_time)
        to_ms = self._parse_time(to_time)

        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "prometheus", "uid": uid},
                    "expr": expr,
                    "instant": instant,
                    "range": not instant,
                }
            ],
            "from": str(from_ms),
            "to": str(to_ms),
        }

        r = await self._request_with_retry(
            "POST",
            "/api/ds/query",
            params={"ds_type": "prometheus"},
            json=payload,
            timeout=60,
        )
        data = r.json()
        return data

    async def query_loki(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Run a LogQL query via Grafana datasource API.

        Args:
            expr: LogQL expression (e.g. '{namespace="application", app="cart"} |= "ERROR"')
            from_time: Start time
            to_time: End time
            limit: Max log lines to return

        Returns:
            List of log entries: [{"timestamp": str, "message": str, "labels": dict}, ...]
        """
        uid = await self._ensure_datasource_uid("loki")
        from_ms = self._parse_time(from_time)
        to_ms = self._parse_time(to_time)

        # Loki server limit is often 5000; cap to avoid "max entries limit exceeded"
        max_lines = min(limit, 5000)
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "loki", "uid": uid},
                    "expr": expr,
                    "queryType": "range",
                    "maxLines": max_lines,
                }
            ],
            "from": str(from_ms),
            "to": str(to_ms),
        }

        r = await self._request_with_retry(
            "POST",
            "/api/ds/query",
            params={"ds_type": "loki"},
            json=payload,
            timeout=120,
        )
        data = r.json()
        return data

    async def list_prometheus_metrics(
        self,
        match: str | None = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> list[str]:
        """
        List available Prometheus metric names via Grafana's CallResource API.
        Optionally filter using a Prometheus match[] selector.
        """
        ds = await self._ensure_datasource("prometheus")
        from_s = self._parse_time(from_time) // 1000
        to_s = self._parse_time(to_time) // 1000

        params: dict[str, Any] = {
            "start": str(from_s),
            "end": str(to_s),
        }
        if match:
            params["match[]"] = match

        r = await self._request_with_retry(
            "GET",
            f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/__name__/values",
            params=params,
            timeout=60,
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def get_prometheus_metric_metadata(
        self, metric_name: str
    ) -> list[dict[str, Any]]:
        """
        Get metadata (type, help, unit) for a specific Prometheus metric via Grafana's CallResource API.
        """
        ds = await self._ensure_datasource("prometheus")
        params = {"metric": metric_name}

        r = await self._request_with_retry(
            "GET",
            f"/api/datasources/uid/{ds.uid}/resources/api/v1/metadata",
            params=params,
        )
        payload = r.json()
        return payload.get("data", {}).get(metric_name, [])

    async def list_prometheus_label_names(
        self,
        match: str | None = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> list[str]:
        """
        List all label names available for a given metric or selector via Grafana's CallResource API.
        This helps identify what "input parameters" (labels) a metric accepts.
        Example: match='http_requests_total'
        """
        ds = await self._ensure_datasource("prometheus")
        from_s = self._parse_time(from_time) // 1000
        to_s = self._parse_time(to_time) // 1000

        params: dict[str, Any] = {
            "start": str(from_s),
            "end": str(to_s),
        }
        if match:
            params["match[]"] = match

        r = await self._request_with_retry(
            "GET",
            f"/api/datasources/uid/{ds.uid}/resources/api/v1/labels",
            params=params,
            timeout=60,
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def list_prometheus_label_values(
        self,
        label_name: str,
        match: str | None = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> list[str]:
        """
        List available values for a specific Prometheus label via Grafana's CallResource API.
        Example: label_name='method', match='http_requests_total'
        """
        ds = await self._ensure_datasource("prometheus")
        from_s = self._parse_time(from_time) // 1000
        to_s = self._parse_time(to_time) // 1000

        params: dict[str, Any] = {
            "start": str(from_s),
            "end": str(to_s),
        }
        if match:
            params["match[]"] = match

        r = await self._request_with_retry(
            "GET",
            f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/{label_name}/values",
            params=params,
            timeout=60,
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]
