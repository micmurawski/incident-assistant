import json
import os
import re
import shutil
from subprocess import PIPE, Popen
from typing import Optional


def _parse_cpu_quantity(s: str) -> float:
    """Parse Kubernetes CPU quantity to cores (e.g. '500m' -> 0.5, '1' -> 1.0)."""
    if not s or not isinstance(s, str):
        return 0.0
    s = s.strip()
    if s.endswith("m"):
        return int(s[:-1]) / 1000.0
    return float(s)


def _parse_memory_quantity(s: str) -> float:
    """Parse Kubernetes memory quantity to bytes (e.g. '256Mi' -> 256*1024*1024)."""
    if not s or not isinstance(s, str):
        return 0.0
    s = s.strip()
    m = re.match(r"^(\d+)(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K)?$", s, re.I)
    if not m:
        return float(s) if s.isdigit() else 0.0
    num = int(m.group(1))
    unit = (m.group(2) or "").upper()
    if unit == "E" or unit == "EI":
        return num * (1000**6)
    if unit == "P" or unit == "PI":
        return num * (1000**5)
    if unit == "T" or unit == "TI":
        return num * (1000**4)
    if unit == "G" or unit == "GI":
        return num * (1024**3)
    if unit == "M" or unit == "MI":
        return num * (1024**2)
    if unit == "K" or unit == "KI":
        return num * 1024
    return float(num)


def get_pod_resource_limits(
    namespace: str,
    apps: list[str],
    env: Optional[dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Fetch CPU and memory limits per app from the cluster via kubectl get pods -o json.
    Returns (cpu_limits_cores, memory_limits_bytes) keyed by app name.
    """
    cpu_limits: dict[str, float] = {}
    memory_limits: dict[str, float] = {}
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        return cpu_limits, memory_limits
    cmd = [kubectl_path, "get", "pods", "-n", namespace, "-o", "json"]
    # Use current process env (includes KUBECONFIG, PATH, etc.) and apply caller overrides.
    # Passing only caller's env would drop KUBECONFIG and break kubectl auth to ~/.kube/config.
    run_env = os.environ.copy()

    if env:
        run_env.update(env)

    try:
        process = Popen(
            args=cmd,
            stdout=PIPE,
            stderr=PIPE,
            env=run_env,
            cwd=cwd,
        )
        stdout, stderr = process.communicate()
    except FileNotFoundError:
        return cpu_limits, memory_limits
    if process.returncode != 0 or stderr:
        return cpu_limits, memory_limits

    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return cpu_limits, memory_limits

    items = data.get("items") or []
    for pod in items:
        meta = pod.get("metadata") or {}
        pod_name = meta.get("name") or ""
        app_key: Optional[str] = None
        for app in apps:
            if pod_name == app or pod_name.startswith(app + "-"):
                app_key = app
                break
        if app_key is None:
            continue
        spec = pod.get("spec") or {}
        for cont in spec.get("containers") or []:
            res = cont.get("resources") or {}
            limits = res.get("limits") or {}
            if "cpu" in limits:
                cpu_limits[app_key] = cpu_limits.get(app_key, 0.0) + _parse_cpu_quantity(str(limits["cpu"]))
            if "memory" in limits:
                memory_limits[app_key] = memory_limits.get(app_key, 0.0) + _parse_memory_quantity(str(limits["memory"]))
    return cpu_limits, memory_limits
