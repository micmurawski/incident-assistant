import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd


def parse_time(t: str) -> int:
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


def loki_time_range_ns(from_time: str, to_time: str) -> Tuple[str, str]:
    """Loki label APIs expect start/end as nanoseconds since Unix epoch (strings)."""
    from_ms = parse_time(from_time)
    to_ms = parse_time(to_time)
    return str(from_ms * 1_000_000), str(to_ms * 1_000_000)


def parse_loki_json(raw_data: dict):
    """
    Parses a Grafana Loki JSON result file into one or more Pandas DataFrames.
    Preserves all metadata (stats, executed queries, etc.) in the DataFrame's .attrs attribute.
    """
    dataframes = []

    # Iterate through all query results (A, B, etc.)
    for ref_id, result in raw_data.get('results', {}).items():
        frames = result.get('frames', [])

        for frame in frames:
            schema = frame.get('schema', {})
            fields = schema.get('fields', [])
            meta = schema.get('meta', {})
            data = frame.get('data', {})
            values = data.get('values', [])

            if not values:
                continue

            # 1. Create mapping from field names to data values
            column_names = [field['name'] for field in fields]

            # Create the base DataFrame
            df = pd.DataFrame(dict(zip(column_names, values)))

            # 2. Convert Time to high-precision datetime
            if 'Time' in df.columns:
                # Timestamps in Grafana Loki JSON are typically in milliseconds
                df['Time'] = pd.to_datetime(df['Time'], unit='ms')

                # Check for nanosecond precision in 'nanos' field
                # data['nanos'] is a list of lists, matching values structure
                nanos_data = data.get('nanos', [])
                if nanos_data:
                    # Find the index of the Time column in the schema
                    time_idx = next((i for i, f in enumerate(fields) if f['name'] == 'Time'), None)
                    if time_idx is not None and len(nanos_data) > time_idx:
                        nanos_list = nanos_data[time_idx]
                        if nanos_list:
                            # Add nanosecond part to existing timestamps
                            # Note: nanos_list contains values like 961599, which are often offset nanos
                            # We use pd.to_timedelta for precision
                            df['Time'] += pd.to_timedelta(nanos_list, unit='ns')

            # 3. Handle Labels (flatten them into separate columns for easier analysis)
            if 'labels' in df.columns:
                labels_df = pd.json_normalize(df['labels'])
                # Prefix label columns to avoid collisions or keep as is
                # labels_df.columns = [f"label_{c}" for c in labels_df.columns]
                df = pd.concat([df.drop(columns=['labels']), labels_df], axis=1)

            # 4. Attach metadata and refId to the DataFrame
            df.attrs['loki_meta'] = meta
            df.attrs['ref_id'] = ref_id
            df.attrs['status'] = result.get('status')

            dataframes.append(df)

    return dataframes


def _labels_to_columns(labels: pd.Series) -> pd.DataFrame:
    """Flatten Loki label dicts per row; non-dict values become empty dicts."""

    def to_dict(x: Any) -> dict:
        if isinstance(x, dict):
            return x
        return {}

    return pd.json_normalize(labels.apply(to_dict))


def _frame_to_dataframe(
    ref_id: str,
    frame_index: int,
    frame: dict,
    metadata_store: dict,
    drop_fields: Optional[Iterable[str]] = None,
) -> Optional[pd.DataFrame]:
    schema = frame.get("schema", {})
    fields = schema.get("fields", [])
    meta = schema.get("meta", {})
    data = frame.get("data", {})
    values = data.get("values", [])

    if not values:
        return None

    metadata_store[ref_id]["frames_meta"].append(meta)

    column_names = [field["name"] for field in fields]
    df = pd.DataFrame(dict(zip(column_names, values)))

    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], unit="ms")
        nanos_data = data.get("nanos", [])
        if nanos_data:
            time_idx = next((i for i, f in enumerate(fields) if f["name"] == "Time"), None)
            if time_idx is not None and len(nanos_data) > time_idx:
                nanos_list = nanos_data[time_idx]
                if nanos_list:
                    df["Time"] += pd.to_timedelta(nanos_list, unit="ns")

    if "labels" in df.columns:
        labels_df = _labels_to_columns(df["labels"])
        df = pd.concat([df.drop(columns=["labels"]), labels_df], axis=1)

    df["ref_id"] = ref_id
    df["frame_index"] = frame_index

    if drop_fields:
        df = df.drop(columns=list(drop_fields), errors="ignore")
    return df


def to_dataframe(
    raw_data: dict,
    *,
    combine: bool = True,
    return_metadata: bool = False,
    drop_fields: Optional[Iterable[str]] = None,
) -> Union[
    pd.DataFrame,
    Dict[str, List[pd.DataFrame]],
    Tuple[pd.DataFrame, dict],
    Tuple[Dict[str, List[pd.DataFrame]], dict],
]:
    """
    Parse Grafana Loki query JSON (``results`` / ``frames``) into pandas objects.

    **Row model:** one row per log sample. Multiple Loki frames are either stacked
    (``combine=True``) or kept separate (``combine=False``). Column names are the union
    of all frame schemas; where schemas differ, missing values are ``NaN``.

    **Metadata:** per-``ref_id`` status and per-frame ``frames_meta``. With
    ``combine=True``, the same structure is also set on
    ``DataFrame.attrs['loki_metadata']``. Use ``return_metadata=True`` if you need
    metadata alongside an empty DataFrame or want to avoid relying on ``attrs``.

    Parameters
    ----------
    raw_data
        Parsed JSON object with a top-level ``results`` mapping (ref_id → query result).
    combine
        If True (default), concatenate all frames into one DataFrame and add ``ref_id``
        and ``frame_index`` (index of the frame in that query's ``frames`` array).
        If False, return ``{ ref_id: [df, ...] }`` with one DataFrame per non-empty frame.
    return_metadata
        If True, return ``(result, metadata_store)`` instead of only ``result``.
    drop_fields
        Optional column names to omit from each frame. Applied after schema parsing
        and label flattening, so names match final DataFrame columns (including
        ``ref_id`` / ``frame_index`` if you list them). Missing names are ignored.
    """
    metadata_store: Dict[str, Any] = {}
    all_frames_dfs: List[pd.DataFrame] = []
    split: Dict[str, List[pd.DataFrame]] = {}

    for ref_id, result in raw_data.get("results", {}).items():
        metadata_store[ref_id] = {
            "status": result.get("status"),
            "frames_meta": [],
        }
        frames = result.get("frames", [])

        for frame_index, frame in enumerate(frames):
            df = _frame_to_dataframe(
                ref_id, frame_index, frame, metadata_store, drop_fields=drop_fields
            )
            if df is None:
                continue
            if combine:
                all_frames_dfs.append(df)
            else:
                split.setdefault(ref_id, []).append(df)

    if combine:
        if not all_frames_dfs:
            out: pd.DataFrame = pd.DataFrame()
        else:
            out = pd.concat(all_frames_dfs, ignore_index=True, sort=False)
            out.attrs["loki_metadata"] = metadata_store
        if return_metadata:
            return out, metadata_store
        return out

    # combine=False: drop empty ref_ids for a cleaner dict
    split = {k: v for k, v in split.items() if v}
    if return_metadata:
        return split, metadata_store
    return split