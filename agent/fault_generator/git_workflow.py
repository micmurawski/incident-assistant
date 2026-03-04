"""
Git-based fault workflow:
  1. git checkout master -f && git checkout -b <uuid>
  2. AI agent applies changes in repo and writes FAULT.md
  3. git add -A && git commit
  4. git format-patch -1 HEAD --stdout > <uuid>.patch
"""

import asyncio
import os
import random
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from framework import AsyncFlow
from framework.decorators import node

from agent.file_ops import FileOpsManager
from agent.llm import LLMAgent
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools, CodebaseWriteTools

FAULT_CLASS_DESCRIPTIONS = {
    2: """**Class 2 – Code ingestion (logic / performance regressions)**
Introduce a logical bug or performance regression in application code.
Targets: service source code under the current working directory (Node, Python, Go, Java, PHP).
Examples (for inspiration only; you choose): wrong HTTP status, broken control flow, wrong calculation, 
unnecessary delay on a hot path, always returning empty/wrong data. Be creative and vary the fault.""",
    3: """**Class 3 – K8s configuration**
Introduce a misconfiguration in the Kubernetes manifest (k8s/robot-shop-eks.yaml).
Targets: any Deployment (app or backing store—targeting redis/mongodb/mysql/rabbitmq can cause cascading failures).
Examples (for inspiration only): memory limit too low (OOMKilled), wrong env var (e.g. REDIS_HOST, MONGO_URL, DB_HOST), 
deployment label mismatch with Service selector, wrong liveness/readiness path or port.""",
    4: """**Class 4 – Runtime / state**
Introduce a runtime or state-related fault in application code (e.g. resource exhaustion).
Targets: service code that uses DBs, Redis, or HTTP clients.
Examples (for inspiration only): long blocking sleep in health or hot path, connection leak (not closing in error path), 
unbounded in-memory growth or cache without eviction. Be creative.""",
}

APP_SERVICES = [
    "cart",
    "catalogue",
    "user",
    "payment",
    "shipping",
    "ratings",
    "dispatch",
    "web",
]
REPO_ROOT = Path("/Users/micmur/GITHUB/o8s/services/robot-shop")
CURRENT_DIR = Path(__file__).resolve().parent

FAULT_INJECTOR_SYSTEM = """You are a fault-injection agent for the Robot Shop microservices app. Your job is to introduce exactly one fault into the repository and document it.

You will be given a fault class (2, 3, or 4) and context about the app. You must:

1. **Apply changes** only under the current working directory. Edit code or K8s manifests to introduce the fault. Use the minimum necessary edits (e.g. one wrong env var, one broken line, one misconfigured limit).

2. **Write FAULT.md** at `FAULT.md` with this structure:
   - **Title**: One line describing the fault.
   - **Description**: What was changed and where.
   - **Symptom**: What users or monitoring will see.
   - **Root cause**: Why this causes the symptom.
   - **Fix**: How to fix it (revert, correct config, etc.).

Use the codebase read/write tools to inspect and edit files. When done, reply briefly that you have applied the fault and written FAULT.md. Do not run shell commands.

- DON'T MAKE COMMENTS, LOGS, OR EXCEPTIONS, OR USE VAR NAMES THAT WOULD BE HINTING FOR THE FAULT. 
- DON'T USE METHOD NAMES OR FUNCTION NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE VARIABLE NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE CLASS NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE MODULE NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE PACKAGE NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE PROJECT NAMES THAT WOULD BE HINTING FOR THE FAULT.
- DON'T USE USER NAMES THAT WOULD BE HINTING FOR THE FAULT.

YOUR FAULTS NEED TO BE DISCRITE. 
"""


def _run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cwd = cwd or REPO_ROOT
    return subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def git_checkout_branch(branch_name: str, repo_root: Path = REPO_ROOT) -> None:
    """Run: git checkout master -f && git checkout -b <branch_name>."""
    r = _run_git("checkout", "master", "-f", cwd=repo_root)
    if r.returncode != 0:
        raise RuntimeError(f"git checkout master -f failed: {r.stderr or r.stdout}")
    r = _run_git("checkout", "-b", branch_name, cwd=repo_root)
    if r.returncode != 0:
        raise RuntimeError(f"git checkout -b {branch_name} failed: {r.stderr or r.stdout}")


