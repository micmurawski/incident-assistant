import asyncio
import glob
import os
import random
import shutil
import subprocess
import uuid
from itertools import product
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
from agent.worktree import WorkTreeService

os.environ["PHOENIX_CLIENT_HEADERS"] = "Authorization=Bearer YOUR_API_KEY"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"

tracer_provider = register(project_name="fault-generator-1-tracing")

REPO_ROOT = Path("/Users/micmur/GITHUB/o8s/services/robot-shop")
LOAD_GEN_SCRIPT = REPO_ROOT / "load-gen" / "robot-shop.py"
WORKTREES_DIR = REPO_ROOT.parent / "robot-shop-worktrees"
CURRENT_DIR = Path(__file__).resolve().parent

# Get a tracer for your application
tracer = trace.get_tracer(__name__)

tracer_provider = register(
    auto_instrument=True
)

work_tree_service = WorkTreeService()


@trace_flow(flow_name="single-fault-generator-execution-flow")
class _TracedFlow(AsyncFlow):
    def __init__(self, start):
        super().__init__(start=start)


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


PROMPT_TEMPLATE = """
We are running chaos engineering experiments your role is to create changes in codebase that will create incident for this microservice. We will be running the following Chaos Mesh experiment for app {service}:
{manifest_yaml}
Your job is to apply changes apply changes in the codebase or/and to the deployment manifest to increase likelihood of incident for this microservice or app overall. Take your time and analyze the codebase and relationships between services. In DOC.md you will find some details about the app.
Make sure that your changes are not obvious and will not be detected by static analysis, do not use names or comments hinting for the fault, make it as subtle as possible. 
In k8s/manifests - you will find deployment manifests for this microservices.
in other folders - you will find other files that might be relevant to the codebase.
for example:
- in k8s/manifests/payment.yaml - you will find deployment manifest for the payment microservice.
- in payment/* - you will find the code for the payment microservice.

The service will be under the following load:
{load_gen_script}

You must:

1. Apply changes in the codebase to increase likely hood and damage for this microservice overall. Take your time and analyze the codebase and relationships between services. In DOC.md you will find some details about the app.
Make sure that your changes are not obvious and will not be detected by static analysis, do not use names or comments hinting for the fault, make it as subtle as possible. 

2. **Write FAULT.md** at `FAULT.md` with this structure:
   - **Title**: One line describing the fault.
   - **Description**: What was changed and where.
   - **Symptom**: What users or monitoring will see.
   - **Root cause**: Why this causes the symptom.
   - **Fix**: How to fix it (revert, correct config, etc.) - Let's assume that we are not able to disable the experiment, so we need to fix the problem.

3. **Write INCIDENT.md** at `INCIDENT.md` with this structure:
    - **Title**: One line describing the incident.
    - **Description**: What happened. How it's observed by the user, what is metrics are affected, be brief to not disclose too much details.
    - This message will be used to announce the incident to a team. You CANNOT give any information about the fault or the fix.
"""


def _selector_yaml(namespace: str, label_selector: str) -> str:
    """Build Chaos Mesh selector block: namespaces + optional labelSelectors (supports 'app=web' or 'app=web,tier=frontend')."""
    out = f"""  selector:
    namespaces:
      - {namespace}
"""
    if label_selector.strip():
        pairs = [p.strip().split("=", 1) for p in label_selector.split(",") if "=" in p]
        if pairs:
            out += "    labelSelectors:\n"
            for k, v in pairs:
                out += f"      {k.strip()}: {v.strip()}\n"
    return out


def _target_selector_yaml(namespace: str, label_selector: str, mode: str) -> str:
    """Build Chaos Mesh target block for partition (selector + mode)."""
    out = f"""  target:
    selector:
      namespaces:
        - {namespace}
"""
    if label_selector.strip():
        pairs = [p.strip().split("=", 1) for p in label_selector.split(",") if "=" in p]
        if pairs:
            out += "      labelSelectors:\n"
            for k, v in pairs:
                out += f"        {k.strip()}: {v.strip()}\n"
    out += f"    mode: {mode}\n"
    return out


