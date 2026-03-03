"""
Runner for LLM-based fault generation. Writes README.md, git.patch, and meta.yaml per fault.
"""

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

# Repo root is parent of agent/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROBOT_SHOP_DOC = REPO_ROOT / "services" / "robot-shop" / "DOC.md"
DOC_EXCERPT_LEN = 3500


def _load_doc_excerpt() -> str | None:
    if not ROBOT_SHOP_DOC.exists():
        return None
    text = ROBOT_SHOP_DOC.read_text(encoding="utf-8")
    return text[:DOC_EXCERPT_LEN] + ("..." if len(text) > DOC_EXCERPT_LEN else "")


def _build_api_handler(provider: str, api_key: str | None, model_id: str | None):
    """Build the LLM API handler from env/config. Lazy import to avoid requiring agent.agent when not used."""
    try:
        from agent.agent.providers import build_api_handler
    except ImportError:
        try:
            from agent.providers import build_api_handler
        except ImportError:
            raise ImportError(
                "Could not import build_api_handler. Ensure the agent package is on PYTHONPATH (e.g. run from repo root with PYTHONPATH=agent)."
            ) from None

    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    if not api_key and provider == "gemini":
        raise ValueError("Set GEMINI_API_KEY or API_KEY for Gemini.")

    model_id = model_id or os.environ.get("FAULT_GEN_MODEL_ID") or os.environ.get("GEMINI_MODEL_ID")
    kwargs = {"api_key": api_key}
    if model_id:
        kwargs["model_id"] = model_id
    return build_api_handler(provider=provider, **kwargs)


async def run(
    fault_class: int,
    *,
    vault_dir: str | Path | None = None,
    cascade_preferred: bool = False,
    provider: str = "gemini",
    api_key: str | None = None,
    model_id: str | None = None,
    seed: int | None = None,
) -> str:
    """
    Generate one fault using the LLM and write README.md, git.patch, meta.yaml.
    Returns the scenario_id (directory name).
    """
    if seed is not None:
        random.seed(seed)

    vault_dir = Path(vault_dir or os.path.join(os.path.dirname(__file__), "..", "fault-vault")).resolve()
    from .config import CLASS_DIRS
    from .generator import generate_fault

    class_dir_name = CLASS_DIRS.get(fault_class, f"class_{fault_class}")
    class_dir = vault_dir / class_dir_name
    class_dir.mkdir(parents=True, exist_ok=True)

    scenario_id = f"fault-{fault_class}-{random.randint(10000, 99999)}"
    scenario_dir = class_dir / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)

    api_handler = _build_api_handler(provider, api_key, model_id)
    doc_excerpt = _load_doc_excerpt()

    readme_text, patch_text = await generate_fault(
        api_handler,
        fault_class,
        cascade_preferred=cascade_preferred,
        robot_shop_doc_excerpt=doc_excerpt,
    )

    (scenario_dir / "README.md").write_text(readme_text, encoding="utf-8")
    (scenario_dir / "git.patch").write_text(patch_text or "# No patch generated\n", encoding="utf-8")

    meta = {
        "class": fault_class,
        "scenario_id": scenario_id,
        "cascade_preferred": cascade_preferred,
    }
    try:
        import yaml
        (scenario_dir / "meta.yaml").write_text(yaml.dump(meta, sort_keys=False), encoding="utf-8")
    except ImportError:
        (scenario_dir / "meta.yaml").write_text(
            f"class: {fault_class}\nscenario_id: {scenario_id}\ncascade_preferred: {cascade_preferred}\n",
            encoding="utf-8",
        )

    print(f"Created fault: {scenario_dir}")
    return scenario_id


def main():
    parser = argparse.ArgumentParser(description="Generate one fault using the LLM (e.g. Gemini).")
    parser.add_argument("fault_class", type=int, choices=[2, 3, 4], nargs="?", default=2, help="Fault class (2=code, 3=k8s, 4=runtime)")
    parser.add_argument("--vault-dir", default=None, help="Base directory for fault-vault (default: agent/fault-vault)")
    parser.add_argument("--cascade", action="store_true", help="Prefer targets that cause cascading failures")
    parser.add_argument("--provider", default=os.environ.get("API_PROVIDER", "gemini"), help="LLM provider (default: gemini)")
    parser.add_argument("--api-key", default=None, help="API key (or set GEMINI_API_KEY / API_KEY)")
    parser.add_argument("--model-id", default=None, help="Model ID (or set FAULT_GEN_MODEL_ID)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for scenario_id")
    args = parser.parse_args()

    fault_class = args.fault_class
    scenario_id = asyncio.run(
        run(
            fault_class,
            vault_dir=args.vault_dir,
            cascade_preferred=args.cascade,
            provider=args.provider,
            api_key=args.api_key,
            model_id=args.model_id,
            seed=args.seed,
        )
    )
    print(f"Scenario ID: {scenario_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
