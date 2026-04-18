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
    "openrouter": ("OPENROUTER_API_KEY", "open_router_api_key"),
    "ovh": ("OVH_AI_ENDPOINTS_ACCESS_TOKEN", "ovh_ai_endpoint_access_token"),
}

# Providers that need an explicit base_url override (overrides whatever the
# handler would default to; also prevents a stale ``api.base_url`` from a
# previous run leaking into a different provider's handler).
_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
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
