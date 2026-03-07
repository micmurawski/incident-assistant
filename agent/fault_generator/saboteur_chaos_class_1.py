import os
import random
from dataclasses import dataclass
from typing import Any, Dict

import yaml

# --- Configuration for Robot Shop ---
NAMESPACE = "application"
SERVICES = [
    "cart",
    "catalogue",
    "dispatch",
    "mongo",
    "mysql",
    "payment",
    "ratings",
    "redis",
    "shipping",
    "user",
    "web"
]

# --- Chaos Templates based on chaos_meshr.py ---
# Note: We only include methods that actually create/modify chaos experiments.
CHAOS_TEMPLATES = [
    {
        "method": "chaos_pod_failure",
        "params": {
            "duration": ["10m", "15m", "20m"],
            "mode": ["one", "all"],
        },
        "description": "Simulate pod failure for a duration.",
    },
    {
        "method": "chaos_pod_kill",
        "params": {
            "mode": ["one", "all", "fixed"],
            "fixed_replicas": [1, 2, 3],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Kill one or more pods to test restart and failover.",
    },
    {
        "method": "chaos_network_delay",
        "params": {
            "latency": ["100ms", "200ms", "500ms"],
            "jitter": ["0ms", "50ms"],
            "duration": ["10m", "15m"],
        },
        "description": "Add network latency to pods.",
    },
    {
        "method": "chaos_network_loss",
        "params": {
            "loss_percent": [10, 25, 50],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Drop a percentage of network packets.",
    },
    {
        "method": "chaos_network_partition",
        "params": {
            "direction": ["to", "from", "both"],
            "mode": ["one", "all"],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Partition traffic between two groups of pods.",
    },
    {
        "method": "chaos_network_bandwidth",
        "params": {
            "rate": ["1mbps", "500kbps"],
            "mode": ["one", "all"],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Limit egress bandwidth for matching pods.",
    },
    {
        "method": "chaos_cpu_stress",
        "params": {
            "load": [80, 100],
            "workers": [1, 2, 3],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Stress CPU on matching pods.",
    },
    {
        "method": "chaos_memory_stress",
        "params": {
            "size": ["128MB", "256MB"],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Consume memory on matching pods.",
    },
    {
        "method": "chaos_io_latency",
        "params": {
            "volume_path": ["/data", "/var/lib/mysql"],
            "delay": ["100ms", "200ms"],
            "percent": [50, 100],
            "mode": ["one", "all"],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Inject latency into disk I/O on matching pods.",
    },
    {
        "method": "chaos_http_abort",
        "params": {
            "port": [80, 8080],
            "code": [500, 503],
            "mode": ["one", "all"],
            "duration": ["5m", "10m", "15m"],
        },
        "description": "Abort HTTP requests with a given status code.",
    },
]


@dataclass
class IncidentInstance:
    scenario_id: str
    service: str
    template: Dict[str, Any]
    selected_params: Dict[str, Any]
    post_mortem: Dict[str, str]


def generate_random_incident() -> IncidentInstance:
    service = random.choice(SERVICES)
    template = random.choice(CHAOS_TEMPLATES)

    selected_params = {}
    for param, values in template["params"].items():
        selected_params[param] = random.choice(values)

    # Add standard params
    selected_params["namespace"] = NAMESPACE
    selected_params["label_selector"] = f"app={service}"

    scenario_id = f"chaos-{service}-{template['method']}-{random.randint(1000, 9999)}"

    # Construct Post Mortem info
    root_cause = f"Infrastructure issue: {template['description']} applied to service '{service}'."
    method = template["method"]
    if method.startswith("chaos_network_"):
        fix = f"Check NetworkChaos resources in namespace '{NAMESPACE}' and delete the one targeting 'app={service}'."
    elif method.startswith("chaos_pod_"):
        fix = f"Investigate why pods for '{service}' are affected; check for active PodChaos experiments."
    elif method.startswith("chaos_cpu_") or method.startswith("chaos_memory_"):
        fix = f"Monitor CPU and memory usage for '{service}' and check for StressChaos experiments."
    elif method.startswith("chaos_io_"):
        fix = f"Inspect disk performance for '{service}' and check for IOChaos experiments on the relevant volumes."
    elif method.startswith("chaos_http_"):
        fix = f"Check HTTPChaos experiments targeting '{service}' and validate ingress/service configuration."
    else:
        fix = f"Review Chaos Mesh experiments impacting '{service}' and clean up any unexpected resources."

    return IncidentInstance(
        scenario_id=scenario_id,
        service=service,
        template=template,
        selected_params=selected_params,
        post_mortem={
            "root_cause": root_cause,
            "fix": fix
        }
    )


def save_incident_to_vault(incident: IncidentInstance):
    vault_dir = "fault-vault"
    scenarios_file = os.path.join(vault_dir, "scenarios_class_1.yaml")

    # Ensure directory exists
    os.makedirs(vault_dir, exist_ok=True)

    # Load existing
    if os.path.exists(scenarios_file):
        with open(scenarios_file, "r") as f:
            data = yaml.safe_load(f) or {"scenarios": []}
    else:
        data = {"scenarios": []}

    # Create the scenario entry
    # Note: We store the 'method' and 'params' so the agent/runner knows how to trigger it via chaos_meshr.py
    new_scenario = {
        "id": incident.scenario_id,
        "class": 1,
        "service": incident.service,
        "chaos_method": incident.template["method"],
        "chaos_params": incident.selected_params,
        "description": f"Class 1 Chaos: {incident.template['description']} on {incident.service}",
        "post_mortem": incident.post_mortem
    }

    data["scenarios"].append(new_scenario)

    with open(scenarios_file, "w") as f:
        yaml.dump(data, f, sort_keys=False)

    print(f"✅ Created Class 1 Incident: {incident.scenario_id}")
    print(f"   Target: {incident.service} | Method: {incident.template['method']}")


if __name__ == "__main__":
    import sys
    num_incidents = 1
    if len(sys.argv) > 1:
        num_incidents = int(sys.argv[1])

    for _ in range(num_incidents):
        incident = generate_random_incident()
        save_incident_to_vault(incident)
