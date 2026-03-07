import asyncio
import shlex
from typing import Annotated, Optional

from agent.tooling._utils import run_cli_command
from agent.tooling.decorators import ToolResult, Tools, tool


def _run_kubectl(args: list[str], timeout: int = 30) -> ToolResult:
    return run_cli_command(["kubectl"] + args, None, timeout)


# ---------------------------------------------------------------------------
# Cluster & Node health
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "cluster"])
async def kubectl_cluster_info() -> ToolResult:
    """
    Get high-level Kubernetes cluster information including the control plane address and CoreDNS.
    Use this first to verify cluster connectivity before running other kubectl commands.
    """
    return await _run_kubectl(["cluster-info"])


@tool(tags=["kubectl", "cluster"])
async def kubectl_get_nodes(
    show_labels: Annotated[bool, "Include node labels in the output"] = False,
) -> ToolResult:
    """
    List all cluster nodes with status, roles, age, version, and resource capacity.
    Essential for checking node health, readiness, and available resources.
    """
    args = ["get", "nodes", "-o", "wide"]
    if show_labels:
        args.append("--show-labels")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "cluster"])
async def kubectl_top_nodes() -> ToolResult:
    """
    Show CPU and memory usage for every node (requires metrics-server).
    Use to identify resource-constrained or overloaded nodes.
    """
    return await _run_kubectl(["top", "nodes"])


# ---------------------------------------------------------------------------
# Namespace
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "namespace"])
async def kubectl_get_namespaces() -> ToolResult:
    """
    List all namespaces in the cluster with their status and age.
    Use to discover which namespaces exist before querying workloads.
    """
    return await _run_kubectl(["get", "namespaces"])


# ---------------------------------------------------------------------------
# Pod observability
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "pods"])
async def kubectl_get_pods(
    namespace: Annotated[Optional[str], "Namespace to query. Omit or pass null for all namespaces."] = None,
    label_selector: Annotated[Optional[str],
                              "Label selector filter, e.g. 'app=web' or 'tier in (frontend,backend)'"] = None,
    field_selector: Annotated[Optional[str],
                              "Field selector filter, e.g. 'status.phase=Failed' or 'status.phase!=Running'"] = None,
    sort_by: Annotated[Optional[str],
                       "JSONPath to sort by, e.g. '.status.startTime' or '.metadata.creationTimestamp'"] = None,
) -> ToolResult:
    """
    List pods with status, restarts, age, node, and IP.
    Start here when investigating workload issues — high restart counts or non-Running phases signal problems.

    Common field selectors for observability:
    - 'status.phase=Pending'   — pods stuck scheduling
    - 'status.phase=Failed'    — failed pods
    - 'status.phase!=Running'  — all unhealthy pods
    """
    args = ["get", "pods", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    if label_selector:
        args += ["-l", label_selector]
    if field_selector:
        args += ["--field-selector", field_selector]
    if sort_by:
        args += ["--sort-by", sort_by]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "pods"])
async def kubectl_get_pod_logs(
    pod_name: Annotated[str, "Name of the pod"],
    namespace: Annotated[str, "Namespace of the pod"],
    container: Annotated[Optional[str], "Container name (required for multi-container pods)"] = None,
    tail_lines: Annotated[int, "Number of most recent log lines to return"] = 200,
    previous: Annotated[bool, "Get logs from the previous (crashed) container instance"] = False,
    since: Annotated[Optional[str], "Only return logs newer than this duration, e.g. '1h', '30m', '5s'"] = None,
) -> ToolResult:
    """
    Retrieve container logs from a pod.

    - Use `tail_lines` to limit output and focus on recent activity.
    - Set `previous=true` to inspect logs of a container that has crashed and restarted.
    - Use `since` to scope logs to a time window (e.g. '10m' for the last 10 minutes).
    """
    args = ["logs", pod_name, "-n", namespace, f"--tail={tail_lines}"]
    if container:
        args += ["-c", container]
    if previous:
        args.append("--previous")
    if since:
        args += [f"--since={since}"]
    return await _run_kubectl(args, timeout=60)


@tool(tags=["kubectl", "pods"])
async def kubectl_top_pods(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
    sort_by: Annotated[Optional[str], "'cpu' or 'memory' to sort results"] = None,
) -> ToolResult:
    """
    Show CPU and memory usage per pod (requires metrics-server).
    Use to find resource-hungry pods or detect memory leaks.
    """
    args = ["top", "pods"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    if sort_by:
        args += ["--sort-by", sort_by]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "pods"])
