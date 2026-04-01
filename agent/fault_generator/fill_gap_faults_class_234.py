#!/usr/bin/env python3
"""
Generate missing class 2 / 3 / 4 faults (LLM + worktree flow from git_workflow).

Vault layout must stay `fault-<class>-<service>-<uuid>` to match existing entries.
git_workflow.start_fault_injector uses a different branch_name order, so this
script defines a local start node and a small create_agent wrapper.

Run from repo root with agent package on PYTHONPATH, e.g.:

  cd agent && python -m fault_generator.fill_gap_faults_class_234 --dry-run
  cd agent && python -m fault_generator.fill_gap_faults_class_234 --limit 1
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import uuid
from pathlib import Path

from fault_generator import git_workflow as gw
from fault_generator.fault_vault_gaps import (
    default_vault_dir, format_gap_report, gaps_class_234,
    retry_excluded_fault_vault_dirnames)
from framework.decorators import node
from openinference.instrumentation import using_attributes
from opentelemetry import trace

from agent.tooling import CodebaseReadTools, CodebaseWriteTools


@node
async def start_fault_injector_gap(service_name: str, fault_class: int, uuid_value: str):
    gw._run_git("checkout", "master", "-f", cwd=gw.REPO_ROOT)
    branch_name = f"fault-{fault_class}-{service_name}-{uuid_value}"
    pattern = str(gw.CURRENT_DIR / "fault-vault" / f"fault-{fault_class}-{service_name}-*" / "FAULT.md")
    res = glob.glob(pattern)
    skip_names = retry_excluded_fault_vault_dirnames()
    content = (
        "Here are the faults that already exist, try to create a new fault "
        "that is different from the ones that already exist:\n"
    )
    for r in res:
        parent_name = Path(r).parent.name
        if parent_name in skip_names:
            continue
        content += f"FAULT: {parent_name}\n"
        content += Path(r).read_text()
        content += "\n"
    return {
        "messages": [
            {
                "role": "user",
                "content": (
                    f"You are a fault-injector for the {service_name} service. "
                    f"You are tasked with introducing a fault into the codebase. "
                    f"The fault class is {fault_class}. "
                    f"The fault is {gw.FAULT_CLASS_DESCRIPTIONS[fault_class]}. \n"
                    f"{content}"
                ),
            }
        ],
        "branch_name": branch_name,
    }


async def create_agent_gap234(repo_root: Path, work_tree_path: Path, branch_name: str):
    result = await gw.work_tree_service.create_worktree(
        cwd=str(repo_root),
        path=str(work_tree_path),
        branch=branch_name,
        base_branch="master",
        create_new_branch=True,
    )
    if not result.success:
        raise RuntimeError(f"Failed to create worktree: {result.message}")
    agent = gw.FaultInjector(
        name=branch_name,
        cwd=work_tree_path,
        system_prompt=gw.FAULT_INJECTOR_SYSTEM,
    )
    tools = CodebaseReadTools | CodebaseWriteTools
    agent.bind_tools(tools, {"cwd": agent.cwd})
    agent.call_llm - "tools" >> tools
    tools >> agent.call_llm
    start_fault_injector_gap >> agent.call_llm
    agent.call_llm - "default" >> gw.check_fault_injector
    gw.check_fault_injector - "reflect" >> agent.call_llm
    gw.check_fault_injector - "default" >> gw.end_fault_injector
    agent.flow = gw._TracedFlow(start=start_fault_injector_gap)
    agent.get_flow_graph_png("fault_injector_gap234.png")
    return agent


async def run_one(service_name: str, fault_class: int) -> None:
    gw._run_git("checkout", "master", "-f", cwd=gw.REPO_ROOT)
    uuid_value = str(uuid.uuid4())
    branch_name = f"fault-{fault_class}-{service_name}-{uuid_value}"
    worktree_path = gw.WORKTREES_DIR / branch_name
    agent = await create_agent_gap234(gw.REPO_ROOT, worktree_path, branch_name)
    shared_state = {
        "cwd": str(worktree_path),
        "service_name": service_name,
        "fault_class": fault_class,
        "uuid_value": uuid_value,
    }
    tracer = trace.get_tracer(__name__)
    session_id = str(uuid.uuid4())
    print(f"[gap234] {branch_name}")
    with tracer.start_as_current_span("fill-gap-fault-class-234-" + session_id):
        with using_attributes(session_id=session_id):
            await agent.call(shared_state)


async def main_async(args: argparse.Namespace) -> None:
    vault = Path(args.vault) if args.vault else default_vault_dir()
    pairs = gaps_class_234(vault)
    if args.service:
        pairs = [(s, c) for s, c in pairs if s == args.service]
    if args.fault_class is not None:
        pairs = [(s, c) for s, c in pairs if c == args.fault_class]
    if args.limit is not None:
        pairs = pairs[: args.limit]
    print(format_gap_report(vault))
    print(f"\nPlanned runs: {len(pairs)}")
    for s, c in pairs:
        print(f"  fault-{c}-{s}-…")
    if args.dry_run:
        return
    for service_name, fault_class in pairs:
        await run_one(service_name, fault_class)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing class 2–4 faults in fault-vault.")
    parser.add_argument("--vault", type=str, default=None, help="Path to fault-vault (default: beside this package)")
    parser.add_argument("--dry-run", action="store_true", help="Only print gaps and planned branch names")
    parser.add_argument("--limit", type=int, default=None, help="Max number of faults to generate")
    parser.add_argument("--service", type=str, default=None, help="Only this service name")
    parser.add_argument("--fault-class", type=int, choices=(2, 3, 4), default=None, help="Only this class")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
