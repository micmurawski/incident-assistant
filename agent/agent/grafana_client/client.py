import time
from dataclasses import dataclass
from typing import Any

import requests


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

    def __init__(self, url: str, api_key: str):
        """
        Args:
            url: Grafana base URL (e.g. http://host/)
            api_key: Grafana API key for Bearer auth
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )
        self._datasources: dict[str, str] | None = None

    def get_datasources(self) -> list[Datasource]:
        """Fetch all configured datasources."""
        r = self._session.get(f"{self.url}/api/datasources", timeout=30)
        r.raise_for_status()
        return [
            Datasource(uid=ds["uid"], type=ds["type"], name=ds.get("name", ""))
            for ds in r.json()
        ]

    def _ensure_datasource_uid(self, ds_type: str) -> str:
        """Get UID for Prometheus or Loki, caching after first fetch."""
        if self._datasources is None:
            sources = self.get_datasources()
            self._datasources = {ds.type: ds.uid for ds in sources}
        uid = self._datasources.get(ds_type)
        if not uid:
            raise ValueError(f"No {ds_type} datasource found in Grafana")
        return uid

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

    def query_prometheus(
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
        uid = self._ensure_datasource_uid("prometheus")
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

        r = self._session.post(
            f"{self.url}/api/ds/query",
            params={"ds_type": "prometheus"},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return self._extract_prometheus_results(data)

    def _extract_prometheus_results(self, data: dict) -> list[dict[str, Any]]:
        """Extract result frames from Grafana query response."""
        results = []
        for ref_id, resp in data.get("results", {}).items():
            for frame in resp.get("frames", []):
                results.append(frame)
        return results

    def query_loki(
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
        uid = self._ensure_datasource_uid("loki")
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

        r = self._session.post(
            f"{self.url}/api/ds/query",
            params={"ds_type": "loki"},
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        #import json
        #print(data["results"]["A"]["status"])
        #print(json.dumps(data["results"]["A"]["frames"][0]["schema"], indent=4))
        #print("keys: ", data["results"]["A"]["frames"][0]['data']['values'][2][0])
        #with open("data.json", "w") as f:
        #    json.dump(data, f, indent=4)
        #print(json.dumps(data, indent=4))
        return self._extract_loki_results(data)

    def _extract_loki_results(self, data: dict) -> list[dict[str, Any]]:
        """Extract log entries from Grafana Loki query response."""
        logs = []
        for _ref_id, resp in data.get("results", {}).items():
            for frame in resp.get("frames", []):
                schema = frame.get("schema", {})
                schema_fields = schema.get("fields", [])
                values = frame.get("data", {}).get("values", [])
                if len(values) < 2:
                    continue
                times_raw = values[1]
                lines_raw = values[2]
                labels = {}
                if schema_fields and isinstance(schema_fields[0], dict):
                    labels = schema_fields[0].get("labels") or {}
                    if labels and not isinstance(labels, dict):
                        labels = {}
                for ts_val, line_val in zip(times_raw, lines_raw):
                    ts_ns = int(ts_val) if isinstance(ts_val, (int, float)) else 0
                    if ts_ns > 1e15:
                        ts_ns = int(ts_ns / 1000)  # ms to ns if needed
                    logs.append(
                        {
                            "timestamp": ts_ns / 1e9,
                            "message": str(line_val) if line_val else "",
                            "labels": dict(labels),
                        }
                    )
        return logs