async def kubectl_get_pod_containers(
    pod_name: Annotated[str, "Name of the pod"],
    namespace: Annotated[str, "Namespace of the pod"],
) -> ToolResult:
    """
    Show detailed container status for a specific pod including init containers,
    ready/started states, restart counts, last termination reason, and image versions.
    Useful for diagnosing CrashLoopBackOff, ImagePullBackOff, and readiness probe failures.
    """
    args = [
        "get", "pod", pod_name, "-n", namespace,
        "-o", "jsonpath="
        '{range .status.containerStatuses[*]}'
        '{"container: "}{.name}{"\\n"}'
        '{"  ready: "}{.ready}{"\\n"}'
        '{"  restartCount: "}{.restartCount}{"\\n"}'
        '{"  state: "}{.state}{"\\n"}'
        '{"  lastState: "}{.lastState}{"\\n"}'
        '{"  image: "}{.image}{"\\n\\n"}'
        '{end}'
        '{range .status.initContainerStatuses[*]}'
        '{"init-container: "}{.name}{"\\n"}'
        '{"  ready: "}{.ready}{"\\n"}'
        '{"  state: "}{.state}{"\\n"}'
        '{"  image: "}{.image}{"\\n\\n"}'
        '{end}'
    ]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Events (critical for observability)
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "events"])
async def kubectl_get_events(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
    event_type: Annotated[Optional[str], "'Warning' or 'Normal' to filter event type"] = None,
    resource_name: Annotated[Optional[str], "Filter events for a specific resource, e.g. 'pod/my-pod'"] = None,
    sort_by_time: Annotated[bool, "Sort events by last timestamp (most recent last)"] = True,
) -> ToolResult:
    """
    List Kubernetes events sorted by time.
    Events are the first place to look when diagnosing scheduling failures, probe failures,
    image pull errors, OOMKills, volume mount issues, and other cluster problems.

    Filter by type='Warning' to focus only on problems.
    """
    args = ["get", "events"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    if event_type:
        args += ["--field-selector", f"type={event_type}"]
    if resource_name:
        args += ["--field-selector", f"involvedObject.name={resource_name}"]
    if sort_by_time:
        args += ["--sort-by", ".lastTimestamp"]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Workload status
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "workloads"])
async def kubectl_get_deployments(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List deployments with desired/ready/up-to-date/available replica counts.
    A mismatch between desired and available replicas signals a rollout issue.
    """
    args = ["get", "deployments", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "workloads"])
async def kubectl_get_statefulsets(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List StatefulSets with ready/desired replica counts.
    Important for stateful services like databases, message brokers, and caches.
    """
    args = ["get", "statefulsets", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "workloads"])
async def kubectl_get_daemonsets(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List DaemonSets with desired/current/ready counts.
    DaemonSets run on every node — a mismatch means some nodes are missing the workload
    (common for logging agents, monitoring exporters, and network plugins).
    """
    args = ["get", "daemonsets", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "workloads"])
async def kubectl_get_jobs(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
    show_failed: Annotated[bool, "Only show failed jobs"] = False,
) -> ToolResult:
    """
    List Jobs and CronJobs with completions, duration, and status.
    Use to check batch workload health and identify stale or failed jobs.
    """
    args = ["get", "jobs", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    result = await _run_kubectl(args)

    cronjob_args = ["get", "cronjobs", "-o", "wide"]
    if namespace:
        cronjob_args += ["-n", namespace]
    else:
        cronjob_args.append("--all-namespaces")
    cronjob_result = await _run_kubectl(cronjob_args)

    combined = f"=== Jobs ===\n{result.result or ''}\n\n=== CronJobs ===\n{cronjob_result.result or ''}"
    error = result.error or cronjob_result.error
    return ToolResult(result=combined, error=error)


@tool(tags=["kubectl", "workloads"])
async def kubectl_rollout_status(
    resource: Annotated[str, "Resource to check, e.g. 'deployment/my-app' or 'statefulset/my-db'"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Check the rollout status of a deployment or statefulset.
    Shows whether the rollout completed successfully, is in progress, or has stalled.
    """
    args = ["rollout", "status", resource, "-n", namespace, "--timeout=10s"]
    return await _run_kubectl(args, timeout=15)


@tool(tags=["kubectl", "workloads"])
async def kubectl_rollout_history(
    resource: Annotated[str, "Resource to inspect, e.g. 'deployment/my-app'"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Show rollout revision history for a deployment or statefulset.
    Useful for understanding what changed and when, especially after an incident.
    """
    args = ["rollout", "history", resource, "-n", namespace]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "network"])
async def kubectl_get_services(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List services with type, cluster IP, external IP, and ports.
    Use to verify service exposure and port mapping.
    """
    args = ["get", "services", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "network"])
async def kubectl_get_endpoints(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
    service_name: Annotated[Optional[str], "Filter endpoints for a specific service"] = None,
) -> ToolResult:
    """
    List endpoints (pod IPs backing each service).
    Empty endpoints mean the service has no healthy pods — a common cause of 503 errors.
    """
    args = ["get", "endpoints"]
    if service_name:
        args.append(service_name)
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "network"])
async def kubectl_get_ingresses(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List ingress resources with hosts, paths, backends, and addresses.
    Use to verify external routing configuration.
    """
    args = ["get", "ingress", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "network"])
async def kubectl_get_network_policies(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List network policies that control pod-to-pod and external traffic.
    Misconfigured network policies are a frequent cause of connectivity issues between services.
    """
    args = ["get", "networkpolicies", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Describe & inspect (deep-dive)
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "inspect"])
async def kubectl_describe(
    resource_type: Annotated[str, "Resource type, e.g. 'pod', 'deployment', 'node', 'service', 'pvc'"],
    resource_name: Annotated[str, "Name of the resource"],
    namespace: Annotated[Optional[str], "Namespace (omit for cluster-scoped resources like nodes)"] = None,
) -> ToolResult:
    """
    Show detailed information about a specific resource including conditions, events,
    volumes, probes, resource requests/limits, and scheduling decisions.
    This is the primary deep-dive tool for diagnosing why a specific resource is unhealthy.
    """
    args = ["describe", resource_type, resource_name]
    if namespace:
        args += ["-n", namespace]
    return await _run_kubectl(args, timeout=30)


