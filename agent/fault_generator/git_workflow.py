"""
Git-based fault workflow using worktrees (enables future parallel execution):

  1. git worktree add -b <branch> <worktree_path> master  (isolated dir per run)
  2. AI agent applies changes in worktree and writes FAULT.md (cwd = worktree_path)
  3. git add -A && git commit && git format-patch -1 HEAD in worktree
  4. Copy FAULT.md and patch to fault-vault; remove worktree

Each run uses a dedicated worktree under WORKTREES_DIR so multiple runs can be
executed in parallel without sharing the same working directory.
"""

import asyncio
import glob
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from framework import AsyncFlow
from framework.decorators import node
from openinference.instrumentation import using_attributes
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import trace
from phoenix.otel import register

from agent.llm import LLMAgent
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager
from agent.tooling import CodebaseReadTools, CodebaseWriteTools
from agent.tracing import trace_flow
from agent.repo_paths import robot_shop_dir
from agent.worktree import WorkTreeService

os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

tracer_provider = register(project_name="fault-generator-tracing")


# Get a tracer for your application
tracer = trace.get_tracer(__name__)

tracer_provider = register(auto_instrument=True)

# Instrument Anthropic SDK so traces use Anthropic semantics (calls still go to
# whatever base_url the client uses, e.g. Minimax when using MiniMaxHandler).
AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
# GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)


work_tree_service = WorkTreeService()

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
REPO_ROOT = robot_shop_dir()
WORKTREES_DIR = REPO_ROOT.parent / "robot-shop-worktrees"
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

3. **Write INCIDENT.md** at `INCIDENT.md` with this structure:
    - **Title**: One line describing the incident.
    - **Description**: What happened. How it's observed by the user, what is metrics are affected.
    - This message will be used to announce the incident to a team. You CANNOT give any information about the fault or the fix.

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
    """Run: git checkout master -f && git checkout -b <branch_name>. (Legacy: single workdir.)"""
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
    """Run: git add -A && git commit -m <msg> && git format-patch -1 HEAD --stdout > patch_out_path.
    When using worktrees, pass the worktree path as repo_root."""
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
    def __init__(self, name: str, cwd: Path, system_prompt: str, api_settings: dict[str, Any] | None = None):
        settings = SettingsManager.get_instance()
        api_settings = api_settings or settings.get("api")
        api_settings["temperature"] = 0.8
        self.cwd = str(cwd)
        self.system_prompt = system_prompt
        self.api_handler: ApiHandler = build_api_handler(**api_settings)
        self.name = name
        self.shared_context = {}


async def create_agent(repo_root: Path, work_tree_path: Path, branch_name: str):
    result = await work_tree_service.create_worktree(
        cwd=str(repo_root),
        path=str(work_tree_path),
        branch=branch_name,
        base_branch="master",
        create_new_branch=True,
    )
    if not result.success:
        raise RuntimeError(f"Failed to create worktree: {result.message}")
    agent = FaultInjector(name=branch_name, cwd=work_tree_path, system_prompt=FAULT_INJECTOR_SYSTEM)

    tools = CodebaseReadTools | CodebaseWriteTools
    agent.bind_tools(tools, {"cwd": agent.cwd})

    # react agent

    agent.call_llm - "tools" >> tools
    tools >> agent.call_llm

    start_fault_injector >> agent.call_llm
    agent.call_llm - "default" >> check_fault_injector
    check_fault_injector - "reflect" >> agent.call_llm
    check_fault_injector - "default" >> end_fault_injector
    agent.flow = _TracedFlow(start=start_fault_injector)
    agent.get_flow_graph_png("fault_injector.png")
    return agent

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")
settings = SettingsManager.get_instance()
# settings.set("api.provider", "minimax")
# settings.set("api.model_id", "MiniMax-M2.5")
# settings.set("api.api_key", MINIMAX_API_KEY)
# Override Minimax API endpoint (passed to MiniMaxHandler as base_url)
settings.set("api.provider", "gemini")
settings.set("api.model_id", "gemini-3.1-pro-preview:thinking")
settings.set("api.api_key", GEMINI_API_KEY)

shared = {
    "apps": APP_SERVICES,
    "fault_classes": [2, 3, 4],
}


@node
async def select_service_and_fault_class(apps: list[str], fault_classes: list[int]):
    # create list of dicts with all possible combinations of apps and fault classes
    app_fault_combinations = []
    for app in apps:
        for fault_class in fault_classes:
            app_fault_combinations.append({"service_name": app, "fault_class": fault_class})
    return {
        "items": app_fault_combinations
    }


@node
async def create_batch(apps: list[str], fault_classes: list[int]):
    """Populate shared['items'] with all (service_name, fault_class) combinations."""
    items = [
        {"service_name": app, "fault_class": fc}
        for app in apps
        for fc in fault_classes
    ]
    return {"items": items[::-1]}


