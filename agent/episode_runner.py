#!/usr/bin/env python3
"""
Episode runner: executes a single fault-injection episode end-to-end.

Steps:
  1. Create workspace: copy service code from robot-shop to workspace.
  2. Remove .git from workspace (agents must not see git history).
  3. Select a random fault from the fault-vault.
  4. Get metrics summary before fault.
  5. Apply fault to the workspace (git apply patch).
  6. Deploy service and wait for problems to appear (default 3 min).
  7. Get metrics summary after fault.
  8. Use INCIDENT.md to announce the incident to the team.
  9. Create prompt with metrics (before/after) and incident for the agent to fix the fault.

Usage:
  python -m agent.episode_runner [--workspace-dir DIR] [--wait-minutes N] [--no-deploy] [--no-metrics]
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Resolve repo root (parent of agent/)
AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent

# Default paths (override with env or CLI)
DEFAULT_SOURCE = REPO_ROOT / "services" / "robot-shop"
DEFAULT_WORKSPACE = REPO_ROOT / "workspace"
FAULT_VAULT_DIR = AGENT_DIR / "fault_generator" / "fault-vault"

# Robot Shop app labels (for metrics)
ROBOT_SHOP_APPS = [
    "cart", "catalogue", "user", "payment", "shipping",
    "ratings", "dispatch", "web",
]
ROBOT_SHOP_NAMESPACE = "robot-shop"

# Wait after deploy for symptoms to appear (seconds)
DEFAULT_WAIT_SECONDS = 180


def step1_create_workspace(source_dir: Path, workspace_dir: Path) -> None:
    """Copy source to workspace. Overwrites existing workspace."""
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(source_dir, workspace_dir, symlinks=False)
    print(f"[1] Created workspace at {workspace_dir}")


def step2_remove_git(workspace_dir: Path) -> None:
    """Remove .git so agents do not see git history."""
    git_dir = workspace_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
        print("[2] Removed .git from workspace")
    else:
        print("[2] No .git in workspace (already clean)")


def step3_select_fault(fault_vault_dir: Path) -> Path | None:
    """Select a random fault from fault-vault (directory containing git.patch + INCIDENT.md)."""
    if not fault_vault_dir.exists():
        print(f"[3] Fault-vault not found: {fault_vault_dir}")
        return None
    candidates = []
    for d in fault_vault_dir.iterdir():
        if not d.is_dir():
            continue
        if (d / "git.patch").exists() and (d / "INCIDENT.md").exists():
            candidates.append(d)
    if not candidates:
        print("[3] No fault scenarios found in fault-vault (need git.patch + INCIDENT.md)")
        return None
    chosen = random.choice(candidates)
    print(f"[3] Selected fault: {chosen.name}")
    return chosen


def get_metrics_summary(window: str = "15m") -> str:
    """Get metrics report from Grafana if configured; otherwise return placeholder."""
    url = os.environ.get("GRAFANA_URL")
    api_key = os.environ.get("GRAFANA_API_KEY")
    if not url or not api_key:
        return "# Metrics (Grafana not configured)\nSet GRAFANA_URL and GRAFANA_API_KEY to fetch real metrics.\n"
    try:
        from agent.grafana_client.client import GrafanaClient
        from agent.grafana_client.report import build_status_report
        client = GrafanaClient(url=url, api_key=api_key)
        return build_status_report(
            client,
            namespace=ROBOT_SHOP_NAMESPACE,
            apps=ROBOT_SHOP_APPS,
            window=window,
        )
    except Exception as e:
        return f"# Metrics (error)\nGrafana request failed: {e}\n"


def step5_apply_fault(workspace_dir: Path, fault_dir: Path) -> bool:
    """Apply git.patch in workspace. Returns True on success."""
    patch_file = fault_dir / "git.patch"
    if not patch_file.exists():
        print("[5] No git.patch in fault directory")
        return False
    try:
        result = subprocess.run(
            ["patch", "-p1", "<", str(patch_file)],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"[5] git apply failed: {result.stderr or result.stdout}")
            return False
        print(f"[5] Applied patch from {fault_dir.name}")
        return True
    except Exception as e:
        print(f"[5] Error applying patch: {e}")
        return False


def step6_deploy_and_wait(
    workspace_dir: Path,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
) -> bool:
    """Run deploy script from workspace k8s/ and wait. Returns True if deploy succeeded."""
    deploy_script = workspace_dir / "k8s" / "deploy.sh"
    if not deploy_script.exists():
        print(f"[6] No deploy script at {deploy_script}; skipping deploy")
        return False
    try:
        subprocess.run(
            [str(deploy_script)],
            cwd=workspace_dir,
            check=True,
            capture_output=False,
        )
    except subprocess.CalledProcessError as e:
        print(f"[6] Deploy failed: {e}")
        return False
    print(f"[6] Deploy completed; waiting {wait_seconds}s for symptoms...")
    time.sleep(wait_seconds)
    return True


def step9_incident_content(fault_dir: Path) -> str:
    """Read INCIDENT.md from fault directory (announcement for the team)."""
    incident_file = fault_dir / "INCIDENT.md"
    if not incident_file.exists():
        return ""
    return incident_file.read_text()


def step10_build_agent_prompt(
    metrics_before: str,
    metrics_after: str,
    incident_md: str,
    fault_id: str,
) -> str:
    """Build the prompt for the agent to fix the fault."""
    return f"""# Incident: {fault_id}

