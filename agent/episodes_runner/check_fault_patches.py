#!/usr/bin/env python3
"""
Verify that fault ``git.patch`` files apply cleanly against the episode source tree.

Mirrors ``episode_runner.apply_fault``: fresh copy of ``services/robot-shop`` (no ``.git``),
then ``patch -p1 -f`` with the patch on stdin — same as a real episode (``-f`` avoids TTY prompts that would hang).

Note: ``episodes_runner/runner.py`` uses ``git apply`` instead; this checker targets the
``episode_runner`` path only.

Usage (from the ``agent/`` directory that contains the ``agent`` package)::

    python -m episodes_runner.check_fault_patches

    python -m episodes_runner.check_fault_patches --all-vault
    python -m episodes_runner.check_fault_patches --scenarios path/to/shuffled_scenarios.yaml
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # noqa: N816  # optional; scenarios file can be parsed without it

# Allow ``python agent/episodes_runner/check_fault_patches.py`` from repo root
_AGENT_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_PKG_ROOT))

from agent.repo_paths import fault_vault_dir, robot_shop_dir  # noqa: E402

_EPISODES_DIR = Path(__file__).resolve().parent


def _prepare_workspace(source_dir: Path, workspace_dir: Path) -> None:
    """Same as ``episode_runner.create_workspace`` (copy tree, strip ``.git``)."""
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(source_dir, workspace_dir, symlinks=False)
    git_dir = workspace_dir / ".git"
    if git_dir.exists():
        if git_dir.is_dir():
            shutil.rmtree(git_dir)
        else:
            os.remove(git_dir)


def _reset_workspace_from_pristine(pristine: Path, workspace: Path) -> None:
    """Restore ``workspace`` to match ``pristine`` (faster than full copytree when rsync exists)."""
    if shutil.which("rsync"):
        workspace.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["rsync", "-a", "--delete", f"{pristine}/", f"{workspace}/"],
            check=True,
            capture_output=True,
        )
        return
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(pristine, workspace, symlinks=False)


def _apply_patch_like_episode(patch_file: Path, workspace_dir: Path) -> tuple[int, str]:
    # -f: non-interactive (otherwise patch may prompt on /dev/tty and hang when stdin is the patch)
    cmd = ["patch", "-p1", "-f"]
    with patch_file.open("rb") as stdin:
        result = subprocess.run(
            cmd,
            cwd=workspace_dir,
            stdin=stdin,
            capture_output=True,
            text=True,
        )
    out = (result.stderr or result.stdout or "").strip()
    return result.returncode, out


def _load_scenario_ids_from_text(text: str) -> list[str]:
    """Parse ``shuffled_scenarios.yaml``-style ``- id: fault-...`` lines (no PyYAML needed)."""
    ids: list[str] = []
    for m in re.finditer(r"^\s*-\s+id:\s*(\S+)", text, re.MULTILINE):
        ids.append(m.group(1))
    return ids


def _load_scenario_ids(scenarios_path: Path) -> list[str]:
    raw = scenarios_path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(raw)
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        if scenarios:
            return [str(s["id"]) for s in scenarios if isinstance(s, dict) and s.get("id")]
    return _load_scenario_ids_from_text(raw)


def _collect_vault_fault_ids(vault: Path) -> list[str]:
    ids: list[str] = []
    if not vault.is_dir():
        return ids
    for child in sorted(vault.iterdir()):
        if child.is_dir() and (child / "git.patch").is_file():
            ids.append(child.name)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check which fault git.patch files fail to apply (patch -p1, robot-shop copy)."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help=f"Episode source tree (default: {robot_shop_dir()})",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help=f"Fault vault directory (default: {fault_vault_dir()})",
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=_EPISODES_DIR / "shuffled_scenarios.yaml",
        help="YAML with `scenarios:` list of `{id: ...}` (default: episodes_runner/shuffled_scenarios.yaml)",
    )
    parser.add_argument(
        "--all-vault",
        action="store_true",
        help="Check every fault directory under the vault that contains git.patch (ignore --scenarios)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing patch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only check the first N scenario IDs (order in the scenarios file)",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        metavar="IDS",
        help="Comma-separated fault IDs to check (overrides --scenarios / --all-vault unless --all-vault is set)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="No progress lines (summary only)",
    )
    args = parser.parse_args()

    source = (args.source or robot_shop_dir()).resolve()
    vault = (args.vault or fault_vault_dir()).resolve()

    if not source.is_dir():
        print(f"error: source directory not found: {source}", file=sys.stderr)
        return 2

    if args.all_vault:
        fault_ids = _collect_vault_fault_ids(vault)
    elif args.only:
        fault_ids = [x.strip() for x in args.only.split(",") if x.strip()]
    else:
        if not args.scenarios.is_file():
            print(f"error: scenarios file not found: {args.scenarios}", file=sys.stderr)
            return 2
        fault_ids = _load_scenario_ids(args.scenarios)

    if not fault_ids:
        print("No fault IDs to check.")
        return 0

    if args.limit is not None and args.limit >= 0:
        fault_ids = fault_ids[: args.limit]

    ok: list[str] = []
    missing_patch: list[str] = []
    missing_dir: list[str] = []
    failed: list[tuple[str, str]] = []

    def log(msg: str = "", *, end: str = "\n") -> None:
        if not args.quiet:
            print(msg, end=end, flush=True)

    total = len(fault_ids)
    log(f"check_fault_patches: {total} scenario(s), source={source}")
    log("Preparing pristine copy of source (this can take a bit)…")

    with tempfile.TemporaryDirectory(prefix="fault_patch_check_") as tmp:
        tmp_path = Path(tmp)
        pristine = tmp_path / "pristine"
        workspace = tmp_path / "workspace"
        _prepare_workspace(source, pristine)
        log(f"Pristine ready; temp dir {tmp_path}")

        for n, fault_id in enumerate(fault_ids, start=1):
            fault_dir = vault / fault_id
            patch_file = fault_dir / "git.patch"

            if not fault_dir.is_dir():
                log(f"[{n}/{total}] {fault_id} … skip (fault dir missing in vault)")
                missing_dir.append(fault_id)
                if args.fail_fast:
                    break
                continue
            if not patch_file.is_file():
                log(f"[{n}/{total}] {fault_id} … skip (no git.patch)")
                missing_patch.append(fault_id)
                if args.fail_fast:
                    break
                continue

            log(f"[{n}/{total}] {fault_id} … ", end="")
            _reset_workspace_from_pristine(pristine, workspace)
            code, out = _apply_patch_like_episode(patch_file, workspace)
            if code == 0:
                ok.append(fault_id)
                log("ok")
            else:
                msg = out if out else f"patch exited with code {code}"
                failed.append((fault_id, msg))
                log("FAIL")
                if args.fail_fast:
                    break

    print(f"Source: {source}")
    print(f"Vault:  {vault}")
    print(f"Checked {len(fault_ids)} scenario(s); patch applied: {len(ok)}, failed: {len(failed)}")
    if missing_dir:
        print(f"\nMissing fault directory ({len(missing_dir)}):")
        for x in missing_dir:
            print(f"  {x}")
    if missing_patch:
        print(f"\nMissing git.patch ({len(missing_patch)}):")
        for x in missing_patch:
            print(f"  {x}")
    if failed:
        print(f"\nPatch apply failures ({len(failed)}):")
        for fault_id, msg in failed:
            print(f"  --- {fault_id} ---")
            for line in msg.splitlines():
                print(f"  {line}")

    if failed or missing_dir or missing_patch:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
