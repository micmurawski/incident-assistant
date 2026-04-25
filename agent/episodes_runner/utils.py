import json
import os
import time

import yaml
from opentelemetry import trace

from agent.repo_paths import api_key_path
from agent.settings import SettingsManager
from agent.tasks.tasks import Task
from agent.tooling.codebase_write import CodebaseWriteTools
from agent.tooling.deploy import deploy_app
from agent.tooling.eks import scale_node_group
from agent.tooling.kubectl import kubectl_apply
from agent.tracing import (ensure_provider_instrumentation,
                           ensure_tracer_provider)

WRITE_TOOLS = [f.name for f in CodebaseWriteTools.tools]
DEPLOY_TOOLS = [deploy_app.name, kubectl_apply.name, scale_node_group.name]
API_KEY_PATH = api_key_path()

# Mapping of provider -> (env_var_name, api_key.json field)
# The env var takes precedence if set; otherwise the JSON field is read.
_PROVIDER_API_KEY_SOURCES: dict[str, tuple[str, str]] = {
    "minimax": ("MINIMAX_API_KEY", "minimax_api_key"),
    "groq": ("GROQ_API_KEY", "groq_api_key"),
    "gemini": ("GEMINI_API_KEY", "gemini_api_key"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "openai_responses": ("OPENAI_API_KEY", "openai_api_key"),
    "openrouter": ("OPENROUTER_API_KEY", "open_router_api_key"),
    "ovh": ("OVH_AI_ENDPOINTS_ACCESS_TOKEN", "ovh_ai_endpoint_access_token"),
}

# Providers that need an explicit base_url override (overrides whatever the
# handler would default to; also prevents a stale ``api.base_url`` from a
# previous run leaking into a different provider's handler).
_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "openai_responses": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ovh": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
}


def _load_provider_api_key(provider: str) -> str:
    source = _PROVIDER_API_KEY_SOURCES.get(provider)
    if source is None:
        raise ValueError(
            f"Unsupported provider '{provider}'. "
            f"Known providers: {sorted(_PROVIDER_API_KEY_SOURCES)}"
        )
    env_name, json_field = source
    if env_name in os.environ and os.environ[env_name]:
        return os.environ[env_name]
    try:
        with open(API_KEY_PATH) as f:
            api_keys = json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"No API key for provider '{provider}': env var {env_name} is unset "
            f"and api_key.json not found at {API_KEY_PATH}."
        ) from e
    if json_field not in api_keys:
        raise RuntimeError(
            f"No API key for provider '{provider}': env var {env_name} is unset "
            f"and '{json_field}' is missing from {API_KEY_PATH}."
        )
    return api_keys[json_field]


def configure_settings(
    project_name: str,
    provider: str | None = None,
    model_id: str | None = None,
) -> trace.Tracer:
    """Configure API settings for the current experiment.

    Provider/model default to the environment variables ``EXPERIMENT_PROVIDER``
    and ``EXPERIMENT_MODEL`` (set by ``experiment_runner.py`` based on CLI args),
    falling back to ``minimax`` with the handler's default model. This lets
    nested callers (e.g. ACE reflector/curator agents) pick up the same
    provider/model without having to plumb arguments through every call.

    ``reasoning_effort`` (``"minimal" | "low" | "medium" | "high"``) overrides the
    model's default reasoning effort for OpenAI-compatible reasoning models
    (gpt-oss, etc). Falls back to ``EXPERIMENT_REASONING_EFFORT`` env var, then
    to the model-declared default.
    """
    settings = SettingsManager.get_instance()
    provider = provider or os.environ.get("EXPERIMENT_PROVIDER") or "minimax"
    model_id = model_id or os.environ.get("EXPERIMENT_MODEL") or None


    settings.set("api.provider", provider)
    settings.set("api.api_key", _load_provider_api_key(provider))
    if provider in _PROVIDER_BASE_URLS:
        settings.set("api.base_url", _PROVIDER_BASE_URLS[provider])
    if model_id:
        settings.set("api.model_id", model_id)


    tracer_provider = ensure_tracer_provider(project_name=project_name)
    ensure_provider_instrumentation(provider, tracer_provider=tracer_provider)
    return trace.get_tracer(__name__)