## Incident announcement
{incident_md}
---
## Metrics before fault

{metrics_before}

---
## Metrics after fault

{metrics_after}
---

Your task: diagnose and fix the fault. Use the codebase and metrics; do not assume the cause from the incident description alone.
"""


def run_episode(
    source_dir: Path | None = None,
    workspace_dir: Path | None = None,
    fault_vault_dir: Path | None = None,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
    skip_deploy: bool = False,
    skip_metrics: bool = False,
) -> dict:
    """
    Run one full episode. Returns a dict with workspace_dir, fault_dir, metrics_before,
    metrics_after, incident_md, and agent_prompt (and success flags).
    """
    source_dir = source_dir or Path(os.environ.get("EPISODE_SOURCE", str(DEFAULT_SOURCE)))
    workspace_dir = workspace_dir or Path(os.environ.get("EPISODE_WORKSPACE", str(DEFAULT_WORKSPACE)))
    fault_vault_dir = fault_vault_dir or FAULT_VAULT_DIR

    out = {
        "workspace_dir": str(workspace_dir),
        "fault_dir": None,
        "fault_id": None,
        "metrics_before": "",
        "metrics_after": "",
        "incident_md": "",
        "agent_prompt": "",
        "steps_ok": {},
    }

    # 1. Create workspace
    step1_create_workspace(source_dir, workspace_dir)
    out["steps_ok"]["create_workspace"] = True

    # 2. Remove .git
    step2_remove_git(workspace_dir)
    out["steps_ok"]["remove_git"] = True

    # 3. Select fault
    fault_dir = step3_select_fault(fault_vault_dir)
    if not fault_dir:
        out["steps_ok"]["select_fault"] = False
        return out
    out["fault_dir"] = str(fault_dir)
    out["fault_id"] = fault_dir.name
    out["steps_ok"]["select_fault"] = True

    # 4. Metrics before
    if not skip_metrics:
        out["metrics_before"] = get_metrics_summary(workspace_dir)
    else:
        out["metrics_before"] = "# Metrics skipped (--no-metrics)\n"
    out["steps_ok"]["metrics_before"] = True

    # 5. Apply fault
    if not step5_apply_fault(workspace_dir, fault_dir):
        out["steps_ok"]["apply_fault"] = False
        return out
    out["steps_ok"]["apply_fault"] = True

    # 6. Deploy and wait
    if not skip_deploy:
        out["steps_ok"]["deploy_and_wait"] = step6_deploy_and_wait(workspace_dir, wait_seconds)
    else:
        print("[6] Deploy skipped (--no-deploy)")
        out["steps_ok"]["deploy_and_wait"] = None

    # 7. Metrics after
    if not skip_metrics:
        out["metrics_after"] = get_metrics_summary(workspace_dir)
    else:
        out["metrics_after"] = "# Metrics skipped (--no-metrics)\n"
    out["steps_ok"]["metrics_after"] = True

    # 8. Incident (for team) — we just have the content
    out["incident_md"] = step9_incident_content(fault_dir)
    out["steps_ok"]["incident"] = True

    # 9. Agent prompt
    out["agent_prompt"] = step10_build_agent_prompt(
        out["metrics_before"],
        out["metrics_after"],
        out["incident_md"],
        out["fault_id"],
    )
    out["steps_ok"]["agent_prompt"] = True

    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one fault-injection episode (workspace + fault + metrics + prompt)."
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=None,
        help=f"Workspace directory (default: {DEFAULT_WORKSPACE})",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help=f"Source robot-shop directory (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--fault-vault-dir",
        type=Path,
        default=FAULT_VAULT_DIR,
        help=f"Fault-vault directory (default: {FAULT_VAULT_DIR})",
    )
    parser.add_argument(
        "--wait-minutes",
        type=float,
        default=DEFAULT_WAIT_SECONDS / 60,
        help="Minutes to wait after deploy (default: 3)",
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Skip deploy and wait (only prepare workspace + apply fault)",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="Skip metrics (use placeholders in prompt)",
    )
    parser.add_argument(
        "--output-prompt",
        type=Path,
        default=None,
        help="Write agent prompt to this file",
    )
    args = parser.parse_args()

    wait_seconds = int(args.wait_minutes * 60)
    result = run_episode(
        source_dir=args.source_dir,
        workspace_dir=args.workspace_dir,
        fault_vault_dir=args.fault_vault_dir,
        wait_seconds=wait_seconds,
        skip_deploy=args.no_deploy,
        skip_metrics=args.no_metrics,
    )

    if not result["steps_ok"].get("select_fault"):
        print("Episode failed: could not select a fault.", file=sys.stderr)
        return 1
    if not result["steps_ok"].get("apply_fault"):
        print("Episode failed: could not apply patch.", file=sys.stderr)
        return 1

    if args.output_prompt:
        args.output_prompt.write_text(result["agent_prompt"], encoding="utf-8")
        print(f"Agent prompt written to {args.output_prompt}")

    print("\n--- Agent prompt (first 800 chars) ---")
    print(result["agent_prompt"][:800])
    if len(result["agent_prompt"]) > 800:
        print("...")
    print("---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
