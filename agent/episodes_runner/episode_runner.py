import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from episodes_runner.utils import live_timer

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.report import (build_status_report_dict,
                                         detect_differences,
                                         format_diff_status_report)
from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import ToolResult
from agent.tooling.metrics import APPS, NAMESPACE

# Resolve repo root (parent of agent/)
CUR_DIR = Path(__file__).resolve().parent

# Default paths (override with env or CLI)
DEFAULT_SOURCE = Path("/Users/micmur/GITHUB/o8s/services/robot-shop")
DEFAULT_WORKSPACE = Path("/Users/micmur/GITHUB/o8s/workspace")
FAULT_VAULT_DIR = Path("/Users/micmur/GITHUB/o8s/agent/fault_generator/fault-vault")

# Wait after deploy for symptoms to appear (seconds)
DEFAULT_WAIT_SECONDS = 180


def create_workspace(source_dir: Path, workspace_dir: Path) -> None:
    """Copy source to workspace. Overwrites existing workspace."""
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(source_dir, workspace_dir, symlinks=False)
    git_dir = workspace_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    print(f"[1] Created workspace at {workspace_dir}")


def select_fault(fault_vault_dir: Path) -> Path:
    """Select a random fault from fault-vault (directory containing git.patch + INCIDENT.md)."""
    if not fault_vault_dir.exists():
        raise Exception(f"[2] Fault-vault not found: {fault_vault_dir}")
    candidates = []
    for d in fault_vault_dir.iterdir():
        if not d.is_dir():
            continue
        if (d / "git.patch").exists() and (d / "INCIDENT.md").exists():
            candidates.append(d)
    if not candidates:
        raise Exception("[2] No fault scenarios found in fault-vault (need git.patch + INCIDENT.md)")
    chosen = random.choice(candidates)
    print(f"[2] Selected fault: {chosen.name}")
    return chosen


async def get_metrics_summary(window: str = "5m") -> dict:
    """Get metrics report from Grafana if configured; otherwise return placeholder."""
    url = os.environ.get("GRAFANA_URL")
    api_key = os.environ.get("GRAFANA_API_KEY")
    if not url or not api_key:
        raise ValueError("GRAFANA_URL and GRAFANA_API_KEY must be set")
    return await build_status_report_dict(
        client=GrafanaClient(url=url, api_key=api_key),
        namespace=NAMESPACE,
        apps=APPS,
        window=window,
    )


async def apply_fault(workspace_dir: Path, fault_dir: Path) -> None:
    """Apply git.patch in workspace. Returns True on success."""
    patch_file = fault_dir / "git.patch"
    if not patch_file.exists():
        raise Exception(f"[3] No git.patch in fault directory: {fault_dir}")
    print("workspace_dir:", workspace_dir)
    print("patch_file:", patch_file)

    try:
        cmd = ["patch", "-p1"]
        with patch_file.open("rb") as stdin:
            print("stdin:", stdin)
            result = subprocess.run(cmd, cwd=workspace_dir, stdin=stdin, check=True)
            if result.returncode != 0:
                raise Exception(f"[3] git apply failed: {result.stderr or result.stdout}")
            print(f"[3] Applied patch from {fault_dir.name}")
    except Exception as e:
        raise Exception(f"[3] Error applying patch: {e}")


async def deploy_and_wait(
    workspace_dir: Path,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
):
    """
    Run deploy script from workspace k8s/ and wait.
    Streams up to 30 lines of deployment output.
    Returns True if deploy succeeded.
    """
    deploy_script = workspace_dir / "k8s" / "deploy.sh"
    if not deploy_script.exists():
        raise Exception(f"[6] No deploy script at {deploy_script}; skipping deploy")
    try:
        result: ToolResult = await run_cli_command(
            ["bash", "-e", str(deploy_script)],
            timeout=300,
            cwd=str(workspace_dir),
            stream=True,
            tail_lines=10,
        )
        if result.error is not None:
            print(f"[6] Deploy failed: {result.error}")
            raise Exception(f"[6] Deploy failed: {result.error}")
        print(f"[6] Deploy completed; waiting {wait_seconds}s for symptoms...")
        live_timer(wait_seconds)
    except Exception as e:
        print(f"[6] Deploy failed: {e}")
        raise e