def chaos_pod_failure(
    *,
    namespace: str,
    label_selector: str,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: chaos-pod-failure-{namespace}
  namespace: {namespace}
spec:
  action: pod-failure
  mode: {mode}
{_selector_yaml(namespace, label_selector)}
  duration: "{duration}"
"""


def chaos_pod_kill(
    *,
    namespace: str,
    label_selector: str,
    mode: str,
    duration: str | None = None,
    fixed_replicas: int | None = None,
) -> str:
    yaml_manifest = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: chaos-pod-kill-{namespace}
  namespace: {namespace}
spec:
  action: pod-kill
  mode: {mode}
{_selector_yaml(namespace, label_selector)}"""
    if fixed_replicas is not None and mode == "fixed":
        yaml_manifest += f'  value: "{fixed_replicas}"\n'
    if duration is not None:
        yaml_manifest += f'  duration: "{duration}"\n'
    return yaml_manifest


def chaos_network_delay(
    *,
    namespace: str,
    label_selector: str,
    latency: str,
    jitter: str,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: chaos-network-delay-{namespace}
  namespace: {namespace}
spec:
  action: delay
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  delay:
    latency: "{latency}"
    correlation: "100"
    jitter: "{jitter}"
  duration: "{duration}"
"""


def chaos_network_loss(
    *,
    namespace: str,
    label_selector: str,
    loss_percent: int,
    mode: str,
    duration: str,
    correlation: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: chaos-network-loss-{namespace}
  namespace: {namespace}
spec:
  action: loss
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  loss:
    loss: "{loss_percent}"
    correlation: "{correlation}"
  duration: "{duration}"
"""


def chaos_network_partition(
    *,
    namespace: str,
    label_selector: str,
    direction: str,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: chaos-network-partition-{namespace}
  namespace: {namespace}
spec:
  action: partition
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  direction: {direction}
{_target_selector_yaml(namespace, label_selector, mode)}  duration: "{duration}"
"""


def chaos_network_bandwidth(
    *,
    namespace: str,
    label_selector: str,
    rate: str,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: chaos-network-bandwidth-{namespace}
  namespace: {namespace}
spec:
  action: bandwidth
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  bandwidth:
    rate: "{rate}"
  duration: "{duration}"
"""


def chaos_cpu_stress(
    *,
    namespace: str,
    label_selector: str,
    workers: int,
    load: int,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: chaos-cpu-stress-{namespace}
  namespace: {namespace}
spec:
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  stressors:
    cpu:
      workers: {workers}
      load: {load}
  duration: "{duration}"
"""


def chaos_memory_stress(
    *,
    namespace: str,
    label_selector: str,
    size: str,
    workers: int,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: chaos-memory-stress-{namespace}
  namespace: {namespace}
spec:
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  stressors:
    memory:
      workers: {workers}
      size: "{size}"
  duration: "{duration}"
"""


def chaos_io_latency(
    *,
    namespace: str,
    label_selector: str,
    volume_path: str,
    delay: str,
    percent: int,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: chaos-io-latency-{namespace}
  namespace: {namespace}
spec:
  action: latency
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  volumePath: "{volume_path}"
  path: ""
  delay: "{delay}"
  percent: {percent}
  duration: "{duration}"
"""


def chaos_http_abort(
    *,
    namespace: str,
    label_selector: str,
    port: int,
    code: int,
    mode: str,
    duration: str,
) -> str:
    return f"""apiVersion: chaos-mesh.org/v1alpha1
kind: HTTPChaos
metadata:
  name: chaos-http-abort-{namespace}
  namespace: {namespace}
spec:
  action: abort
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  port: {port}
  duration: "{duration}"
  replace:
    code: {code}
    body: "Service is currently unavailable"
"""


CHAOS_TEMPLATES = [
    {
        "method": chaos_pod_failure,
        "params": {
            "duration": ["60m"],
            "mode": ["one"],
        },
        "description": "Simulate pod failure for a duration.",
    },
    {
        "method": chaos_pod_kill,
        "params": {
            "mode": ["one"],
            "duration": ["60m"],
        },
        "description": "Kill one or more pods to test restart and failover.",
    },
    {
        "method": chaos_network_delay,
        "params": {
            "mode": ["one"],
            "latency": ["100ms", "200ms", "500ms"],
            "jitter": ["0ms", "50ms"],
            "duration": ["10m", "15m"],
        },
        "description": "Add network latency to pods.",
    },
    {
        "method": chaos_network_loss,
        "params": {
            "loss_percent": [10, 25, 50],
            "mode": ["one"],
            "duration": ["60m"],
            "correlation": ["25", "50"],
        },
        "description": "Drop a percentage of network packets.",
    },
    {
        "method": chaos_network_partition,
        "params": {
            "direction": ["to", "from", "both"],
            "mode": ["one"],
            "duration": ["60m"],
        },
        "description": "Partition traffic between two groups of pods.",
    },
    {
        "method": chaos_network_bandwidth,
        "params": {
            "rate": ["1mbps", "500kbps"],
            "mode": ["one"],
            "duration": ["60m"],
        },
        "description": "Limit egress bandwidth for matching pods.",
    },
    {
        "method": chaos_cpu_stress,
        "params": {
            "mode": ["one"],
            "load": [15, 25, 50],
            "workers": [1],
            "duration": ["60m"],
        },
        "description": "Stress CPU on matching pods.",
    },
    {
        "method": chaos_memory_stress,
        "params": {
            "size": ["128MB", "256MB", "512MB"],
            "duration": ["60m"],
            "mode": ["one"],
            "workers": [1],
        },
        "description": "Consume memory on matching pods.",
    },
    {
        "method": chaos_io_latency,
        "params": {
            "volume_path": ["/data", "/var/lib/mysql"],
            "delay": ["200ms", "300ms", "500ms"],
            "percent": [50, 100],
            "mode": ["one"],
            "duration": ["60m"],
        },
        "description": "Inject latency into disk I/O on matching pods.",
    },
    {
        "method": chaos_http_abort,
        "params": {
            "port": [80, 8080],
            "code": [500, 503],
            "mode": ["one"],
            "duration": ["5m", "10m", "15m"],
        },
        "description": "Abort HTTP requests with a given status code.",
    },
]


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


async def create_agent(repo_root: Path, work_tree_path: Path, branch_name: str, system_prompt: str):
    result = await work_tree_service.create_worktree(
        cwd=str(repo_root),
        path=str(work_tree_path),
        branch=branch_name,
        base_branch="master",
        create_new_branch=True,
    )
    if not result.success:
        raise RuntimeError(f"Failed to create worktree: {result.message}")
    agent = FaultInjector(name=branch_name, cwd=work_tree_path, system_prompt=system_prompt)

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
PROVIDER = "minimax"

if PROVIDER == "minimax":
    AnthropicInstrumentor().instrument(tracer_provider=tracer_provider)
elif PROVIDER == "gemini":
    from openinference.instrumentation.google_genai import \
        GoogleGenAIInstrumentor
    GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
else:
    raise ValueError(f"Unknown provider: {PROVIDER}")

settings.set("api.provider", "minimax")
settings.set("api.model_id", "MiniMax-M2.5")
settings.set("api.api_key", MINIMAX_API_KEY)
# Override Minimax API endpoint (passed to MiniMaxHandler as base_url)
# settings.set("api.provider", "gemini")
# settings.set("api.model_id", "gemini-3.1-pro-preview:thinking")
# settings.set("api.api_key", GEMINI_API_KEY)


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
async def start_fault_injector(service_name: str, branch_name: str):
    _run_git("checkout", "master", "-f", cwd=REPO_ROOT)
    branch_name_wildcard = branch_name.rsplit("-", 1)[0]+"-*"
    res = glob.glob(str(CURRENT_DIR / "fault-vault" / branch_name_wildcard / "FAULT.md"))
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
                    f"{content}"
                )
            }
        ],
        "branch_name": branch_name,
    }


@node
async def check_fault_injector(cwd: str, messages: list[dict]):
    print("CHECKING FAULT INJECTOR")
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
async def end_fault_injector(branch_name: str, cwd: str, manifest_yaml: str):
    print("ENDING FAULT INJECTOR")
    worktree_root = Path(cwd)
    patch_out_path = CURRENT_DIR / "fault-vault" / branch_name / "git.patch"
    patch_out_path.parent.mkdir(parents=True, exist_ok=True)
    fault_vault_dir = CURRENT_DIR / "fault-vault" / branch_name
    fault_vault_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(worktree_root / "FAULT.md", fault_vault_dir / "FAULT.md")
    shutil.copy(worktree_root / "INCIDENT.md", fault_vault_dir / "INCIDENT.md")
    with open(fault_vault_dir / "experiment.yaml", "w") as f:
        f.write(manifest_yaml)
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


async def main():
    fault_id = 1
    selected_services = random.sample(SERVICES, 1)
    selected_chaos_templates = random.sample(CHAOS_TEMPLATES, 1)
    for select_service in selected_services:
        for chaos_template in selected_chaos_templates:
            param_names = list(chaos_template["params"].keys())
            param_values = [chaos_template["params"][name] for name in param_names]
            all_combos = list(product(*param_values))
            random.shuffle(all_combos)
            all_combos_sample = random.sample(all_combos, 1)

            for combo in all_combos_sample:
                combo_kwargs = dict(zip(param_names, combo))
                select_service_label = f"app={select_service}"
                manifest_yaml = chaos_template["method"](
                    namespace=NAMESPACE,
                    label_selector=select_service_label,
                    **combo_kwargs,
                )
                print("MANIFEST_YAML: ")
                print(manifest_yaml)
                print("--------------------------------")
                system_prompt = PROMPT_TEMPLATE.format(service=select_service, manifest_yaml=manifest_yaml)
                uuid_value = uuid.uuid4().hex
                branch_name = (
                    f"fault-{fault_id}-"
                    f"{select_service}-"
                    f"{chaos_template['method'].__name__}-"
                    f"{uuid_value}"
                )
                worktree_path = WORKTREES_DIR / branch_name
                agent = await create_agent(REPO_ROOT, worktree_path, branch_name, system_prompt)
                shared_state = {
                    "cwd": str(worktree_path),
                    "service_name": select_service,
                    "fault_class": fault_id,
                    "uuid_value": uuid_value,
                    "manifest_yaml": manifest_yaml,
                    "branch_name": branch_name,
                }
                print(f"Injecting fault {fault_id} into {select_service} with UUID {shared_state['uuid_value']}")
                SESSION_ID = str(uuid.uuid4())
                with tracer.start_as_current_span("single-fault-generator-execution-flow-session-" + SESSION_ID):
                    with using_attributes(session_id=SESSION_ID):
                        await agent.call(shared_state)
                print(f"Fault injection complete for {select_service}, fault_id {fault_id}")


if __name__ == "__main__":
    asyncio.run(main())
