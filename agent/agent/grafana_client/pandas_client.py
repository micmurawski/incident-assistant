from typing import Any, Dict

import pandas as pd

from .client import GrafanaClient
from .parsers import extract_loki_results


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
    A wrapper around GrafanaClient that returns query results as well-described pandas DataFrames.
    """
    def __init__(self, client: GrafanaClient):
        self.client = client
        
    async def query_prometheus(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        instant: bool = True,
    ) -> pd.DataFrame:
        """
        Run a PromQL query and return results as a DataFrame.
        """
        data = await self.client.query_prometheus(expr, from_time, to_time, instant)
        return prometheus_to_df(data)
        
    async def query_loki(
        self,
        expr: str,
        from_time: str = "now-1h",
        to_time: str = "now",
        limit: int = 5000,
    ) -> pd.DataFrame:
        """
        Run a LogQL query and return results as a DataFrame.
        """
        data = await self.client.query_loki(expr, from_time, to_time, limit)
        return loki_to_df(data)

    async def aclose(self) -> None:
        """Close the underlying client."""
        await self.client.aclose()

    def __getattr__(self, name: str) -> Any:
        """Forward all other attributes and methods to the underlying GrafanaClient."""
        return getattr(self.client, name)
