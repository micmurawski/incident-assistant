import random
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent


CODE_CHANGES_DIR = BASE_DIR / ".." / "fault_generator" / "fault-vault"
SHUFFLED_SCENARIOS_DIR = BASE_DIR / "shuffled_scenarios.yaml"


def generate_shuffled_scenarios() -> list[dict]:
    scenarios = []
    for dir in CODE_CHANGES_DIR.iterdir():
        _, class_id, service_name, hash = dir.name.split("-", 3)
        scenario = {
            "id": dir.name,
            "class_id": int(class_id),
            "service_name": service_name,
        }
        scenarios.append(scenario)
    random.shuffle(scenarios)

    return scenarios


if __name__ == "__main__":
    data = {
        "scenarios": generate_shuffled_scenarios()
    }
    with open(SHUFFLED_SCENARIOS_DIR, "w") as f:
        yaml.dump(data, f, sort_keys=False)
