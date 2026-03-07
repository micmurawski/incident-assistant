"""
Detect and diagnose non-JSON-serializable values in nested structures.

Use paths_not_json_serializable() to find exactly which paths would break
json.dumps(), so you can fix serialization at the source (e.g. in the
framework or where data is built) instead of masking the issue.
"""
from typing import Any, List

# Types that are valid for JSON; anything else is considered not serializable.
_JSON_PRIMITIVES = (type(None), str, int, float, bool)


def paths_not_json_serializable(obj: Any, prefix: str = "") -> List[str]:
    """
    Return a list of paths (e.g. "messages[1].content") where the value is not
    JSON-serializable (e.g. SerializationIterator, Pydantic model, custom class).

    Use this to find where non-serializable values are introduced so you can
    fix serialization at the source rather than materializing defensively.
    """
    bad: List[str] = []
    sep = "." if prefix else ""

    if obj is None or isinstance(obj, _JSON_PRIMITIVES):
        return bad
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{prefix}{sep}{k}" if prefix else k
            if v is None or isinstance(v, _JSON_PRIMITIVES):
                continue
            if isinstance(v, dict):
                bad.extend(paths_not_json_serializable(v, key_path))
            elif isinstance(v, list):
                bad.extend(paths_not_json_serializable(v, key_path))
            else:
                # Not dict/list/primitive -> not JSON-serializable (e.g. SerializationIterator, Pydantic model)
                bad.append(key_path)
        return bad
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            idx_path = f"{prefix}[{i}]" if prefix else f"[{i}]"
            if item is None or isinstance(item, _JSON_PRIMITIVES):
                continue
            if isinstance(item, dict):
                bad.extend(paths_not_json_serializable(item, idx_path))
            elif isinstance(item, list):
                bad.extend(paths_not_json_serializable(item, idx_path))
            else:
                bad.append(idx_path)
        return bad
    # Single value that is not dict/list/primitive -> not JSON-serializable
    bad.append(prefix or "<root>")
    return bad
