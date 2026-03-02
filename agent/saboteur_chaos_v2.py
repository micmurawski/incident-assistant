import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List

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
CHAOS_TEMPLATES = [
    {
        "kind": "PodChaos",
        "action": "pod-failure",
        "method": "chaos_pod_failure",
        "params": {
            "duration": ["10m", "15m", "20m"],
            "mode": ["one", "all"]
        },
        "description": "Simulate pod failure for a duration."
    },
    {
        "kind": "NetworkChaos",
        "action": "delay",
        "method": "chaos_network_delay",
        "params": {
            "latency": ["10m", "15m", "20m"],
            "jitter": ["0ms", "50ms"],
            "duration": ["10m", "15m"]
        },
        "description": "Add network latency to pods."
    },
    {
        "kind": "NetworkChaos",
        "action": "loss",
        "method": "chaos_network_loss",
        "params": {
            "loss_percent": [10, 25, 50],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Drop a percentage of network packets."
    },
    {
        "kind": "StressChaos",
        "action": "cpu",
        "method": "chaos_cpu_stress",
        "params": {
            "load": [80, 100],
            "workers": [1, 2, 3],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Stress CPU on matching pods."
    },
    {
        "kind": "StressChaos",
        "action": "memory",
        "method": "chaos_memory_stress",
        "params": {
            "size": ["128MB", "256MB"],
            "duration": ["10m", "15m", "20m"],
        },
        "description": "Consume memory on matching pods."
    }
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
    
    scenario_id = f"chaos-{service}-{template['action']}-{random.randint(1000, 9999)}"
    
    # Construct Post Mortem info
    root_cause = f"Infrastructure issue: {template['description']} applied to service '{service}'."
    if template['kind'] == "NetworkChaos":
        fix = f"Check NetworkChaos resources in namespace '{NAMESPACE}' and delete the one targeting 'app={service}'."
    elif template['kind'] == "PodChaos":
        fix = f"Investigate why pods for '{service}' are failing; check for active PodChaos experiments."
    else:
        fix = f"Monitor resource usage for '{service}' and check for StressChaos experiments."

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
    scenarios_file = os.path.join(vault_dir, "scenarios.yaml")
    
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
    print(f"   Target: {incident.service} | Action: {incident.template['action']}")

if __name__ == "__main__":
    import sys
    num_incidents = 1
    if len(sys.argv) > 1:
        num_incidents = int(sys.argv[1])
    
    for _ in range(num_incidents):
        incident = generate_random_incident()
        save_incident_to_vault(incident)