@tool(tags=["kubectl", "inspect"])
async def kubectl_get_yaml(
    resource_type: Annotated[str, "Resource type, e.g. 'pod', 'deployment', 'configmap', 'service'"],
    resource_name: Annotated[str, "Name of the resource"],
    namespace: Annotated[Optional[str], "Namespace (omit for cluster-scoped resources)"] = None,
) -> ToolResult:
    """
    Get the full YAML manifest of a resource.
    Use when you need to inspect the exact spec, annotations, labels,
    environment variables, volume mounts, or other configuration details.
    """
    args = ["get", resource_type, resource_name, "-o", "yaml"]
    if namespace:
        args += ["-n", namespace]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Config & Storage
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "config"])
async def kubectl_get_configmap(
    name: Annotated[str, "Name of the ConfigMap"],
    namespace: Annotated[str, "Namespace of the ConfigMap"],
) -> ToolResult:
    """
    Retrieve a ConfigMap's data contents.
    Use to verify application configuration, feature flags, or connection strings
    that may be causing misbehavior.
    """
    args = ["get", "configmap", name, "-n", namespace, "-o", "jsonpath={.data}"]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "config"])
async def kubectl_get_pvcs(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List PersistentVolumeClaims with status, capacity, access modes, and storage class.
    Pending PVCs block pod scheduling — a common cause of pods stuck in Pending state.
    """
    args = ["get", "pvc", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# RBAC & Security
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "security"])
async def kubectl_auth_can_i(
    verb: Annotated[str, "Action to check, e.g. 'get', 'list', 'create', 'delete', 'watch'"],
    resource: Annotated[str, "Resource to check, e.g. 'pods', 'deployments', 'secrets'"],
    namespace: Annotated[Optional[str], "Namespace scope (omit for cluster-level check)"] = None,
) -> ToolResult:
    """
    Check if the current kubeconfig identity has permission to perform an action.
    Use before running a command to avoid confusing permission errors.
    """
    args = ["auth", "can-i", verb, resource]
    if namespace:
        args += ["-n", namespace]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# HPA & Autoscaling
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "autoscaling"])
async def kubectl_get_hpa(
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
) -> ToolResult:
    """
    List Horizontal Pod Autoscalers with current/target metrics and replica counts.
    Check whether HPAs are scaling correctly or stuck at min/max replicas.
    """
    args = ["get", "hpa", "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Generic resource listing
# ---------------------------------------------------------------------------

@tool(tags=["kubectl"])
async def kubectl_api_resources() -> ToolResult:
    """
    List all available resource types in the cluster (built-in and CRDs).
    Use when you need to discover what resource types are installed,
    e.g. to check for Prometheus, Istio, or cert-manager CRDs.
    """
    return await _run_kubectl(["api-resources", "--sort-by=name"])


@tool(tags=["kubectl"])
async def kubectl_get_resource(
    resource_type: Annotated[str, "Any valid resource type, e.g. 'certificates', 'virtualservices', 'prometheusrules'"],
    namespace: Annotated[Optional[str], "Namespace to query. Omit for all namespaces."] = None,
    label_selector: Annotated[Optional[str], "Label selector filter"] = None,
) -> ToolResult:
    """
    Generic tool to list any Kubernetes resource type (including CRDs).
    Use this as a fallback when no specialized tool exists for the resource type you need.
    """
    args = ["get", resource_type, "-o", "wide"]
    if namespace:
        args += ["-n", namespace]
    else:
        args.append("--all-namespaces")
    if label_selector:
        args += ["-l", label_selector]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Export the collection
# ---------------------------------------------------------------------------

KubectlTools = Tools(tools=[
    # Cluster & Nodes
    kubectl_cluster_info,
    kubectl_get_nodes,
    kubectl_top_nodes,
    # Namespaces
    kubectl_get_namespaces,
    # Pods
    kubectl_get_pods,
    kubectl_get_pod_logs,
    kubectl_top_pods,
    kubectl_get_pod_containers,
    # Events
    kubectl_get_events,
    # Workloads
    kubectl_get_deployments,
    kubectl_get_statefulsets,
    kubectl_get_daemonsets,
    kubectl_get_jobs,
    kubectl_rollout_status,
    kubectl_rollout_history,
    # Networking
    kubectl_get_services,
    kubectl_get_endpoints,
    kubectl_get_ingresses,
    kubectl_get_network_policies,
    # Describe & Inspect
    kubectl_describe,
    kubectl_get_yaml,
    # Config & Storage
    kubectl_get_configmap,
    kubectl_get_pvcs,
    # Security
    kubectl_auth_can_i,
    # Autoscaling
    kubectl_get_hpa,
    # Generic
    kubectl_api_resources,
    kubectl_get_resource,
])


# ===========================================================================
# MUTATING TOOLS — modify cluster state
# ===========================================================================

# ---------------------------------------------------------------------------
# Pod & Container operations
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "pods"])
async def kubectl_delete_pod(
    pod_name: Annotated[str, "Name of the pod to delete"],
    namespace: Annotated[str, "Namespace of the pod"],
    grace_period: Annotated[Optional[int],
                            "Seconds to wait for graceful shutdown. 0 for immediate force-delete."] = None,
) -> ToolResult:
    """
    Delete a pod. Kubernetes will recreate it if managed by a controller (Deployment, StatefulSet, etc.).
    Use to force-restart a misbehaving pod or clear a stuck CrashLoopBackOff.
    Set grace_period=0 for immediate termination of hung pods.
    """
    args = ["delete", "pod", pod_name, "-n", namespace]
    if grace_period is not None:
        args += [f"--grace-period={grace_period}"]
    return await _run_kubectl(args, timeout=120)


@tool(tags=["kubectl", "mutate", "pods"])
async def kubectl_exec(
    pod_name: Annotated[str, "Name of the pod"],
    namespace: Annotated[str, "Namespace of the pod"],
    command: Annotated[str, "Command to run inside the container, e.g. 'cat /etc/config/app.yaml'"],
    container: Annotated[Optional[str], "Container name (required for multi-container pods)"] = None,
) -> ToolResult:
    """
    Execute a command inside a running container.
    Useful for inspecting files, checking connectivity (curl, nslookup, ping),
    reading environment variables, or verifying process state.

    Examples:
    - ['cat', '/etc/resolv.conf']       — check DNS config
    - ['nslookup', 'my-service']        — test service DNS resolution
    - ['env']                           — list environment variables
    - ['ls', '-la', '/app/data']        — inspect mounted volumes
    - ['wget', '-qO-', 'http://localhost:8080/health'] — test health endpoint
    """
    args = ["exec", pod_name, "-n", namespace]
    if container:
        args += ["-c", container]
    args += ["--"] + shlex.split(command.strip())   # split the command into a list of arguments
    return await _run_kubectl(args, timeout=30)


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "scaling"])
async def kubectl_scale(
    resource: Annotated[str, "Resource to scale, e.g. 'deployment/my-app' or 'statefulset/my-db'"],
    replicas: Annotated[int, "Desired number of replicas"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Scale a deployment, statefulset, or replicaset to a desired replica count.
    Use to scale up under load, scale down to save resources, or scale to 0 to temporarily stop a workload.
    """
    args = ["scale", resource, f"--replicas={replicas}", "-n", namespace]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Rollout management
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "rollout"])
async def kubectl_rollout_restart(
    resource: Annotated[str, "Resource to restart, e.g. 'deployment/my-app' or 'daemonset/my-agent'"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Trigger a rolling restart of all pods in a deployment, statefulset, or daemonset.
    Pods are recreated one by one with zero downtime. Use to pick up ConfigMap/Secret changes
    or clear transient issues across all replicas.
    """
    args = ["rollout", "restart", resource, "-n", namespace]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "rollout"])
async def kubectl_rollout_undo(
    resource: Annotated[str, "Resource to rollback, e.g. 'deployment/my-app'"],
    namespace: Annotated[str, "Namespace of the resource"],
    revision: Annotated[Optional[int],
                        "Specific revision to roll back to. Omit to rollback to the previous revision."] = None,
) -> ToolResult:
    """
    Rollback a deployment or statefulset to a previous revision.
    Use after a bad deploy to quickly restore the last known-good state.
    Check rollout_history first to see available revisions.
    """
    args = ["rollout", "undo", resource, "-n", namespace]
    if revision is not None:
        args += [f"--to-revision={revision}"]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "rollout"])
async def kubectl_rollout_pause(
    resource: Annotated[str, "Resource to pause, e.g. 'deployment/my-app'"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Pause an in-progress rollout. No new pods will be created until resumed.
    Use to halt a problematic deployment mid-rollout while you investigate.
    """
    args = ["rollout", "pause", resource, "-n", namespace]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "rollout"])
