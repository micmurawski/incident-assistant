import base64
from typing import Annotated, Optional

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import ToolResult, Tools, tool


async def _run_kubectl(args: list[str], stdin: Optional[str] = None, timeout: int = 60) -> ToolResult:
    """Run kubectl; if stdin is provided, use it as -f - for apply/create."""
    cmd = ["kubectl"] + args
    return await run_cli_command(cmd, stdin, timeout)


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


# ---------------------------------------------------------------------------
# List / delete chaos experiments
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "observability"])
async def chaos_list_experiments(
    namespace: Annotated[
        Optional[str],
        "Namespace to list chaos experiments in. Omit for all namespaces.",
    ] = None,
) -> ToolResult:
    """
    List all Chaos Mesh experiments (PodChaos, NetworkChaos, StressChaos, IOChaos, HTTPChaos)
    in the cluster. Use to see active chaos before adding more or to find experiment names to delete.
    """
    resources = "podchaos,networkchaos,stresschaos,iochaos,httpchaos"
    if namespace:
        args = ["get", resources, "-n", namespace, "-o", "wide"]
    else:
        args = ["get", resources, "-A", "-o", "wide"]
    return await _run_kubectl(args)


@tool(tags=["chaos", "cleanup"])
async def chaos_delete_experiment(
    name: Annotated[str, "Name of the chaos experiment"],
    kind: Annotated[
        str,
        "Kind of resource: PodChaos, NetworkChaos, StressChaos, IOChaos, or HTTPChaos",
    ],
    namespace: Annotated[str, "Namespace where the experiment was created"],
) -> ToolResult:
    """
    Delete a Chaos Mesh experiment by name and kind. Use after listing with chaos_list_experiments.
    """
    # Map Kind to kubectl resource name (lowercase)
    kind_lower = kind.lower().strip()
    if not kind_lower.endswith("chaos"):
        kind_lower = kind_lower + "chaos"
    return await _run_kubectl(["delete", kind_lower, name, "-n", namespace])


# ---------------------------------------------------------------------------
# Pod chaos (PodChaos)
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "pod"])
async def chaos_pod_kill(
    namespace: Annotated[str, "Namespace containing the target pods"],
    label_selector: Annotated[
        str,
        "Label selector for target pods, e.g. 'app=web' or 'app.kubernetes.io/name=api'",
    ] = "app=web",
    mode: Annotated[
        str,
        "Mode: 'one' (one pod), 'all' (all matching pods), or 'fixed' (fixed number)",
    ] = "one",
    fixed_replicas: Annotated[
        Optional[int],
        "When mode is 'fixed', number of pods to kill",
    ] = None,
    duration: Annotated[
        Optional[str],
        "How long the chaos runs (e.g. '30s', '5m'). Omit for one-shot kill.",
    ] = None,
    experiment_name: Annotated[
        Optional[str],
        "Unique name for this experiment (default: chaos-pod-kill-<namespace>)",
    ] = None,
) -> ToolResult:
    """
    Kill one or more pods matching a label selector (Chaos Mesh PodChaos pod-kill).
    Useful to test restart policies and failover. Use mode 'one' to affect a single pod.
    """
    name = experiment_name or f"chaos-pod-kill-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  action: pod-kill
  mode: {mode}
{_selector_yaml(namespace, label_selector)}"""
    if fixed_replicas is not None and mode == "fixed":
        spec += f"  value: \"{fixed_replicas}\"\n"
    if duration:
        spec += f"  duration: \"{duration}\"\n"
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "pod"])
async def chaos_pod_failure(
    namespace: Annotated[str, "Namespace containing the target pods"],
    label_selector: Annotated[
        str,
        "Label selector for target pods, e.g. 'app=backend'",
    ] = "app=backend",
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long the pod is failed (e.g. '30s', '2m')"] = "30s",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Simulate pod failure for a duration (Chaos Mesh PodChaos pod-failure). The pod will be
    unavailable and then recover; use to test detection and recovery.
    """
    name = experiment_name or f"chaos-pod-failure-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  action: pod-failure
  mode: {mode}
{_selector_yaml(namespace, label_selector)}
  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


# ---------------------------------------------------------------------------
# Network chaos (NetworkChaos)
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "network"])
async def chaos_network_delay(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods, e.g. 'app=frontend'"] = "app=frontend",
    latency: Annotated[str, "Delay to add (e.g. '100ms', '500ms', '2s')"] = "200ms",
    jitter: Annotated[str, "Optional jitter (e.g. '0ms', '50ms')"] = "0ms",
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to apply delay (e.g. '2m', '5m')"] = "2m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Add network latency to pods matching the selector (Chaos Mesh NetworkChaos delay).
    Use to simulate slow or distant backends and test timeouts/retries.
    """
    name = experiment_name or f"chaos-network-delay-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {name}
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
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "network"])
async def chaos_network_loss(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods"] = "app=frontend",
    loss_percent: Annotated[int, "Percentage of packets to drop (0-100)"] = 10,
    correlation: Annotated[str, "Correlation percentage for loss (e.g. '100')"] = "100",
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to apply loss (e.g. '1m', '3m')"] = "1m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Drop a percentage of network packets (Chaos Mesh NetworkChaos loss). Use to test
    resilience to packet loss and retries.
    """
    name = experiment_name or f"chaos-network-loss-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  action: loss
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  loss:
    loss: "{loss_percent}"
    correlation: "{correlation}"
  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "network"])
