import os
import subprocess
import tempfile
import json
import random
from dataclasses import dataclass
from typing import List, Dict, Any
import yaml
from anthropic import Anthropic

# --- ACE Incident Classes (from README.md) ---

INCIDENT_CLASSES = {
    2: {
        "name": "Code Ingestion (Logic Regressions)",
        "target": "code",
        "strategies": [
            "Introduce an O(n^2) loop in a high-traffic path (e.g. checking list memberships).",
            "Remove a cache lookup, forcing redundant expensive database or API operations.",
            "Add a 'N+1' pattern for external calls by moving a bulk fetch into a per-item loop.",
            "Introduce a Regular Expression with Catastrophic Backtracking on specific input patterns.",
            "Replace a fast dictionary lookup with a linear list scan for a key-value store.",
            "Force synchronous processing of a task that should be async (e.g., waiting for a non-critical log write).",
            "Repeatedly re-parse a large static configuration file/string on every request."
        ]
    },
    3: {
        "name": "K8s Configuration (Resource/Config)",
        "target": "k8s",
        "strategies": [
            "Set memory limits just below the application's peak runtime requirement (OOM Trap).",
            "Sabotage readiness/liveness probes to point to non-existent endpoints or set very low timeouts.",
            "Inject a subtle typo in a critical environment variable (e.g., changing 'DB_HOST' to 'DATABASE_HOST').",
            "Mismatch the Service 'targetPort' with the Deployment 'containerPort' (silent traffic drop).",
            "Change a ConfigMap key name while keeping the YAML valid, causing the app to use a bad default value.",
            "Set a 'nodeSelector' that matches no nodes, leaving pods in a 'Pending' state.",
            "Reduce the 'failureThreshold' on liveness probes to 1, causing restarts on minor network blips."
        ]
    },
    4: {
        "name": "Service Code (Runtime/State)",
        "target": "code",
        "strategies": [
            "Introduce a database connection leak by removing a 'close' or 'cleanup' call.",
            "Create a memory leak by appending request metadata to a global/static list that never clears.",
            "Inject a deadlock condition using two locks acquired in different orders across routes.",
            "Leak File Descriptors by opening a file/socket in a request handler and never closing it.",
            "Create Socket Exhaustion by initializing a new HTTP client for every request instead of reusing a session.",
            "Implement 'State Corruption' by modifying a shared global variable across requests without a lock/mutex.",
            "Exhaust the thread pool by introducing a long, un-interruptible sleep in a background task."
        ]
    }
}

@dataclass
class SaboteurResult:
    scenario_id: str
    class_id: int
    patch_content: str
    post_mortem: Dict[str, str]