def collect_tasks(t: Task) -> list[Task]:
    all_tasks = []
    all_tasks.append(t)
    for child in t.children:
        all_tasks.extend(collect_tasks(child))
    return all_tasks


def collect_meaningful_actions(goal: Task) -> tuple[list[str], set[str], bool]:
    all_tasks = collect_tasks(goal)
    deploy_app_called = False
    meaningful_actions = []
    modified_files = set()
    for t in all_tasks:
        for tu in t.get_tool_usage():
            name = tu.get("name")
            if name in DEPLOY_TOOLS:
                deploy_app_called = True
                inp = tu.get("input", {})
                meaningful_actions.append(f"- Action: `{name}` was executed with input: {json.dumps(inp, indent=4)}")
            elif name in WRITE_TOOLS:
                # Try to extract file path from various possible input schemas
                inp: dict = tu.get("input", {})
                path = (
                    inp.pop("path", None)
                    or inp.pop("filename", None)
                    or inp.pop("file_path", None)
                )
                if path:
                    modified_files.add(path)
                    meaningful_actions.append(f"- Action: `{name}` modified \n `{json.dumps(inp, indent=4)}`")
    return meaningful_actions, modified_files, deploy_app_called


def live_timer(seconds: int | float):
    start_time = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= seconds:
                break
            print(f"\rElapsed time: {elapsed:.0f} seconds", end="", flush=True)

            time.sleep(0.5)  # Update frequently for a smooth look
    except KeyboardInterrupt:
        print("\nTimer stopped.")


def clean_all_containers():
    from agent.rlm.container import ContainersResourceManager
    for sandbox in list(ContainersResourceManager.containers.values()):
        sandbox.shutdown()
    ContainersResourceManager.containers.clear()


def get_pod_snapshot(namespace: str) -> dict[str, dict]:
    """Return current pod metadata keyed by pod name for a namespace."""
    import subprocess

    env = get_kubectl_env()
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"[kubectl] failed to list pods in {namespace}: {result.stderr or result.stdout}")
    payload = json.loads(result.stdout or "{}")
    items = payload.get("items", [])
    return {item.get("metadata", {}).get("name", ""): item for item in items if item.get("metadata", {}).get("name")}