def fault_content(fault_dir: Path) -> str:
    """Read FAULT.md from fault directory (fault description)."""
    fault_file = fault_dir / "FAULT.md"
    if not fault_file.exists():
        raise Exception(f"[9] No FAULT.md in fault directory: {fault_dir}")
    return fault_file.read_text().strip()


def incident_content(fault_dir: Path) -> str:
    """Read INCIDENT.md from fault directory (announcement for the team)."""
    incident_file = fault_dir / "INCIDENT.md"
    if not incident_file.exists():
        raise Exception(f"[9] No INCIDENT.md in fault directory: {fault_dir}")
    return incident_file.read_text().strip()


def build_agent_prompt(
    focused_metrics_report: str,
    incident_md: str,
) -> str:
    """Build the prompt for the agent to fix the fault."""
# """
# ---
# Focused metrics comparison (changed services only)
#
# {focused_metrics_report}
# ---
# """
    print(f"\033[33mfocused_metrics_report: {focused_metrics_report}\033[0m")
    incident_start_time = datetime.now() - timedelta(minutes=5)
    return f"""
## Incident announcement
Current time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Incident start time: {incident_start_time.strftime("%Y-%m-%d %H:%M:%S")}
{incident_md}

Your task is to: 
 - provide a root cause analysis of the incident
 - propose a fix
 - execute the fix
 
 Provide your response in post-mortem report format with sections: 
 - Root Cause Analysis
 - Proposed Fix
 - Execution
 - Conclusion
 
Proceed with work right after this message.
Remember: 
- Your fixes need to maintain the API contract with the user.
- Once you need to use deploy tool once fix is ready to be deployed.

"""


async def run_episode(
    selected_fault: Path | None = None,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
) -> dict:
    """
    Run one full episode. Returns a dict with workspace_dir, fault_dir, metrics_before,
    metrics_after, incident_md, and agent_prompt (and success flags).
    """
    source_dir = Path(os.environ.get("EPISODE_SOURCE", str(DEFAULT_SOURCE)))
    workspace_dir = Path(os.environ.get("EPISODE_WORKSPACE", str(DEFAULT_WORKSPACE)))
    fault_vault_dir = FAULT_VAULT_DIR

    out = {
        "workspace_dir": str(workspace_dir),
        "fault_dir": None,
        "fault_id": None,
        "metrics_before": "",
        "metrics_after": "",
        "incident_md": "",
        "agent_prompt": "",
    }

    # 1. Create workspace
    create_workspace(source_dir, workspace_dir)

    # 2. Select fault
    if selected_fault:
        fault_dir = Path(fault_vault_dir) / selected_fault
    else:
        fault_dir = select_fault(fault_vault_dir)

    out["fault_dir"] = str(fault_dir)
    out["fault_id"] = fault_dir.name

    # 4. Metrics before
    if Path(CUR_DIR / "metrics_before.json").exists():
        with open(CUR_DIR / "metrics_before.json", "r") as f:
            out["metrics_before"] = json.load(f)
    else:
        out["metrics_before"] = await get_metrics_summary()
        with open(CUR_DIR / "metrics_before.json", "w") as f:
            json.dump(out["metrics_before"], f)

    # 5. Apply fault
    await apply_fault(workspace_dir, fault_dir)

    # 6. Deploy and wait
    await deploy_and_wait(workspace_dir, wait_seconds)

    # 7. Metrics after
    out["metrics_after"] = await get_metrics_summary()

    out["metrics_diff"] = detect_differences(out["metrics_before"], out["metrics_after"])
    out["focused_metrics_report"] = format_diff_status_report(out["metrics_diff"], "incident")

    # 8. Incident (for team) — we just have the content
    out["incident_md"] = incident_content(fault_dir)
    out["fault_md"] = fault_content(fault_dir)

    # 9. Agent prompt
    out["agent_prompt"] = build_agent_prompt(
        out["focused_metrics_report"],
        out["incident_md"],
    )
    # Print agent prompt in pink color
    print("\033[95m" + out["agent_prompt"] + "\033[0m")

    return out


async def main() -> int:
    import json
    result = await get_metrics_summary()
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
