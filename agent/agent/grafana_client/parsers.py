import math
from datetime import datetime, timezone
from typing import Any


def parse_prom_output(
    data: list,
    parse_time_to_dt: bool = True,
    row_as_dict: bool = True,
    exclude_fields: list[str] | None = None,
) -> None:
    """
    Parse multiple frames from Grafana/Prometheus response and output YAML.

    Output schema:
    frames:
      - fields:
          <field_name>:
            type: <from field.typeInfo.frame>
            labels: <from field.labels>
          ...
        data:
          - <field1>: value1
            <field2>: value2
          ...
    """
    if exclude_fields is None:
        exclude_fields = []
    status =  int(data["results"]["A"]["status"])
    if status // 100 != 2:
        return {"error": f"Error: {status}"}
    frames = data["results"]["A"]["frames"]
    
    output = {"frames": []}
    
    for frame in frames:
        schema = frame.get("schema", {})
        fields = schema.get("fields", [])
        time_indexes = []
        json_indexes = []
        excluded_field_indexes = [
            i for i, field in enumerate(fields) if field.get("name") in exclude_fields
        ]
        if parse_time_to_dt:
            for i, field in enumerate(fields):
                if field.get("type") == "time":
                    time_indexes.append(i)
                    field["type"] = "datetime"
                    field["labels"] = field.get("labels", {})
                    field["name"] = field.get("name", "")
                elif field.get("typeInfo", {}).get("frame") == "json.RawMessage":
                    json_indexes.append(i)
                
        frame_obj = {}

        # Build fields metadata
        fields_meta = {}
        for idx, field in enumerate(fields):
            if idx in excluded_field_indexes:
                continue
            meta = {
                "type": field.get("typeInfo", {}).get("frame", ""),
            }
            if "labels" in field:
                meta["labels"] = field["labels"]
            fields_meta[field["name"]] = meta

        frame_obj["fields"] = fields_meta

        # Prepare data rows
        # Values are usually in frame["data"]["values"]: a list of lists, each field's data
        values = frame.get("data", {}).get("values", [])

        if parse_time_to_dt:
            for i in time_indexes:
                values[i] = [str(datetime.fromtimestamp(v / 1000, tz=timezone.utc)) for v in values[i]]
            for i in json_indexes:
                for v in values[i]:
                    v.pop("filename", None)
                values[i] = [dict_to_str(v) for v in values[i]]
        if not values and "frames" in frame:
            # Try inner frames [fallback]
            values = frame["frames"][0].get("data", {}).get("values", [])
        data_rows = []
        if values and len(values) == len(fields):
            row_count = len(values[0])
            for i in range(row_count):
                if row_as_dict:
                    row = {}
                    for idx, field in enumerate(fields):
                        if idx in excluded_field_indexes:
                            continue
                        row[field["name"]] = values[idx][i]
                else:
                    row = []
                    for idx, field in enumerate(fields):
                        if idx in excluded_field_indexes:
                            continue
                        row.append(values[idx][i])
                data_rows.append(row)
        frame_obj["data"] = data_rows

        output["frames"].append(frame_obj)
    return output


def dict_to_str(data: dict) -> str:
    return ",".join([f"{k}={v}" for k, v in data.items()])


def dynamic_round(data: list[float], target_sig_figs: int = 3) -> list[float]:
    if not data:
        return []

    # Use the smallest non-zero absolute value to determine precision
    # This prevents small numbers from becoming 0.0
    _range = [abs(x) for x in data if x != 0]
    if not _range:
        return data
    reference_val = min(_range)

    precision = max(0, target_sig_figs - 1 - int(math.floor(math.log10(reference_val))))
    return [round(x, precision) for x in data]


