from typing import Any, Dict, Optional

import pandas as pd

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.parsers import extract_labels, extract_loki_results
from agent.grafana_client.utils import to_dataframe

NAMESPACE = "application"


def _ensure_namespace_in_query(query: str | None) -> str:
    if query is None:
        return f"{{namespace=\"{NAMESPACE}\"}}"
    else:
        extracted_labels = extract_labels(query)
        extracted_labels.update({"namespace": NAMESPACE})
        return f"{{{','.join([f'{k}="{v}"' for k, v in extracted_labels.items()])}}}"


def prometheus_to_df(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert Grafana Prometheus query results (DS query API response) to a pandas DataFrame.

    The resulting DataFrame is in 'long' format, with labels as individual columns,
    a 'timestamp' column, and a 'value' column.
    """
    all_rows = []

    results = data.get("results", {})
    for ref_id, resp in results.items():
        frames = resp.get("frames", [])
        for frame in frames:
            schema = frame.get("schema", {})
            fields = schema.get("fields", [])
            data_vals = frame.get("data", {}).get("values", [])

            if not fields or not data_vals:
                continue

            # Find the time field index
            time_idx = next((i for i, f in enumerate(fields) if f.get("type") == "time"), None)

            # Process each non-time field as a series
            for i, field in enumerate(fields):
                if i == time_idx:
                    continue

                labels = field.get("labels") or {}
                field_name = field.get("name") or "Value"

                # Check if this field has values
                field_vals = data_vals[i]
                for j, val in enumerate(field_vals):
                    row = {
                        "metric": field_name,
                        **labels
                    }
                    if time_idx is not None and j < len(data_vals[time_idx]):
                        # Grafana Prometheus frames use milliseconds for time
                        ts_ms = data_vals[time_idx][j]
                        row["timestamp"] = pd.to_datetime(ts_ms, unit="ms", utc=True)

                    row["value"] = val
                    all_rows.append(row)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Organize columns: timestamp first, then metric, then labels, then value
    cols = df.columns.tolist()
    preferred_order = ["timestamp", "metric"]
    other_cols = [c for c in cols if c not in preferred_order and c != "value"]
    final_cols = [c for c in preferred_order if c in cols] + other_cols + (["value"] if "value" in cols else [])

    return df[final_cols]


def loki_to_df(data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert Grafana Loki query results to a flattened pandas DataFrame.

    Labels and fields are expanded into individual columns prefixed with 'label_' and 'field_'.
    """
    logs = extract_loki_results(data)
    if not logs:
        return pd.DataFrame()

    df = pd.DataFrame(logs)

    # Expand 'labels' dict into columns
    if "labels" in df.columns:
        labels_df = pd.json_normalize(df["labels"]).add_prefix("label_")
        df = pd.concat([df.drop(columns=["labels"]), labels_df], axis=1)

    # Expand 'fields' dict into columns
    if "fields" in df.columns:
        fields_df = pd.json_normalize(df["fields"]).add_prefix("field_")
        df = pd.concat([df.drop(columns=["fields"]), fields_df], axis=1)

    # Convert numeric timestamp to datetime objects
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

    # Order columns: timestamp, message, then labels/fields
    cols = df.columns.tolist()
    preferred_order = ["timestamp", "message"]
    other_cols = [c for c in cols if c not in preferred_order]
    final_cols = [c for c in preferred_order if c in cols] + other_cols

    return df[final_cols]


class GrafanaPandasClient:
    """
    A wrapper around synchronous GrafanaClient that returns query results as well-described pandas DataFrames.
    """

    def __init__(self, url, token):
        self.client = GrafanaClient(url, token)

    def query_prometheus(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        instant: bool = True,
    ) -> pd.DataFrame:
        """
        Run a PromQL query and return results as a DataFrame.
        """
        # expr = _ensure_namespace_in_query(expr)
        data = self.client.query_prometheus(expr, from_time, to_time, instant)
        return to_dataframe(data, drop_fields=["tsNs"])

    def query_loki(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        limit: int | None = None,
    ) -> pd.DataFrame:
        """
        Run a LogQL query and return results as a DataFrame.
        """
        # expr = _ensure_namespace_in_query(expr)
        data = self.client.query_loki(expr, from_time, to_time, limit)
        return to_dataframe(data, drop_fields=["tsNs"])

    def list_loki_labels(
        self, from_time: str = "now-1h", to_time: str = "now", *, query: Optional[str] = None, source: str = "loki"
    ) -> pd.Series:
        """List available Loki labels as a Series."""
        return pd.Series(self.client.list_loki_labels(from_time, to_time, query=query, source=source), name="label")

    def list_loki_label_values(
        self,
        label_name: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        *,
        query: Optional[str] = None,
        source: str = "loki",
    ) -> pd.Series:
        """List values for a Loki label as a Series."""
        return pd.Series(
            self.client.list_loki_label_values(label_name, from_time, to_time, query=query, source=source),
            name=label_name,
        )

    def list_metrics(
        self,
        match: Optional[str] = None,
        source: str = "prometheus",
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> pd.Series:
        """List Prometheus metrics as a Series."""
        return pd.Series(self.client.list_metrics(match, source, from_time, to_time), name="metric")

    def get_metric_metadata(self, metric_name: str, source: str = "prometheus") -> pd.DataFrame:
        """Get metric metadata as a DataFrame."""
        return pd.DataFrame(self.client.get_metric_metadata(metric_name, source))

    def get_label_values(
        self,
        label_name: str,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> pd.Series:
        """List values for a Prometheus label as a Series."""
        return pd.Series(
            self.client.get_label_values(label_name, source, match, from_time, to_time), name=label_name
        )

    def get_label_names(
        self,
        source: str = "prometheus",
        match: Optional[str] = None,
        from_time: str = "now-1h",
        to_time: str = "now",
    ) -> pd.Series:
        """List label names for a metric/selector as a Series."""
        return pd.Series(self.client.get_label_names(source, match, from_time, to_time), name="label_name")

    def close(self) -> None:
        """Close the underlying client."""
        self.client.close()

    def __getattr__(self, name: str) -> Any:
        """Forward all other attributes and methods to the underlying GrafanaClient."""
        return getattr(self.client, name)


def main():
    import json

    from agent.repo_paths import api_key_path

    key_path = api_key_path()
    with open(key_path) as f:
        data = json.load(f)
        GRAFANA_URL = data["grafana_url"]
        GRAFANA_API_KEY = data["grafana_api_token"]
    pd_client = GrafanaPandasClient(url=GRAFANA_URL, token=GRAFANA_API_KEY)
    df = pd_client.query_prometheus('up{job="linkerd-proxy"}', from_time="now-5m", instant=True)
    print(df.head())


if __name__ == "__main__":
    main()