async def kubectl_rollout_resume(
    resource: Annotated[str, "Resource to resume, e.g. 'deployment/my-app'"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Resume a previously paused rollout so it can continue creating new pods.
    """
    args = ["rollout", "resume", resource, "-n", namespace]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Labels & Annotations
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "metadata"])
async def kubectl_label(
    resource_type: Annotated[str, "Resource type, e.g. 'pod', 'node', 'namespace'"],
    resource_name: Annotated[str, "Name of the resource"],
    labels: Annotated[dict[str, str], "Labels to set, e.g. {'env': 'staging', 'team': 'platform'}. Use value '-' to remove a label."],
    namespace: Annotated[Optional[str], "Namespace (omit for cluster-scoped resources)"] = None,
    overwrite: Annotated[bool, "Allow overwriting existing labels"] = True,
) -> ToolResult:
    """
    Add or update labels on a resource. Labels drive service selectors, scheduling,
    and policy targeting. Use value '-' to remove a label (e.g. {'old-label': '-'}).
    """
    label_args = [f"{k}={v}" if v != "-" else f"{k}-" for k, v in labels.items()]
    args = ["label", resource_type, resource_name] + label_args
    if namespace:
        args += ["-n", namespace]
    if overwrite:
        args.append("--overwrite")
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "metadata"])
async def kubectl_annotate(
    resource_type: Annotated[str, "Resource type, e.g. 'pod', 'deployment', 'service'"],
    resource_name: Annotated[str, "Name of the resource"],
    annotations: Annotated[dict[str, str], "Annotations to set. Use value '-' to remove an annotation."],
    namespace: Annotated[Optional[str], "Namespace (omit for cluster-scoped resources)"] = None,
    overwrite: Annotated[bool, "Allow overwriting existing annotations"] = True,
) -> ToolResult:
    """
    Add or update annotations on a resource.
    Annotations store non-identifying metadata like config hints, last-applied configs,
    or integration settings (e.g. Prometheus scrape config, Istio sidecar injection).
    """
    ann_args = [f"{k}={v}" if v != "-" else f"{k}-" for k, v in annotations.items()]
    args = ["annotate", resource_type, resource_name] + ann_args
    if namespace:
        args += ["-n", namespace]
    if overwrite:
        args.append("--overwrite")
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Cordon & Drain (node maintenance)
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "nodes"])
async def kubectl_cordon(
    node_name: Annotated[str, "Name of the node to cordon"],
) -> ToolResult:
    """
    Mark a node as unschedulable. Existing pods keep running but no new pods will be placed here.
    Use before draining a node for maintenance.
    """
    return await _run_kubectl(["cordon", node_name])


@tool(tags=["kubectl", "mutate", "nodes"])
async def kubectl_uncordon(
    node_name: Annotated[str, "Name of the node to uncordon"],
) -> ToolResult:
    """
    Mark a node as schedulable again after maintenance.
    """
    return await _run_kubectl(["uncordon", node_name])


@tool(tags=["kubectl", "mutate", "nodes"])
async def kubectl_drain(
    node_name: Annotated[str, "Name of the node to drain"],
    ignore_daemonsets: Annotated[bool, "Ignore DaemonSet-managed pods (usually required)"] = True,
    delete_emptydir_data: Annotated[bool, "Delete pods using emptyDir volumes"] = False,
    force: Annotated[bool, "Force drain even with unmanaged pods"] = False,
    timeout: Annotated[int, "Seconds to wait for graceful eviction"] = 300,
) -> ToolResult:
    """
    Safely evict all pods from a node for maintenance.
    Pods managed by controllers are rescheduled to other nodes.

    WARNING: This will disrupt workloads on the node.
    Always cordon first, then drain.
    """
    args = ["drain", node_name, f"--timeout={timeout}s"]
    if ignore_daemonsets:
        args.append("--ignore-daemonsets")
    if delete_emptydir_data:
        args.append("--delete-emptydir-data")
    if force:
        args.append("--force")
    return await _run_kubectl(args, timeout=timeout + 30)


# ---------------------------------------------------------------------------
# Resource lifecycle (create, apply, patch, delete)
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "lifecycle"])
async def kubectl_apply(
    manifest_yaml: Annotated[str, "YAML manifest content to apply"],
    namespace: Annotated[Optional[str], "Namespace (overrides namespace in the manifest if set)"] = None,
) -> ToolResult:
    """
    Apply a YAML manifest to create or update resources declaratively.
    This is the standard way to deploy or modify Kubernetes resources.
    Supports any resource type — Deployments, Services, ConfigMaps, etc.
    """
    args = ["apply", "-f", "-"]
    if namespace:
        args += ["-n", namespace]
    try:
        process = await asyncio.create_subprocess_exec(
            "kubectl", *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=manifest_yaml.encode("utf-8")), timeout=30
        )
        error_msg = stderr.decode("utf-8") if process.returncode != 0 else None
        return ToolResult(result=stdout.decode("utf-8"), error=error_msg)
    except asyncio.TimeoutError:
        return ToolResult(result=None, error="kubectl apply timed out after 30s")
    except Exception as e:
        return ToolResult(result=None, error=str(e))


@tool(tags=["kubectl", "mutate", "lifecycle"])
async def kubectl_patch(
    resource_type: Annotated[str, "Resource type, e.g. 'deployment', 'service', 'configmap'"],
    resource_name: Annotated[str, "Name of the resource"],
    patch: Annotated[str, "JSON patch content, e.g. '{\"spec\":{\"replicas\":3}}'"],
    namespace: Annotated[str, "Namespace of the resource"],
    patch_type: Annotated[str, "Patch strategy: 'strategic', 'merge', or 'json'"] = "strategic",
) -> ToolResult:
    """
    Patch a specific field of a resource without replacing the whole manifest.
    Use for targeted changes like updating an image tag, changing resource limits,
    or modifying a single annotation.

    Examples:
    - Update image: '{"spec":{"template":{"spec":{"containers":[{"name":"app","image":"app:v2"}]}}}}'
    - Set replicas: '{"spec":{"replicas":5}}'
    - Add env var: '{"spec":{"template":{"spec":{"containers":[{"name":"app","env":[{"name":"DEBUG","value":"true"}]}]}}}}'
    """
    args = ["patch", resource_type, resource_name, "-n", namespace, "--type", patch_type, "-p", patch]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "lifecycle"])
async def kubectl_delete_resource(
    resource_type: Annotated[str, "Resource type, e.g. 'deployment', 'service', 'job', 'configmap'"],
    resource_name: Annotated[str, "Name of the resource to delete"],
    namespace: Annotated[str, "Namespace of the resource"],
    grace_period: Annotated[Optional[int], "Seconds for graceful shutdown. 0 for immediate."] = None,
) -> ToolResult:
    """
    Delete a Kubernetes resource.
    WARNING: This is destructive. Deleting a Deployment removes all its pods.
    Deleting a PVC may lose data. Use with caution.
    """
    args = ["delete", resource_type, resource_name, "-n", namespace]
    if grace_period is not None:
        args += [f"--grace-period={grace_period}"]
    return await _run_kubectl(args, timeout=120)


# ---------------------------------------------------------------------------
# Namespace operations
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "namespace"])
async def kubectl_create_namespace(
    name: Annotated[str, "Name of the namespace to create"],
) -> ToolResult:
    """
    Create a new namespace for isolating workloads.
    """
    return await _run_kubectl(["create", "namespace", name])


# ---------------------------------------------------------------------------
# ConfigMap & Secret management
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "config"])
async def kubectl_create_configmap(
    name: Annotated[str, "Name of the ConfigMap"],
    namespace: Annotated[str, "Namespace to create the ConfigMap in"],
    from_literal: Annotated[Optional[dict[str, str]], "Key-value pairs for the ConfigMap data"] = None,
) -> ToolResult:
    """
    Create a ConfigMap from literal key-value pairs.
    ConfigMaps store non-sensitive configuration consumed by pods as environment variables or mounted files.
    """
    args = ["create", "configmap", name, "-n", namespace]
    if from_literal:
        for k, v in from_literal.items():
            args += [f"--from-literal={k}={v}"]
    return await _run_kubectl(args)


@tool(tags=["kubectl", "mutate", "config"])
async def kubectl_create_secret(
    name: Annotated[str, "Name of the Secret"],
    namespace: Annotated[str, "Namespace to create the Secret in"],
    from_literal: Annotated[dict[str, str], "Key-value pairs for the Secret data"],
    secret_type: Annotated[str, "Secret type, e.g. 'generic', 'docker-registry', 'tls'"] = "generic",
) -> ToolResult:
    """
    Create a Secret from literal key-value pairs.
    Values are base64-encoded automatically. Use for passwords, API keys, and certificates.
    """
    args = ["create", "secret", secret_type, name, "-n", namespace]
    for k, v in from_literal.items():
        args += [f"--from-literal={k}={v}"]
    return await _run_kubectl(args)


# ---------------------------------------------------------------------------
# Port forwarding
# ---------------------------------------------------------------------------

@tool(tags=["kubectl", "mutate", "network"])
async def kubectl_port_forward(
    resource: Annotated[str, "Resource to forward to, e.g. 'pod/my-pod', 'svc/my-service', 'deploy/my-app'"],
    ports: Annotated[str, "Port mapping, e.g. '8080:80' (local:remote) or '8080' (same port)"],
    namespace: Annotated[str, "Namespace of the resource"],
) -> ToolResult:
    """
    Forward a local port to a port on a pod, service, or deployment.
    Useful for accessing cluster-internal services (dashboards, databases, APIs) from your machine.

    NOTE: This starts a background process. The forwarding remains active until the process is killed.
    """
    args = ["port-forward", resource, ports, "-n", namespace]
    try:
        process = await asyncio.create_subprocess_exec(
            "kubectl", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(2)
        if process.returncode is not None:
            stdout, stderr = await process.communicate()
            return ToolResult(
                result=stdout.decode("utf-8"),
                error=stderr.decode("utf-8") if process.returncode != 0 else None,
            )
        return ToolResult(
            result=f"Port forwarding started (pid={process.pid}): kubectl {' '.join(args)}\nUse 'kill {process.pid}' to stop.",
            error=None,
        )
    except Exception as e:
        return ToolResult(result=None, error=str(e))


# ---------------------------------------------------------------------------
# Export the mutating tools collection
# ---------------------------------------------------------------------------

KubectlMutateTools = Tools(tools=[
    # Pod operations
    kubectl_delete_pod,
    kubectl_exec,
    # Scaling
    kubectl_scale,
    # Rollout management
    kubectl_rollout_restart,
    kubectl_rollout_undo,
    kubectl_rollout_pause,
    kubectl_rollout_resume,
    # Labels & Annotations
    kubectl_label,
    kubectl_annotate,
    # Node maintenance
    kubectl_cordon,
    kubectl_uncordon,
    kubectl_drain,
    # Resource lifecycle
    kubectl_apply,
    kubectl_patch,
    kubectl_delete_resource,
    # Namespace
    kubectl_create_namespace,
    # ConfigMap & Secrets
    kubectl_create_configmap,
    kubectl_create_secret,
    # Networking
    kubectl_port_forward,
])


# ===========================================================================
# SMALL KUBECTL — single flexible tool (saves context vs many specialized tools)
# ===========================================================================

@tool(tags=["kubectl", "small"])
async def kubectl(
    args: Annotated[
        str,
        "Subcommand and flags passed to kubectl, e.g. ['get','pods','-n','default'] or ['logs','my-pod','-n','default','--tail=100']. See tool description for all documented behaviors.",
    ],
    timeout: Annotated[int, "Command timeout in seconds (default 30; use 60+ for logs/apply/delete)"] = 30,
) -> ToolResult:
    """
    Run kubectl with the given subcommand and arguments. One tool for all read and mutate operations.
    Pass args as a list, e.g. ['get','pods','-n','default'] or ['logs','my-pod','-n','default','--tail=200'].

    --- READ (observability) ---

    - cluster-info
      Get high-level cluster information (control plane address, CoreDNS). Use first to verify cluster connectivity.

    - get nodes [-o wide] [--show-labels]
      List all nodes with status, roles, age, version, and resource capacity. Essential for node health and available resources.

    - top nodes
      Show CPU and memory usage per node (requires metrics-server). Identify resource-constrained or overloaded nodes.

    - get namespaces
      List all namespaces with status and age. Discover namespaces before querying workloads.

    - get pods [-n NS] [--all-namespaces] [-l label] [--field-selector ...] [--sort-by ...] -o wide
      List pods with status, restarts, age, node, IP. High restart counts or non-Running phases signal problems.
      Field selectors: status.phase=Pending (stuck scheduling), status.phase=Failed, status.phase!=Running.

    - logs <pod> -n <ns> [--tail=N] [-c container] [--previous] [--since=10m]
      Retrieve container logs. Use --previous for crashed container instance; --since for time window (e.g. 10m).

    - top pods [-n NS] [--all-namespaces] [--sort-by=cpu|memory]
      CPU and memory per pod (requires metrics-server). Find resource-hungry pods or memory leaks.

    - get pod <name> -n <ns> (-o jsonpath=... for container status)
      Detailed container status: ready/started, restart counts, last termination reason, image. Diagnose CrashLoopBackOff, ImagePullBackOff, probe failures.

    - get events [-n NS] [--all-namespaces] [--field-selector type=Warning] [--sort-by=.lastTimestamp]
      Events sorted by time. First place for scheduling failures, probe failures, image pull errors, OOMKills, volume issues. Filter type=Warning for problems only.

    - get deployments|statefulsets|daemonsets|jobs|cronjobs -o wide [-n NS]
      Deployments: desired/ready/up-to-date/available (mismatch = rollout issue). StatefulSets: ready/desired (databases, caches). DaemonSets: desired/current/ready (one per node). Jobs/CronJobs: completions, duration, status.

    - rollout status|history deployment|statefulset <name> -n <ns>
      Status: whether rollout completed, in progress, or stalled. History: revision history for rollback.

    - get services|endpoints|ingress|networkpolicies -o wide [-n NS]
      Services: type, cluster IP, ports. Endpoints: pod IPs backing each service (empty = 503). Ingress: hosts, paths, backends. NetworkPolicies: traffic rules (misconfig = connectivity issues).

    - describe <type> <name> [-n <ns>]
      Detailed info: conditions, events, volumes, probes, resource limits, scheduling decisions. Primary deep-dive for unhealthy resources.

    - get <type> <name> [-n <ns>] -o yaml
      Full YAML manifest. Inspect spec, annotations, labels, env, volume mounts.

    - get configmap <name> -n <ns> -o jsonpath={.data}
      ConfigMap data. Verify application config, feature flags, connection strings.

    - get pvc -o wide [-n NS]
      PVCs with status, capacity, access modes, storage class. Pending PVCs block pod scheduling.

    - auth can-i <verb> <resource> [-n NS]
      Check if current kubeconfig identity has permission. Use before commands to avoid permission errors.

    - get hpa -o wide [-n NS]
      HorizontalPodAutoscalers: current/target metrics, replica counts. Check if HPAs scale correctly.

    - api-resources [--sort-by=name]
      List all resource types (built-in and CRDs). Discover installed types (e.g. Prometheus, Istio, cert-manager).

    - get <resource> [name] [-n NS] [-l label] -o wide
      Generic list for any resource type including CRDs. Fallback when no specialized tool exists.

    --- MUTATE ---

    - delete pod <name> -n <ns> [--grace-period=0]
      Delete pod; controller recreates it. Force-restart misbehaving pod or clear CrashLoopBackOff. grace-period=0 for immediate.

    - exec <pod> -n <ns> [-c container] -- <cmd>...
      Run command in container. Inspect files, DNS (nslookup), env, volumes, health endpoint.

    - scale deployment|statefulset|replicaset <name> --replicas=N -n <ns>
      Scale to N replicas. Scale up/down or to 0 to stop workload.

    - rollout restart|undo|pause|resume deployment|statefulset|daemonset <name> -n <ns> [--to-revision=N]
      Restart: rolling restart (pick up ConfigMap/Secret changes). Undo: rollback to previous or --to-revision. Pause/Resume: halt or continue rollout.

    - label|annotate <type> <name> key=val [key-= to remove] [-n <ns>] [--overwrite]
      Labels: selectors, scheduling, policy. Annotations: config hints, Prometheus/Istio settings. Use --overwrite to replace.

    - cordon|uncordon <node>
      Cordon: mark node unschedulable (existing pods keep running). Use before drain. Uncordon: mark schedulable again.

    - drain <node> [--ignore-daemonsets] [--timeout=300s] [--force] [--delete-emptydir-data]
      Evict all pods from node for maintenance. Controllers reschedule. Cordon first. WARNING: disrupts node.

    - patch <type> <name> -n <ns> --type strategic|merge|json -p '<json>'
      Patch specific field (image, replicas, env) without full replace. Example: -p '{"spec":{"replicas":5}}'.

    - delete <type> <name> -n <ns> [--grace-period=N]
      Delete resource. WARNING: destructive (e.g. deleting Deployment removes all pods; PVC may lose data).

    - create namespace <name>
      Create namespace for isolating workloads.

    - create configmap <name> -n <ns> [--from-literal=KEY=val ...]
      Create ConfigMap from literal key-value pairs. Consumed by pods as env or mounted files.

    - create secret generic|docker-registry|tls <name> -n <ns> --from-literal=KEY=val ...
      Create Secret (values base64-encoded). Use for passwords, API keys, certificates.

    - port-forward <resource> <ports> -n <ns> (e.g. pod/my-pod 8080:80 or svc/my-svc 8080:80)
      Forward local port to pod/svc/deploy. For cluster-internal dashboards, DBs, APIs. Starts background process; kill to stop.

    Note: apply -f - (YAML from stdin) is not supported by this tool; use the dedicated kubectl_apply tool for that.
    """
    args = shlex.split(args.strip())
    return await _run_kubectl(args, timeout=timeout)


SmallKubeCtlTools = Tools(tools=[kubectl])
