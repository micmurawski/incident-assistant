import asyncio
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from agent.grafana_client.base import (BaseGrafanaClient, Datasource,
                                       GrafanaBadRequestError)
from agent.grafana_client.utils import loki_time_range_ns, parse_time


class GrafanaClient(BaseGrafanaClient):
    """
    Synchronous Client for Grafana API.
    """

    def __init__(self, url: str, api_key: str, *, timeout_s: float = 60.0):
        super().__init__(url, api_key)
        self._client = httpx.Client(
            base_url=self.url,
            headers=self.headers,
            timeout=httpx.Timeout(timeout_s),
        )
        self._datasources: Optional[Dict[str, Datasource]] = None

    def close(self) -> None:
        self._client.close()

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        max_retries = 3
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                r = self._client.request(method, path, json=json, params=params, timeout=timeout)
                r.raise_for_status()
                return r
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                is_server_error = isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                if (is_server_error or isinstance(e, httpx.RequestError)) and attempt < max_retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 400:
                    raise GrafanaBadRequestError(e.response.text)
                raise
        raise RuntimeError("Retry loop exhausted")

    def get_datasources(self) -> List[Datasource]:
        r = self._request_with_retry("GET", "/api/datasources", timeout=30)
        return [Datasource(uid=ds["uid"], type=ds["type"], name=ds.get("name", "")) for ds in r.json()]

    def _ensure_datasource(self, ds_type: str) -> Datasource:
        if self._datasources is None:
            sources = self.get_datasources()
            self._datasources = {ds.type: ds for ds in sources}
        ds = self._datasources.get(ds_type)
        if not ds:
            raise ValueError(f"No {ds_type} datasource found in Grafana")
        return ds

    def query_prometheus(
        self, expr: str, from_time: str = "now-1h", to_time: str = "now", instant: bool = True
    ) -> Dict[str, Any]:
        uid = self._ensure_datasource(ds_type="prometheus").uid
        from_ms = parse_time(from_time)
        to_ms = parse_time(to_time)
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
        r = self._request_with_retry(
            "POST", "/api/ds/query", params={"ds_type": "prometheus"}, json=payload, timeout=60
        )
        return r.json()

    def query_loki(self, expr: str, from_time: str = "now-1h", to_time: str = "now", limit: int | None = None) -> Dict[str, Any]:
        uid = self._ensure_datasource(ds_type="loki").uid
        from_ms = parse_time(from_time)
        to_ms = parse_time(to_time)
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "loki", "uid": uid},
                    "expr": expr,
                    "queryType": "range",
                
                }
            ],
            "from": str(from_ms),
            "to": str(to_ms),
        }
        if limit:
            payload["queries"][0]["maxLines"] = limit
        r = self._request_with_retry("POST", "/api/ds/query", params={"ds_type": "loki"}, json=payload, timeout=120)
        return r.json()

    def list_loki_labels(
        self, from_time: str = "now-1h", to_time: str = "now", *, query: Optional[str] = None, source: str = "loki"
    ) -> List[str]:
        ds = self._ensure_datasource(source)
        start_ns, end_ns = loki_time_range_ns(from_time, to_time)
        params: Dict[str, Any] = {"start": start_ns, "end": end_ns}
        if query:
            params["query"] = query
        r = self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/labels", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    def list_loki_label_values(
        self,
        label_name: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        *,
        query: Optional[str] = None,
        source: str = "loki",
    ) -> List[str]:
        ds = self._ensure_datasource(source)
        start_ns, end_ns = loki_time_range_ns(from_time, to_time)
        params: Dict[str, Any] = {"start": start_ns, "end": end_ns}
        if query:
            params["query"] = query
        safe_label = quote(label_name, safe="")
        r = self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/label/{safe_label}/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    def list_metrics(
        self,
        match: Optional[str] = None,
        source: str = "prometheus",
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/__name__/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    def get_metric_metadata(self, metric_name: str, source: str = "prometheus") -> List[Dict[str, Any]]:
        ds = self._ensure_datasource(source)
        params = {"metric": metric_name}
        r = self._request_with_retry("GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/metadata", params=params)
        payload = r.json()
        return payload.get("data", {}).get(metric_name, [])

    def get_label_values(
        self,
        label_name: str,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/{label_name}/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    def get_label_names(
        self,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/labels", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]


class AsyncGrafanaClient(BaseGrafanaClient):
    """
    Asynchronous Client for Grafana API.
    """

    def __init__(self, url: str, api_key: str, *, timeout_s: float = 60.0):
        super().__init__(url, api_key)
        self._client = httpx.AsyncClient(
            base_url=self.url,
            headers=self.headers,
            timeout=httpx.Timeout(timeout_s),
        )
        self._datasources: Optional[Dict[str, Datasource]] = None
        self._datasources_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        max_retries = 3
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                r = await self._client.request(method, path, json=json, params=params, timeout=timeout)
                r.raise_for_status()
                return r
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                is_server_error = isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                if (is_server_error or isinstance(e, httpx.RequestError)) and attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 400:
                    raise GrafanaBadRequestError(e.response.text)
                raise
        raise RuntimeError("Retry loop exhausted")

    async def get_datasources(self) -> List[Datasource]:
        r = await self._request_with_retry("GET", "/api/datasources", timeout=30)
        return [Datasource(uid=ds["uid"], type=ds["type"], name=ds.get("name", "")) for ds in r.json()]

    async def _ensure_datasource(self, ds_type: str) -> Datasource:
        if self._datasources is None:
            async with self._datasources_lock:
                if self._datasources is None:
                    sources = await self.get_datasources()
                    self._datasources = {ds.type: ds for ds in sources}
        ds = self._datasources.get(ds_type)
        if not ds:
            raise ValueError(f"No {ds_type} datasource found in Grafana")
        return ds

    async def query_prometheus(
        self, expr: str, from_time: str = "now-1h", to_time: str = "now", instant: bool = True
    ) -> Dict[str, Any]:
        ds = await self._ensure_datasource(ds_type="prometheus")
        from_ms = parse_time(from_time)
        to_ms = parse_time(to_time)
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "prometheus", "uid": ds.uid},
                    "expr": expr,
                    "instant": instant,
                    "range": not instant,
                }
            ],
            "from": str(from_ms),
            "to": str(to_ms),
        }
        r = await self._request_with_retry(
            "POST", "/api/ds/query", params={"ds_type": "prometheus"}, json=payload, timeout=60
        )
        return r.json()

    async def query_loki(
        self, expr: str, from_time: str = "now-1h", to_time: str = "now", limit: int | None = None
    ) -> Dict[str, Any]:
        ds = await self._ensure_datasource(ds_type="loki")
        from_ms = parse_time(from_time)
        to_ms = parse_time(to_time)
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "loki", "uid": ds.uid},
                    "expr": expr,
                    "queryType": "range",
                }
            ],
            "from": str(from_ms),
            "to": str(to_ms),
        }
        if limit:
            payload["queries"][0]["maxLines"] = limit
        r = await self._request_with_retry("POST", "/api/ds/query", params={"ds_type": "loki"}, json=payload, timeout=120)
        return r.json()

    async def list_loki_labels(
        self, from_time: str = "now-1h", to_time: str = "now", *, query: Optional[str] = None, source: str = "loki"
    ) -> List[str]:
        ds = await self._ensure_datasource(source)
        start_ns, end_ns = loki_time_range_ns(from_time, to_time)
        params: Dict[str, Any] = {"start": start_ns, "end": end_ns}
        if query:
            params["query"] = query
        r = await self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/labels", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def list_loki_label_values(
        self,
        label_name: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        *,
        query: Optional[str] = None,
        source: str = "loki",
    ) -> List[str]:
        ds = await self._ensure_datasource(source)
        start_ns, end_ns = loki_time_range_ns(from_time, to_time)
        params: Dict[str, Any] = {"start": start_ns, "end": end_ns}
        if query:
            params["query"] = query
        safe_label = quote(label_name, safe="")
        r = await self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/label/{safe_label}/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def list_metrics(
        self,
        match: Optional[str] = None,
        source: str = "prometheus",
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = await self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = await self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/__name__/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def get_metric_metadata(self, metric_name: str, source: str = "prometheus") -> List[Dict[str, Any]]:
        ds = await self._ensure_datasource(source)
        params = {"metric": metric_name}
        r = await self._request_with_retry("GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/metadata", params=params)
        payload = r.json()
        return payload.get("data", {}).get(metric_name, [])

    async def get_label_values(
        self,
        label_name: str,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = await self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = await self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/label/{label_name}/values", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]

    async def get_label_names(
        self,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> List[str]:
        ds = await self._ensure_datasource(source)
        from_s = parse_time(from_time) // 1000
        to_s = parse_time(to_time) // 1000
        params: Dict[str, Any] = {"start": str(from_s), "end": str(to_s)}
        if match:
            params["match[]"] = match
        r = await self._request_with_retry(
            "GET", f"/api/datasources/uid/{ds.uid}/resources/api/v1/labels", params=params, timeout=60
        )
        payload = r.json()
        values = payload.get("data", []) or []
        return [str(v) for v in values if v is not None]