class SaboteurAgent:
    def __init__(self, model: str = "claude-3-5-sonnet-latest"):
        self.client = Anthropic()
        self.model = model

    def _call_llm(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=4096, temperature=0.7,
            system=system, messages=[{"role": "user", "content": user}]
        )
        return response.content[0].text

    def generate_sabotage(self, service_name: str, file_path: str, class_id: int) -> SaboteurResult:
        """Proposes a 'Golden Sabotage' strictly for Class 2, 3, or 4."""
        if class_id not in [2, 3, 4]:
            raise ValueError("Saboteur only handles classes 2, 3, and 4.")

        with open(file_path, "r") as f:
            content = f.read()

        class_info = INCIDENT_CLASSES[class_id]
        strategy = random.choice(class_info["strategies"])
        
        print(f"🎭 [Saboteur] Generating Class {class_id}: {class_info['name']}")
        print(f"👉 [Strategy] {strategy}")

        system = f"""You are an Expert Chaos Engineer for Kubernetes.
        Goal: Generate a 'Golden Sabotage' for Class {class_id}: {class_info['name']}.
        
        A Golden Sabotage MUST:
        1. Pass static checks (compilation/YAML validation).
        2. Be subtle and pass simple CI/CD gates.
        3. Trigger a runtime incident under load.
        
        For Class 3 (K8s), provide a YAML overlay or a patch that modifies the original manifest.
        For Class 2/4 (Code), provide a standard git diff patch.

        Output format:
        ---
        PATCH:
        <raw patch or YAML overlay here>
        ---
        POST_MORTEM:
        {{
            "root_cause": "brief explanation",
            "fix": "how to resolve it"
        }}
        """

        user = f"""
        TARGET SERVICE: {service_name}
        FILE TYPE: {class_info['target']}
        STRATEGY: {strategy}
        
        FILE CONTENT:
        ```
        {content}
        ```
        
        Generate the sabotage. Ensure it is syntactically correct.
        """

        response = self._call_llm(system, user)
        
        try:
            patch_part = response.split("PATCH:")[1].split("POST_MORTEM:")[0].strip()
            pm_part = response.split("POST_MORTEM:")[1].strip()
            # Clean formatting
            patch_part = patch_part.replace("```patch", "").replace("```diff", "").replace("```yaml", "").replace("```", "").strip()
            pm_part = pm_part.replace("```json", "").replace("```", "").strip()
            
            return SaboteurResult(
                scenario_id=f"ace-{class_id}-{service_name}-{random.randint(100, 999)}",
                class_id=class_id,
                patch_content=patch_part,
                post_mortem=json.loads(pm_part)
            )
        except Exception as e:
            print(f"❌ [Saboteur] Error parsing response: {e}")
            raise

    def validate_patch(self, original_file: str, result: SaboteurResult) -> bool:
        """Gate 1: Validation check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = os.path.join(tmpdir, os.path.basename(original_file))
            with open(original_file, "r") as f:
                content = f.read()
            with open(temp_file, "w") as f:
                f.write(content)

            if result.class_id == 3: # K8s YAML
                try:
                    yaml.safe_load(result.patch_content)
                    print("✅ [Gate 1] YAML Validation passed.")
                    return True
                except Exception as e:
                    print(f"❌ [Gate 1] Invalid YAML: {e}")
                    return False
            else: # Code Patch
                patch_file = os.path.join(tmpdir, "sabotage.patch")
                with open(patch_file, "w") as f:
                    f.write(result.patch_content)
                try:
                    subprocess.run(["patch", temp_file, patch_file], check=True, capture_output=True)
                    # Simple compilation check
                    if original_file.endswith(".py"):
                        subprocess.run(["python3", "-m", "py_compile", temp_file], check=True)
                    elif original_file.endswith(".js"):
                        subprocess.run(["node", "--check", temp_file], check=True)
                    print("✅ [Gate 1] Code validation passed.")
                    return True
                except Exception as e:
                    print(f"❌ [Gate 1] Static check failed: {e}")
                    return False

    def save_to_vault(self, result: SaboteurResult, service: str):
        vault_dir = "fault-vault"
        ext = "yaml" if result.class_id == 3 else "patch"
        patch_path = f"patches/{result.scenario_id}.{ext}"
        
        # Save Patch
        os.makedirs(os.path.join(vault_dir, "patches"), exist_ok=True)
        with open(os.path.join(vault_dir, patch_path), "w") as f:
            f.write(result.patch_content)

        # Update scenarios.yaml
        scenarios_file = os.path.join(vault_dir, "scenarios.yaml")
        with open(scenarios_file, "r") as f:
            data = yaml.safe_load(f) or {"scenarios": []}
        
        data["scenarios"].append({
            "id": result.scenario_id,
            "class": result.class_id,
            "service": service,
            "patch_file": patch_path,
            "post_mortem": result.post_mortem
        })
        
        with open(scenarios_file, "w") as f:
            yaml.dump(data, f, sort_keys=False)
        print(f"💎 [Vault] Saved Class {result.class_id} Sabotage: {result.scenario_id}")

if __name__ == "__main__":
    import sys
    # Usage: python saboteur.py <service> <file> <class_id>
    # Example: python saboteur.py payment payment.py 2
    if len(sys.argv) < 4:
        print("Usage: python saboteur.py <service> <file_path> <class_id>")
    else:
        agent = SaboteurAgent()
        res = agent.generate_sabotage(sys.argv[1], sys.argv[2], int(sys.argv[3]))
        if agent.validate_patch(sys.argv[2], res):
            agent.save_to_vault(res, sys.argv[1])