def cleanup_additional_pods(namespace: str, baseline_pods: set[str]) -> list[str]:
    """Delete pods that appeared after baseline and are safe cleanup targets.

    Safe targets are:
      - terminal pods (Succeeded/Failed)
      - pods owned by a Job
    """
    import subprocess

    current = get_pod_snapshot(namespace)
    extra_pods = [pod for pod in current.keys() if pod not in baseline_pods]
    if not extra_pods:
        print(f"[cleanup] no additional pods detected in {namespace}")
        return []

    env = get_kubectl_env()
    deleted: list[str] = []
    for pod_name in extra_pods:
        pod = current[pod_name]
        status_phase = pod.get("status", {}).get("phase", "")
        owner_refs = pod.get("metadata", {}).get("ownerReferences", []) or []
        owner_kinds = {ref.get("kind", "") for ref in owner_refs}
        is_terminal = status_phase in {"Succeeded", "Failed"}
        is_job_owned = "Job" in owner_kinds
        if not (is_terminal or is_job_owned):
            continue

        delete_res = subprocess.run(
            ["kubectl", "delete", "pod", pod_name, "-n", namespace, "--wait=false"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        if delete_res.returncode == 0:
            deleted.append(pod_name)
        else:
            print(
                f"[cleanup] failed to delete pod {pod_name} in {namespace}: "
                f"{delete_res.stderr or delete_res.stdout}"
            )

    print(f"[cleanup] deleted {len(deleted)} additional pod(s) in {namespace}")
    return deleted


def cleanup_keep_one_pod_per_service(namespace: str, services: list[str]) -> list[str]:
    """Keep one best pod per service and delete the rest.

    Pod names are matched by:
      - exact name (e.g. ``redis-0``)
      - prefix ``<service>-`` for rollout suffixes (ReplicaSet pod names)
    """
    import subprocess

    current = get_pod_snapshot(namespace)
    env = get_kubectl_env()
    deleted: list[str] = []

    for service in services:
        candidates = [
            pod for pod in current.values()
            if pod.get("metadata", {}).get("name") == service
            or pod.get("metadata", {}).get("name", "").startswith(f"{service}-")
        ]
        if len(candidates) <= 1:
            continue

        # Keep the healthiest pod:
        # 1) Running phase
        # 2) max ready containers
        # 3) oldest creation time (stable incumbent over fresh Pending replacement)
        def _score(item: dict) -> tuple[int, int, str]:
            status = item.get("status", {})
            phase = status.get("phase", "")
            container_statuses = status.get("containerStatuses", []) or []
            ready = sum(1 for c in container_statuses if c.get("ready"))
            created = item.get("metadata", {}).get("creationTimestamp", "")
            return (1 if phase == "Running" else 0, ready, created)

        keep = sorted(candidates, key=_score, reverse=True)[0]
        keep_name = keep.get("metadata", {}).get("name")

        for pod in candidates:
            pod_name = pod.get("metadata", {}).get("name")
            if not pod_name or pod_name == keep_name:
                continue
            delete_res = subprocess.run(
                ["kubectl", "delete", "pod", pod_name, "-n", namespace, "--wait=false"],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            if delete_res.returncode == 0:
                deleted.append(pod_name)
            else:
                print(
                    f"[cleanup] failed pruning pod {pod_name} for {service} in {namespace}: "
                    f"{delete_res.stderr or delete_res.stdout}"
                )

    print(f"[cleanup] keep-one-per-service deleted {len(deleted)} pod(s) in {namespace}")
    return deleted


def _pod_service_key(pod_name: str) -> str:
    """Infer stable service key from a pod name."""
    if not pod_name:
        return pod_name
    parts = pod_name.split("-")
    # Deployment pod format: <name>-<rs-hash>-<pod-id>
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    # StatefulSet pod format: <name>-<ordinal>
    if len(parts) >= 2 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return pod_name


def cleanup_keep_initial_services(namespace: str, baseline_pods: set[str]) -> list[str]:
    """Keep one pod per baseline service and prune everything else.

    Baseline pods should be captured before the experiment starts.
    """
    import subprocess

    baseline_services = {_pod_service_key(name) for name in baseline_pods}
    current = get_pod_snapshot(namespace)
    env = get_kubectl_env()
    deleted: list[str] = []
    deleted_workloads: set[tuple[str, str]] = set()

    service_to_pods: dict[str, list[dict]] = {}
    for pod in current.values():
        pod_name = pod.get("metadata", {}).get("name", "")
        service = _pod_service_key(pod_name)
        service_to_pods.setdefault(service, []).append(pod)

    for service, pods in service_to_pods.items():
        if service not in baseline_services:
            # Service was introduced during the experiment. Deleting pods only is not
            # enough because Deployment/StatefulSet controllers recreate them.
            to_delete = []
            for pod in pods:
                pod_name = pod.get("metadata", {}).get("name", "")
                owner_refs = pod.get("metadata", {}).get("ownerReferences", []) or []
                owner = owner_refs[0] if owner_refs else {}
                owner_kind = owner.get("kind", "")
                owner_name = owner.get("name", "")
                delete_kind = ""
                delete_name = ""

                if owner_kind == "ReplicaSet" and owner_name:
                    # ReplicaSet name format: <deployment>-<hash>
                    maybe_deploy = owner_name.rsplit("-", 1)
                    if len(maybe_deploy) == 2:
                        delete_kind, delete_name = "deployment", maybe_deploy[0]
                elif owner_kind == "StatefulSet" and owner_name:
                    delete_kind, delete_name = "statefulset", owner_name
                elif owner_kind == "DaemonSet" and owner_name:
                    delete_kind, delete_name = "daemonset", owner_name
                elif owner_kind == "Job" and owner_name:
                    delete_kind, delete_name = "job", owner_name

                if delete_kind and delete_name:
                    workload_key = (delete_kind, delete_name)
                    if workload_key in deleted_workloads:
                        continue
                    delete_res = subprocess.run(
                        [
                            "kubectl",
                            "delete",
                            delete_kind,
                            delete_name,
                            "-n",
                            namespace,
                            "--wait=false",
                        ],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=60,
                    )
                    if delete_res.returncode == 0:
                        deleted_workloads.add(workload_key)
                        deleted.append(f"{delete_kind}/{delete_name}")
                    else:
                        print(
                            f"[cleanup] failed to delete {delete_kind}/{delete_name} in {namespace}: "
                            f"{delete_res.stderr or delete_res.stdout}"
                        )
                elif pod_name:
                    # Fallback for orphan/standalone pods.
                    to_delete.append(pod)
        else:
            if len(pods) <= 1:
                continue

            def _score(item: dict) -> tuple[int, int, str]:
                status = item.get("status", {})
                phase = status.get("phase", "")
                container_statuses = status.get("containerStatuses", []) or []
                ready = sum(1 for c in container_statuses if c.get("ready"))
                created = item.get("metadata", {}).get("creationTimestamp", "")
                return (1 if phase == "Running" else 0, ready, created)

            keep = sorted(pods, key=_score, reverse=True)[0]
            keep_name = keep.get("metadata", {}).get("name")
            keep_owner_refs = keep.get("metadata", {}).get("ownerReferences", []) or []
            keep_owner = keep_owner_refs[0] if keep_owner_refs else {}
            keep_owner_kind = keep_owner.get("kind", "")
            keep_owner_name = keep_owner.get("name", "")
            to_delete = []

            for pod in pods:
                pod_name = pod.get("metadata", {}).get("name")
                if not pod_name or pod_name == keep_name:
                    continue

                owner_refs = pod.get("metadata", {}).get("ownerReferences", []) or []
                owner = owner_refs[0] if owner_refs else {}
                owner_kind = owner.get("kind", "")
                owner_name = owner.get("name", "")

                # During a stuck Deployment rollout we may have one healthy old RS pod
                # plus one Pending pod owned by a different RS. Deleting only the pod
                # can let the RS recreate it, so prune that non-keeper RS instead.
                if (
                    owner_kind == "ReplicaSet"
                    and owner_name
                    and (owner_kind, owner_name) != (keep_owner_kind, keep_owner_name)
                ):
                    workload_key = ("replicaset", owner_name)
                    if workload_key in deleted_workloads:
                        continue
                    delete_res = subprocess.run(
                        [
                            "kubectl",
                            "delete",
                            "replicaset",
                            owner_name,
                            "-n",
                            namespace,
                            "--wait=false",
                        ],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=60,
                    )
                    if delete_res.returncode == 0:
                        deleted_workloads.add(workload_key)
                        deleted.append(f"replicaset/{owner_name}")
                        continue
                    print(
                        f"[cleanup] failed to delete replicaset/{owner_name} in {namespace}: "
                        f"{delete_res.stderr or delete_res.stdout}"
                    )

                to_delete.append(pod)

        for pod in to_delete:
            pod_name = pod.get("metadata", {}).get("name")
            if not pod_name:
                continue
            delete_res = subprocess.run(
                ["kubectl", "delete", "pod", pod_name, "-n", namespace, "--wait=false"],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            if delete_res.returncode == 0:
                deleted.append(pod_name)
            else:
                print(
                    f"[cleanup] failed to delete pod {pod_name} for service {service} in {namespace}: "
                    f"{delete_res.stderr or delete_res.stdout}"
                )

    # Strict convergence pass: controllers can recreate duplicate pods after the first
    # prune pass (e.g. during a stuck Deployment rollout). Retry a few times and force
    # non-keeper ReplicaSets to 0 to converge to a single pod per baseline service.
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        current = get_pod_snapshot(namespace)
        baseline_duplicates: dict[str, list[dict]] = {}
        for pod in current.values():
            pod_name = pod.get("metadata", {}).get("name", "")
            service = _pod_service_key(pod_name)
            if service not in baseline_services:
                continue
            baseline_duplicates.setdefault(service, []).append(pod)

        baseline_duplicates = {
            service: pods
            for service, pods in baseline_duplicates.items()
            if len(pods) > 1
        }
        if not baseline_duplicates:
            break

        print(
            f"[cleanup] enforce-single-pod pass {attempt}/{max_attempts} "
            f"for {len(baseline_duplicates)} service(s) in {namespace}"
        )

        for service, pods in baseline_duplicates.items():
            def _score(item: dict) -> tuple[int, int, str]:
                status = item.get("status", {})
                phase = status.get("phase", "")
                container_statuses = status.get("containerStatuses", []) or []
                ready = sum(1 for c in container_statuses if c.get("ready"))
                created = item.get("metadata", {}).get("creationTimestamp", "")
                return (1 if phase == "Running" else 0, ready, created)

            keep = sorted(pods, key=_score, reverse=True)[0]
            keep_name = keep.get("metadata", {}).get("name")
            keep_owner_refs = keep.get("metadata", {}).get("ownerReferences", []) or []
            keep_owner = keep_owner_refs[0] if keep_owner_refs else {}
            keep_owner_kind = keep_owner.get("kind", "")
            keep_owner_name = keep_owner.get("name", "")

            for pod in pods:
                pod_name = pod.get("metadata", {}).get("name")
                if not pod_name or pod_name == keep_name:
                    continue

                owner_refs = pod.get("metadata", {}).get("ownerReferences", []) or []
                owner = owner_refs[0] if owner_refs else {}
                owner_kind = owner.get("kind", "")
                owner_name = owner.get("name", "")

                if (
                    owner_kind == "ReplicaSet"
                    and owner_name
                    and (owner_kind, owner_name) != (keep_owner_kind, keep_owner_name)
                ):
                    workload_key = ("replicaset-scale0", owner_name)
                    if workload_key not in deleted_workloads:
                        scale_res = subprocess.run(
                            [
                                "kubectl",
                                "scale",
                                "replicaset",
                                owner_name,
                                "-n",
                                namespace,
                                "--replicas=0",
                            ],
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=60,
                        )
                        if scale_res.returncode == 0:
                            deleted_workloads.add(workload_key)
                            deleted.append(f"replicaset/{owner_name}:scaled-0")
                        else:
                            print(
                                f"[cleanup] failed to scale replicaset/{owner_name} to 0 in {namespace}: "
                                f"{scale_res.stderr or scale_res.stdout}"
                            )

                delete_res = subprocess.run(
                    ["kubectl", "delete", "pod", pod_name, "-n", namespace, "--wait=false"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=60,
                )
                if delete_res.returncode == 0:
                    deleted.append(pod_name)
                else:
                    print(
                        f"[cleanup] failed to delete duplicate pod {pod_name} "
                        f"for service {service} in {namespace}: "
                        f"{delete_res.stderr or delete_res.stdout}"
                    )

        time.sleep(2)

    print(f"[cleanup] keep-initial-services deleted {len(deleted)} pod(s) in {namespace}")
    return deleted


def get_kubectl_env():
    """Env for subprocesses that call kubectl/AWS CLIs.

    Must merge with ``os.environ``: passing a dict that only sets AWS keys
    replaces the whole process environment and drops ``PATH``, so ``kubectl``
    is not found (FileNotFoundError).
    """
    api = json.load(open(API_KEY_PATH))
    env = os.environ.copy()
    env.update(
        {
            "AWS_ACCESS_KEY_ID": api["robot"]["access_key_id"],
            "AWS_SECRET_ACCESS_KEY": api["robot"]["secret_access_key"],
            "AWS_REGION": "us-east-1",
        }
    )
    return env


async def restore_eks_node_group():
    from agent.tooling.eks import list_node_groups, scale_node_group
    env = get_kubectl_env()
    # Attempt to generate/fetch node group - pick the first available, fallback to "ng-1" if none found
    # cluster_info = await get_cluster_info(env=env)
    # cluster_info = yaml.safe_load(cluster_info.result)
    result = await list_node_groups(env=env)
    cluster_info = yaml.safe_load(result.result)
    # apps_node_group = filter(lambda x: x.startswith("apps-"), cluster_info["nodegroups"])

    for node_group in cluster_info["nodegroups"]:
        result = await scale_node_group(node_group=node_group, desired_size=1, min_size=1, max_size=1, env=env)
        if result.error is not None:
            raise RuntimeError(f"[eks] restore_eks_node_group failed: {result.error}")
        print(f"[eks] restore_eks_node_group completed: {node_group}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(restore_eks_node_group())