def git_commit_and_format_patch(
    branch_name: str,
    patch_out_path: Path,
    repo_root: Path = REPO_ROOT,
    commit_message: str | None = None,
) -> None:
    """Run: git add -A && git commit -m <msg> && git format-patch -1 HEAD --stdout > patch_out_path."""
    msg = commit_message or f"fault: {branch_name}"
    r = _run_git("add", "-A", cwd=repo_root)
    if r.returncode != 0:
        raise RuntimeError(f"git add -A failed: {r.stderr or r.stdout}")
    r = _run_git("commit", "-m", msg, cwd=repo_root)
    if r.returncode != 0:
        raise RuntimeError(f"git commit failed: {r.stderr or r.stdout}")
    patch_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(patch_out_path, "w", encoding="utf-8") as f:
        r = subprocess.run(
            ["git", "format-patch", "-1", "HEAD", "--stdout"],
            cwd=repo_root,
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if r.returncode != 0:
        raise RuntimeError(f"git format-patch failed: {r.stderr}")


class FaultInjector(LLMAgent):
    def __init__(self, name: str, system_prompt: str, api_settings: dict[str, Any] | None = None):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        api_settings["temperature"] = 0.8 
        self.cwd = settings.get("workspace.path") or os.getcwd()
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.file_ops_manager = FileOpsManager(cwd=self.cwd)
        self.name = name


settings = SettingsManager.get_instance()
settings.set("api.provider", "gemini")
settings.set("api.model_id", "gemini-2.5-pro:thinking")
settings.set("api.api_key", "AIzaSyAmNJmXdpejo2LQWDowsqsK3bvMhZSXfII")
settings.set("workspace.path", str(REPO_ROOT))


tools = CodebaseReadTools | CodebaseWriteTools
fault_injector = FaultInjector(name="fault-injector", system_prompt=FAULT_INJECTOR_SYSTEM)
fault_injector.bind_tools(tools, {"cwd": fault_injector.cwd})
fault_injector.call_llm - "tools" >> tools
tools >> fault_injector.call_llm


@node
async def start_fault_injector(service_name: str, fault_class: int, uuid: str):
    branch_name = f"fault-{service_name}-{fault_class}-{uuid}"
    git_checkout_branch(branch_name)
    return {
        "messages": [
            {
                "role": "user",
                "content": f"You are a fault-injector for the {service_name} service. "
                "You are tasked with introducing a fault into the codebase. "
                "The fault class is {fault_class}. The fault is {FAULT_CLASS_DESCRIPTIONS[fault_class]}. " 
            }
        ],
        "branch_name": branch_name
    }


@node
async def end_fault_injector(branch_name: str):
    patch_out_path = CURRENT_DIR / "fault-vault" / branch_name / "git.patch"
    patch_out_path.parent.mkdir(parents=True, exist_ok=True)
    fault_vault_dir = CURRENT_DIR / "fault-vault" / branch_name
    fault_vault_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "FAULT.md", fault_vault_dir / "FAULT.md")
    os.remove(REPO_ROOT / "FAULT.md")
    git_commit_and_format_patch(branch_name, patch_out_path)



start_fault_injector >> fault_injector.call_llm >> end_fault_injector

async_flow = AsyncFlow(start_fault_injector)


async def main():

    select_service = random.choice(APP_SERVICES)
    fault_id = random.choice([2, 3, 4])
    shared = {
        "service_name": select_service,
        "fault_class": fault_id,
        "uuid": str(uuid.uuid4())
    }
    print(f"Injecting fault {fault_id} into {select_service} with UUID {shared['uuid']}")
    await asyncio.sleep(1)
    await async_flow.run_async(shared)
    print("Fault injection complete")

if __name__ == "__main__":
    asyncio.run(main())
