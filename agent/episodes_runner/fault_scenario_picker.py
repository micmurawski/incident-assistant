"""Run scenarios in shuffled order; fault_history.yaml tracks completed and failed runs."""

from pathlib import Path

import yaml

_EPISODES_DIR = Path(__file__).resolve().parent
FAULT_SCENARIOS_PATH = _EPISODES_DIR / "shuffled_scenarios.yaml"
FAULT_HISTORY_PATH = _EPISODES_DIR / "fault_history.yaml"

_MAX_ERROR_LEN = 2000


def create_fault_scenario_history() -> None:
    if not FAULT_HISTORY_PATH.exists():
        FAULT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAULT_HISTORY_PATH, "w") as f:
            yaml.dump({"history": []}, f)


def _load_history() -> dict:
    create_fault_scenario_history()
    with open(FAULT_HISTORY_PATH, "r") as f:
        data = yaml.safe_load(f)
    if not data or not isinstance(data, dict):
        return {"history": []}
    if "history" not in data or data["history"] is None:
        data["history"] = []
    return data


def _save_history(history: dict) -> None:
    with open(FAULT_HISTORY_PATH, "w") as f:
        yaml.dump(history, f)


def _entry_status(entry: dict) -> str:
    """Legacy entries without ``status`` are treated as completed."""
    return entry.get("status") or "completed"


def _completed_ids(history: list) -> set[str]:
    return {h["id"] for h in history if _entry_status(h) == "completed"}


def _scenario_base(scenario: dict) -> dict:
    """Stable fields to store in history (id, class_id, service_name)."""
    return {
        "id": scenario["id"],
        "class_id": scenario["class_id"],
        "service_name": scenario["service_name"],
    }


def pick_fault_scenario() -> dict:
    """
    - If the last history entry is ``failed``, return that scenario again (retry).
    - Otherwise return the first scenario in ``shuffled_scenarios.yaml`` whose ``id``
      is not yet ``completed`` in history.

    Does not write history; call ``record_episode_success`` / ``record_episode_failure``
    after the episode run.
    """
    with open(FAULT_SCENARIOS_PATH, "r") as f:
        scenarios = yaml.safe_load(f)["scenarios"]

    history = _load_history()
    hist = history["history"]

    if hist and _entry_status(hist[-1]) == "failed":
        sid = hist[-1]["id"]
        chosen = next((s for s in scenarios if s["id"] == sid), None)
        if chosen is None:
            raise RuntimeError(
                f"Last history entry is failed id {sid!r} but that id is not in shuffled_scenarios.yaml"
            )
        print(f"[2] Retrying failed fault scenario: {chosen['id']}")
        return chosen

    done = _completed_ids(hist)
    chosen = None
    for scenario in scenarios:
        if scenario["id"] not in done:
            chosen = scenario
            break

    if chosen is None:
        raise RuntimeError(
            "No remaining scenarios (every id in shuffled_scenarios.yaml is already completed in fault_history.yaml)."
        )

    print(f"[2] Picked fault scenario (next in shuffled order): {chosen['id']}")
    return chosen


def record_episode_success(scenario: dict) -> None:
    """Mark scenario as completed: replace a trailing failed entry for same id, or append."""
    history = _load_history()
    hist = history["history"]
    base = _scenario_base(scenario)
    row = {**base, "status": "completed"}

    if hist and _entry_status(hist[-1]) == "failed" and hist[-1]["id"] == scenario["id"]:
        hist[-1] = row
    else:
        hist.append(row)

    _save_history(history)
    print(f"[history] Recorded completed: {scenario['id']}")


def record_episode_failure(scenario: dict, error: str) -> None:
    """Append or update last row as failed with a short error string."""
    history = _load_history()
    hist = history["history"]
    err = (error or "").strip()
    if len(err) > _MAX_ERROR_LEN:
        err = err[: _MAX_ERROR_LEN] + "…"

    base = _scenario_base(scenario)
    row = {**base, "status": "failed", "error": err}

    if hist and _entry_status(hist[-1]) == "failed" and hist[-1]["id"] == scenario["id"]:
        hist[-1] = row
    else:
        hist.append(row)

    _save_history(history)
    print(f"[history] Recorded failed: {scenario['id']}")
