import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.report import build_status_report_dict
from agent.tooling.metrics import APPS, NAMESPACE
from episodes_runner.utils import detect_differences, live_timer

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE = BASE_DIR / "services" / "robot-shop"
DEFAULT_WORKSPACE = BASE_DIR / "workspace"
FAULT_SCENARIOS_DIR = Path(__file__).resolve().parent / "shuffled_scenarios.yaml"
FAULT_HISTORY_DIR = Path(__file__).resolve().parent / "fault_history.yaml"

FAULT_VAULT_DIR = BASE_DIR / "agent" / "fault_generator" / "fault-vault"

API_KEY = json.load(open(BASE_DIR / "api_key.json"))
GRAFANA_API_KEY = API_KEY["grafana_api_token"]
GRAFANA_URL = API_KEY["grafana_url"]

ENV = {
    **os.environ.copy(),
    "AWS_ACCESS_KEY_ID": API_KEY["robot"]["access_key_id"],
    "AWS_SECRET_ACCESS_KEY": API_KEY["robot"]["secret_access_key"],
    "AWS_REGION": "us-east-1",
}


GRAFANA_CLIENT = GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY)


def create_fault_scenario_history() -> None:
    if not FAULT_HISTORY_DIR.exists():
        FAULT_HISTORY_DIR.touch()
        with open(FAULT_HISTORY_DIR, "w") as f:
            yaml.dump({"history": []}, f)


def pick_fault_scenario() -> dict:
    with open(FAULT_HISTORY_DIR, "r") as f1, open(FAULT_SCENARIOS_DIR, "r") as f2:
        history = yaml.safe_load(f1)
        scenarios = yaml.safe_load(f2)["scenarios"]
        idx = max(0, len(history["history"]) - 1)
        history["history"].append(scenarios[idx])
    with open(FAULT_HISTORY_DIR, "w") as f:
        yaml.dump(history, f)
    print(f"[2] Picked fault scenario: {scenarios[idx]['id']}")
    return scenarios[idx]


def create_workspace(source_dir: Path, workspace_dir: Path) -> None:
    """Copy source to workspace. Overwrites existing workspace."""
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(source_dir, workspace_dir, symlinks=False)
    git_dir = workspace_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    print(f"[1] Created workspace at {workspace_dir}")


def build_agent_prompt(metrics_before: dict, metrics_after: dict, incident_md: str, secret_info: str) -> str:
    diff = detect_differences(metrics_before, metrics_after)
    metrics_diff = yaml.dump(diff, indent=4)

    res = f"""
    ## Detected differences in metrics
    {metrics_diff}
    """

    if incident_md is not None:
        res += f"""
        ## Incident announcement
        {incident_md}
        ---
        """
    if secret_info is not None:
        res += f"""
        ## Secret information
        {secret_info}
        ---
        """
    return res


def apply_patch(fault_dir: Path) -> None:
    if not (fault_dir / "git.patch").exists():
        raise Exception(f"[3] No git.patch in {fault_dir.name}")
    cmd = ["git", "apply", str(fault_dir / "git.patch")]
    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=DEFAULT_WORKSPACE, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"[3] git apply failed: {result.stderr or result.stdout}")
    print(f"[3] Applied patch from {fault_dir.name}")


def deploy(workspace_dir: Path, env: dict) -> None:
    cmd = ["bash", str(workspace_dir / "k8s" / "deploy.sh")]
    result = subprocess.run(cmd, cwd=workspace_dir, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise Exception(f"[3] kubectl apply failed: {result.stderr or result.stdout}")
    print(f"[3] Deployed to {workspace_dir.name}")


async def deploy_async(workspace_dir: Path, env: dict) -> None:
    cmd = ["bash", str(workspace_dir / "k8s" / "deploy.sh")]
    print(f"[3] Running deploy command: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(workspace_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    logs = []
    max_lines = 20  # Only keep last N lines

    assert process.stdout is not None
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            trimmed_line = line.decode().rstrip()
            if trimmed_line:
                logs.append(trimmed_line)
                if len(logs) > max_lines:
                    logs.pop(0)
            print(f"[deploy-log] {trimmed_line}")
    finally:
        process.stdout.close()
    returncode = await process.wait()
    if returncode != 0:
        trimmed_output = "\n".join(logs)
        raise Exception(f"[3] kubectl apply failed (exit={returncode}):\n---\n{trimmed_output}\n---")
    print(f"[3] Deployed to {workspace_dir.name}")


def apply_chaos_mesh_fault(manifest_path: Path, env: dict) -> None:
    cmd = ["kubectl", "apply", "-f", manifest_path]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise Exception(f"[3] kubectl apply failed: {result.stderr or result.stdout}")
    print(f"[3] Applied chaos mesh fault from {manifest_path}")


def delete_chaos_mesh_all_experiments(env: dict) -> None:
    resources = "podchaos,networkchaos,stresschaos,iochaos,httpchaos"
    cmd = ["kubectl", "delete", resources, "--all", "-A"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise Exception(f"[3] kubectl delete {resources} failed: {result.stderr or result.stdout}")
    print(f"[3] Deleted all chaos mesh {resources}")


async def apply_scenario(fault_scenario: dict, metrics_before: dict) -> None:
    print(f"[3] Applying fault scenario: {fault_scenario['id']}")
    fault_dir = FAULT_VAULT_DIR / fault_scenario["id"]
    fault_md = (fault_dir / "FAULT.md").read_text()
    incident_md = (fault_dir / "INCIDENT.md").read_text()
    experiment_manifest = fault_dir / "experiment.yaml"

    if experiment_manifest.exists():
        apply_chaos_mesh_fault(experiment_manifest, ENV)
    apply_patch(fault_dir)
    await deploy_async(DEFAULT_WORKSPACE, ENV)
    print("[3] Waiting for 5 minutes to let the fault take effect...")
    live_timer(60*6)
    metrics_after = await build_status_report_dict(
        GRAFANA_CLIENT, NAMESPACE, APPS,
        window="5m",
        env=ENV,
        cwd=DEFAULT_WORKSPACE,
    )
    return build_agent_prompt(metrics_before, metrics_after, incident_md, fault_md)


async def read_metrics_before() -> dict:
    METRICS_BEFORE_PATH = DEFAULT_WORKSPACE / "metrics_before.yaml"
    if METRICS_BEFORE_PATH.exists():
        with open(METRICS_BEFORE_PATH, "r") as f:
            metrics_before = yaml.safe_load(f)
    else:
        metrics_before = await build_status_report_dict(
            GRAFANA_CLIENT, NAMESPACE, APPS,
            window="5m",
            env=ENV,
            cwd=DEFAULT_WORKSPACE,
        )
        with open(METRICS_BEFORE_PATH, "w") as f:
            yaml.dump(metrics_before, f)
    return metrics_before


async def main():
    metrics_before = await read_metrics_before()
    create_fault_scenario_history()
    create_workspace(DEFAULT_SOURCE, DEFAULT_WORKSPACE)
    fault_scenario = pick_fault_scenario()
    user_prompt = await apply_scenario(fault_scenario, metrics_before)
    print(user_prompt)

    delete_chaos_mesh_all_experiments(ENV)

    await GRAFANA_CLIENT.aclose()



if __name__ == "__main__":
    asyncio.run(main())