@node
async def start_fault_injector(service_name: str, fault_class: int, uuid_value: str):
    _run_git("checkout", "master", "-f", cwd=REPO_ROOT)
    branch_name = f"fault-{service_name}-{fault_class}-{uuid_value}"

    res = glob.glob(str(CURRENT_DIR / "fault-vault" / f"fault-{service_name}-{fault_class}-*/FAULT.md"))
    content = "Here are the faults that already exist, try to create a new fault that is different from the ones that already exist:\n"
    for r in res:
        content += f"FAULT: {Path(r).parent.name}\n"
        content += Path(r).read_text()
        content += "\n"
    return {
        "messages": [
            {
                "role": "user",
                "content": (
                    f"You are a fault-injector for the {service_name} service. "
                    f"You are tasked with introducing a fault into the codebase. "
                    f"The fault class is {fault_class}. The fault is {FAULT_CLASS_DESCRIPTIONS[fault_class]}. \n"
                    f"{content}"
                )
            }
        ],
        "branch_name": branch_name,
    }


@node
async def check_fault_injector(cwd: str, messages: list[dict]):
    # check if FAULT.md exists, and there are no uncommitted changes (in the worktree)
    feedback = ""
    cwd = Path(cwd)
    if not (cwd / "FAULT.md").exists():
        feedback += "FAULT.md does not exist\n"
    if not (cwd / "INCIDENT.md").exists():
        feedback += "INCIDENT.md does not exist\n"
    r = _run_git("status", "--porcelain", cwd=cwd)
    changes = [
        line.replace("?? ", "")
        for line in r.stdout.splitlines()
        if not line.strip().endswith(".md")
    ]
    print("CHANGES: ", changes)
    if not (r.returncode != 0 or changes):
        print("no changes to commit")
        feedback += f"There are no changes to commit besides {' and '.join(changes)}\n"
    if feedback:
        print("FEEDBACK: ", feedback)
        messages.append({
            "role": "user",
            "content": feedback
        })
        return {"messages": messages}, "reflect"


@node
async def end_fault_injector(branch_name: str, cwd: str):
    worktree_root = Path(cwd)
    patch_out_path = CURRENT_DIR / "fault-vault" / branch_name / "git.patch"
    patch_out_path.parent.mkdir(parents=True, exist_ok=True)
    fault_vault_dir = CURRENT_DIR / "fault-vault" / branch_name
    fault_vault_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(worktree_root / "FAULT.md", fault_vault_dir / "FAULT.md")
    shutil.copy(worktree_root / "INCIDENT.md", fault_vault_dir / "INCIDENT.md")
    os.remove(worktree_root / "FAULT.md")
    os.remove(worktree_root / "INCIDENT.md")
    git_commit_and_format_patch(branch_name, patch_out_path, repo_root=worktree_root)
    delete_result = await work_tree_service.delete_worktree(
        cwd=str(REPO_ROOT),
        worktree_path=cwd,
        force=True,
    )
    if not delete_result.success:
        raise RuntimeError(f"Failed to remove worktree: {delete_result.message}")


@node(batch=True)
async def batch_inject_fault(fault_id: str, service_name: str, fault_class: int):
    """Batch node: for each (service_name, fault_class) create a worktree, run the agent, and store the fault."""
    uuid_value = str(uuid.uuid4())
    branch_name = f"fault-{fault_id}-{service_name}-{fault_class}-{uuid_value}"
    worktree_path = WORKTREES_DIR / branch_name
    agent = await create_agent(REPO_ROOT, worktree_path, branch_name)
    shared_state = {
        "cwd": str(worktree_path),
        "fault_id": fault_id,
        "service_name": service_name,
        "fault_class": fault_class,
        "uuid_value": uuid_value,
    }
    print(
        f"[BATCH] Injecting fault {fault_id} into {service_name} "
        f"with UUID {shared_state['uuid_value']}"
    )
    await agent.call(shared_state)
    print(f"[BATCH] Fault injection complete for {service_name}, class {fault_class}")
    return {"fault_id": fault_id, "service_name": service_name, "fault_class": fault_class}


@trace_flow(flow_name="single-fault-generator-execution-flow")
class _TracedFlow(AsyncFlow):
    def __init__(self, start):
        super().__init__(start=start)


# Flow wiring: create_batch >> batch_inject_fault
create_batch >> batch_inject_fault
fault_batch_flow = _TracedFlow(start=create_batch)


async def main():
    for select_service in APP_SERVICES:
        for fault_id in [2, 3, 4]:
            uuid_value = str(uuid.uuid4())
            branch_name = f"fault-{fault_id}-{select_service}-{uuid_value}"
            worktree_path = WORKTREES_DIR / branch_name
            agent = await create_agent(REPO_ROOT, worktree_path, branch_name)
            shared_state = {
                "cwd": str(worktree_path),
                "service_name": select_service,
                "fault_class": fault_id,
                "uuid_value": uuid_value,
            }
            print(f"Injecting fault {fault_id} into {select_service} with UUID {shared_state['uuid_value']}")
            SESSION_ID = str(uuid.uuid4())

            with tracer.start_as_current_span("single-fault-generator-execution-flow-session-" + SESSION_ID):
                with using_attributes(session_id=SESSION_ID):
                    await agent.call(shared_state)

            print(f"Fault injection complete for {select_service}, fault_id {fault_id}")
    return

if __name__ == "__main__":
    asyncio.run(main())