def prase_to_table(data: list, parse_time_to_dt: bool = True, separator: str = " | ", exclude_fields: list[str] = None) -> str:
    if exclude_fields is None:
        exclude_fields = []
    output = ""
    status =  int(data["results"]["A"]["status"])
    if status // 100 != 2:
        output = f"Error: {status}"
    frames = data["results"]["A"]["frames"]
    
    for i, frame in enumerate(frames):
        output += f"FRAME {i+1}:\nFields:\n"
        schema = frame.get("schema", {})
        fields = schema.get("fields", [])
        time_indexes = []
        json_indexes = []
        fields_to_round = []
        exclude_fields_indexes = [
            i for i, field in enumerate(fields) if field.get("name") in exclude_fields
        ]
        included_field_indexes = [
            i for i in range(len(fields)) if i not in exclude_fields_indexes
        ]
        if parse_time_to_dt:
            for i, field in enumerate(fields):
                if field.get("type") == "time":
                    time_indexes.append(i)
                    field["type"] = "datetime"
                    field["labels"] = field.get("labels", {})
                    field["name"] = field.get("name", "")
                elif field.get("typeInfo", {}).get("frame") == "json.RawMessage":
                    json_indexes.append(i)

        def _field_sort_key(field_idx: int) -> tuple[int, str]:
            field = fields[field_idx]
            name = str(field.get("name", ""))
            is_time = field.get("type") == "datetime" or name.lower() == "time"
            is_labels = name.lower() == "labels"
            if is_time:
                group = 0
            elif is_labels:
                group = 2
            else:
                group = 1
            return (group, name.lower())

        ordered_field_indexes = sorted(included_field_indexes, key=_field_sort_key)
        frame_obj = {}

        # Build fields metadata
        fields_meta = {}
        output += separator.join(["Name", "Type", "Labels"]) + "\n"


        for idx in ordered_field_indexes:
            field = fields[idx]
            fields_row = []
            meta = {
                "type": field.get("typeInfo", {}).get("frame", ""),
            }
            if field.get("type") in {"float", "double", "number", "float64"}:
                fields_to_round.append(idx)
            if "labels" in field:
                meta["labels"] = field["labels"]
            fields_meta[field["name"]] = meta
            fields_row.append(field["name"])
            fields_row.append(meta["type"])
            fields_row.append(f"'{dict_to_str(field.get("labels", {}))}'")
            output += separator.join(fields_row) + "\n"

        output += "\n"
        frame_obj["fields"] = fields_meta

        # Prepare data rows
        # Values are usually in frame["data"]["values"]: a list of lists, each field's data
        values = frame.get("data", {}).get("values", [])
        output += "Values:\n"
        for idx in fields_to_round:
            values[idx] = dynamic_round(values[idx])
        if parse_time_to_dt:
            for i in time_indexes:
                values[i] = [str(datetime.fromtimestamp(v / 1000, tz=timezone.utc)) for v in values[i]]
            for i in json_indexes:
                # remove filename
                for v in values[i]:
                    v.pop("filename", None)
                values[i] = [dict_to_str(v) for v in values[i]]
        if not values and "frames" in frame:
            # Try inner frames [fallback]
            values = frame["frames"][0].get("data", {}).get("values", [])

        if values and len(values) == len(fields):
            row_count = len(values[0])
            output += separator.join([fields[idx]["name"] for idx in ordered_field_indexes]) + "\n"

            for i in range(row_count):
                row = []
                for idx in ordered_field_indexes:
                    row.append(str(values[idx][i]))
                output += separator.join(row) + "\n"
        output += "\n"
    return output


def extract_loki_results(data: dict) -> list[dict[str, Any]]:
    """Extract log entries from Grafana Loki query response."""
    logs = []
    for _ref_id, resp in data.get("results", {}).items():
        for frame in resp.get("frames", []):
            schema = frame.get("schema", {})
            schema_fields = schema.get("fields", [])
            values = frame.get("data", {}).get("values", [])
            # Expect at least: fields, Time (ms), Line. Some responses also include tsNs and id.
            if len(values) < 3:
                continue
            fields = values[0]
            times_ms = values[1]
            lines_raw = values[2]

            # Prefer the high‑precision tsNs column when available
            ts_ns_values = None
            if len(values) >= 4:
                ts_ns_values = values[3]

            labels = {}
            if schema_fields and isinstance(schema_fields[0], dict):
                labels = schema_fields[0].get("labels") or {}
                if labels and not isinstance(labels, dict):
                    labels = {}
            for idx, (fields_val, line_val) in enumerate(zip(fields, lines_raw)):
                fields_val.pop("filename", None)
                if line_val is None or line_val == "":
                    continue

                # Determine timestamp in seconds since epoch.
                ts_ns = None
                if ts_ns_values is not None and idx < len(ts_ns_values):
                    # tsNs is a string representing nanoseconds since epoch
                    ts_raw = ts_ns_values[idx]
                    try:
                        ts_ns = int(ts_raw)
                    except (TypeError, ValueError):
                        ts_ns = None

                if ts_ns is None:
                    # Fallback to Time column (milliseconds since epoch)
                    if idx < len(times_ms):
                        ts_raw = times_ms[idx]
                        try:
                            ts_ms = int(ts_raw)
                            ts_ns = ts_ms * 1_000_000
                        except (TypeError, ValueError):
                            ts_ns = 0
                    else:
                        ts_ns = 0

                if line_val is None or line_val == "":
                    continue
                logs.append(
                    {
                        "timestamp": ts_ns / 1e9,
                        "message": str(line_val) if line_val else "",
                        "labels": dict(labels),
                        "fields": dict(fields_val),
                    }
                )
    return logs


def extract_prometheus_results(data: dict) -> list[dict[str, Any]]:
    """Extract result frames from Grafana query response."""
    results = []
    for ref_id, resp in data.get("results", {}).items():
        for frame in resp.get("frames", []):
            results.append(frame)
    return results


if __name__ == "__main__":
    import json
    data = json.load(open("data.json"))
    print(prase_to_table(data, separator=", "))
