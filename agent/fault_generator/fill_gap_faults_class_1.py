#!/usr/bin/env python3
"""
Generate missing class 1 (Chaos Mesh + codebase) faults using
saboteur_chaos_class_1 helpers and create_agent.

PROMPT_TEMPLATE expects `load_gen_script`; main() in saboteur_chaos_class_1 does
not pass it — this script supplies a truncated load script excerpt.

Run (from agent project root, PYTHONPATH set as for other fault_generator scripts):

  python -m fault_generator.fill_gap_faults_class_1 --dry-run
  python -m fault_generator.fill_gap_faults_class_1 --limit 1
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import uuid
from itertools import product
from pathlib import Path

from openinference.instrumentation import using_attributes
from opentelemetry import trace

from fault_generator.fault_vault_gaps import (default_vault_dir,
                                              format_gap_report, gaps_class_1)
from fault_generator.saboteur_chaos_class_1 import (CHAOS_TEMPLATES,
                                                    LOAD_GEN_SCRIPT, NAMESPACE,
                                                    PROMPT_TEMPLATE, REPO_ROOT,
                                                    WORKTREES_DIR,
                                                    create_agent)


def _load_gen_excerpt() -> str:
    if LOAD_GEN_SCRIPT.is_file():
        text = LOAD_GEN_SCRIPT.read_text(encoding="utf-8", errors="replace")
        return text[:8000] + ("\n..." if len(text) > 8000 else "")
    return str(LOAD_GEN_SCRIPT)


def _stable_index(service: str, modulus: int) -> int:
    h = hashlib.sha256(service.encode("utf-8")).hexdigest()
    return int(h[:16], 16) % modulus


def _pick_template_and_combo(service: str):
    """Deterministic template + one hyperparameter combo per service name."""
    idx = _stable_index(service, len(CHAOS_TEMPLATES))
    chaos_template = CHAOS_TEMPLATES[idx]
    param_names = list(chaos_template["params"].keys())
    param_values = [chaos_template["params"][name] for name in param_names]
    all_combos = list(product(*param_values))
    combo = all_combos[_stable_index(service, len(all_combos))]
    return chaos_template, combo


async def run_one(service: str, chaos_template: dict, combo: tuple) -> None:
    fault_id = 1
    param_names = list(chaos_template["params"].keys())
    combo_kwargs = dict(zip(param_names, combo))
    manifest_yaml = chaos_template["method"](
        namespace=NAMESPACE,
        label_selector=f"app={service}",
        **combo_kwargs,
    )
    system_prompt = PROMPT_TEMPLATE.format(
        service=service,
        manifest_yaml=manifest_yaml,
        load_gen_script=_load_gen_excerpt(),
    )
    uuid_value = uuid.uuid4().hex
    branch_name = (
        f"fault-{fault_id}-{service}-"
        f"{chaos_template['method'].__name__}-"
        f"{uuid_value}"
    )
    worktree_path = WORKTREES_DIR / branch_name
    agent = await create_agent(REPO_ROOT, worktree_path, branch_name, system_prompt)
    shared_state = {
        "cwd": str(worktree_path),
        "service_name": service,
        "fault_class": fault_id,
        "uuid_value": uuid_value,
        "manifest_yaml": manifest_yaml,
        "branch_name": branch_name,
    }
    tracer = trace.get_tracer(__name__)
    session_id = str(uuid.uuid4())
    print(f"[gap1] {branch_name}")
    with tracer.start_as_current_span("fill-gap-fault-class-1-" + session_id):
        with using_attributes(session_id=session_id):
            await agent.call(shared_state)


async def main_async(args: argparse.Namespace) -> None:
    vault = Path(args.vault) if args.vault else default_vault_dir()
    services = gaps_class_1(vault)
    if args.service:
        services = [s for s in services if s == args.service]
    if args.limit is not None:
        services = services[: args.limit]
    print(format_gap_report(vault))
    print(f"\nPlanned class-1 runs: {len(services)}")
    for s in services:
        print(f"  {s}")
    if args.dry_run:
        return
    for service in services:
        tpl, combo = _pick_template_and_combo(service)
        await run_one(service, tpl, combo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing class 1 (Chaos Mesh) faults in fault-vault.")
    parser.add_argument("--vault", type=str, default=None, help="Path to fault-vault (default: beside this package)")
    parser.add_argument("--dry-run", action="store_true", help="Only print gaps and planned services")
    parser.add_argument("--limit", type=int, default=None, help="Max number of faults to generate")
    parser.add_argument("--service", type=str, default=None, help="Only this service name")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