async def chaos_network_partition(
    namespace: Annotated[str, "Namespace of source and target"],
    source_selector: Annotated[
        str,
        "Label selector for source pods (e.g. 'app=backend')",
    ] = "app=backend",
    target_selector: Annotated[
        str,
        "Label selector for target pods (e.g. 'app=database')",
    ] = "app=database",
    direction: Annotated[
        str,
        "Direction: 'to' (source cannot reach target), 'from', or 'both'",
    ] = "to",
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed' for source/target"] = "all",
    duration: Annotated[str, "How long the partition lasts (e.g. '3m')"] = "3m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Partition network between two groups of pods (Chaos Mesh NetworkChaos partition).
    E.g. isolate backend from database to test failure handling and circuit breakers.
    """
    name = experiment_name or f"chaos-network-partition-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  action: partition
  mode: {mode}
{_selector_yaml(namespace, source_selector)}  direction: {direction}
{_target_selector_yaml(namespace, target_selector, mode)}  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "network"])
async def chaos_network_bandwidth(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods"] = "app=frontend",
    rate: Annotated[str, "Bandwidth limit, e.g. '1mbps', '100kbps'"] = "1mbps",
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to apply limit (e.g. '2m')"] = "2m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Limit egress bandwidth for matching pods (Chaos Mesh NetworkChaos bandwidth).
    Use to simulate slow links or rate limiting.
    """
    name = experiment_name or f"chaos-network-bandwidth-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  action: bandwidth
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  bandwidth:
    rate: "{rate}"
  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


# ---------------------------------------------------------------------------
# Stress chaos (StressChaos)
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "stress"])
async def chaos_cpu_stress(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods, e.g. 'app=backend'"] = "app=backend",
    workers: Annotated[int, "Number of CPU stress workers"] = 1,
    load: Annotated[int, "CPU load percentage per worker (e.g. 80, 100)"] = 100,
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to stress (e.g. '5m')"] = "5m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Stress CPU on matching pods (Chaos Mesh StressChaos). Use to test behavior under
    high CPU and resource limits.
    """
    name = experiment_name or f"chaos-cpu-stress-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  stressors:
    cpu:
      workers: {workers}
      load: {load}
  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "stress"])
async def chaos_memory_stress(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods, e.g. 'app=backend'"] = "app=backend",
    size: Annotated[str, "Memory to consume per worker (e.g. '128MB', '256MB')"] = "128MB",
    workers: Annotated[int, "Number of memory stress workers"] = 1,
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to stress (e.g. '3m')"] = "3m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Consume memory on matching pods (Chaos Mesh StressChaos). Use to test OOM behavior
    and memory limits.
    """
    name = experiment_name or f"chaos-memory-stress-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  stressors:
    memory:
      workers: {workers}
      size: "{size}"
  duration: "{duration}"
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


# ---------------------------------------------------------------------------
# I/O chaos (IOChaos)
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "io"])
async def chaos_io_latency(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods, e.g. 'app=database'"] = "app=database",
    volume_path: Annotated[str, "Volume path to inject latency (e.g. /data/db)"] = "/data",
    delay: Annotated[str, "I/O delay to add (e.g. '50ms', '100ms')"] = "100ms",
    percent: Annotated[int, "Percentage of I/O operations to delay (0-100)"] = 100,
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to apply (e.g. '5m')"] = "5m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Add latency to disk I/O on matching pods (Chaos Mesh IOChaos). Use to simulate
    slow storage or congested disks. Requires volumePath to be a mounted volume.
    """
    name = experiment_name or f"chaos-io-latency-{namespace}"
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
metadata:
  name: {name}
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
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


# ---------------------------------------------------------------------------
# HTTP chaos (HTTPChaos) — optional, for service-level faults
# ---------------------------------------------------------------------------


@tool(tags=["chaos", "http"])
async def chaos_http_abort(
    namespace: Annotated[str, "Namespace of target pods"],
    label_selector: Annotated[str, "Label selector for target pods"] = "app=web",
    port: Annotated[int, "Target port number"] = 8080,
    code: Annotated[int, "HTTP status code to return (e.g. 500, 503)"] = 500,
    mode: Annotated[str, "Mode: 'one', 'all', or 'fixed'"] = "one",
    duration: Annotated[str, "How long to abort (e.g. '1m')"] = "1m",
    experiment_name: Annotated[Optional[str], "Unique name for this experiment"] = None,
) -> ToolResult:
    """
    Abort HTTP requests with a given status code (Chaos Mesh HTTPChaos). Use to
    simulate service errors (5xx) or maintenance (503). Injects connection abort on the target port.
    """
    name = experiment_name or f"chaos-http-abort-{namespace}"
    # replace.body is []byte in the CRD; webhook decodes base64.
    _body_b64 = base64.b64encode(b"Service is currently unavailable").decode("ascii")
    spec = f"""apiVersion: chaos-mesh.org/v1alpha1
kind: HTTPChaos
metadata:
  name: {name}
  namespace: {namespace}
spec:
  mode: {mode}
{_selector_yaml(namespace, label_selector)}  target: Response
  port: {port}
  duration: "{duration}"
  replace:
    code: {code}
    body: {_body_b64}
"""
    return await _run_kubectl(["apply", "-f", "-"], stdin=spec.strip(), timeout=30)


@tool(tags=["chaos", "cleanup"])
async def chaos_delete_all_experiments() -> ToolResult:
    """
    Delete all Chaos Mesh experiments in the cluster. Use to clean up after testing.
    """
    resources = "podchaos,networkchaos,stresschaos,iochaos,httpchaos"
    return await _run_kubectl(["delete", resources, "--all", "-A"])

ChaosTools = Tools(
    tools=[
        chaos_list_experiments,
        chaos_delete_experiment,
        chaos_delete_all_experiments,
        chaos_pod_kill,
        chaos_pod_failure,
        chaos_network_delay,
        chaos_network_loss,
        chaos_network_partition,
        chaos_network_bandwidth,
        chaos_cpu_stress,
        chaos_memory_stress,
        chaos_io_latency,
        chaos_http_abort,
    ]
)
