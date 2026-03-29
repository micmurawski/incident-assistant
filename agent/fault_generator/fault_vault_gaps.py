"""
Scan fault-vault directory names (`fault-<type>-<service>-…`) and report
(service, type) pairs with zero entries.

Used by fill_gap_faults_class_1.py and fill_gap_faults_class_234.py.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

# Class 2–4 injector targets (git_workflow apps plus datastores that appear in vault).
FAULT_234_SERVICES = [
    "cart",
    "catalogue",
    "user",
    "payment",
    "shipping",
    "ratings",
    "dispatch",
    "web",
    "mongo",
    "mysql",
    "redis",
]

# Class 1 (Chaos Mesh) services — keep aligned with saboteur_chaos_class_1.SERVICES.
CHAOS_CLASS_1_SERVICES = [
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
    "web",
]


def default_vault_dir() -> Path:
    return Path(__file__).resolve().parent / "fault-vault"


# Basenames under fault-vault that do NOT count toward gap detection (partial / bad runs you want to redo).
# Edit the block below: lines starting with # are ignored. Any other non-empty line is an excluded dirname.
_RETRY_EXCLUDE_FAULT_VAULT_DIRNAMES_BLOCK = """
# Mar 28 gap-fill run — comment out (prefix #) a line when that folder should count again.
fault-3-cart-f41cb112-e415-47f0-acf3-46fd8d76c8ce
fault-3-catalogue-716cc0dd-5274-4884-88b3-33e0d0eb292e
fault-3-dispatch-ef47e639-f1c3-4d81-9fc7-29d9ef958f87
fault-2-mongo-6763a60c-177c-49b8-8c0d-50e1ed196630
fault-3-mongo-df7f6052-d298-472e-99fb-1907c4e12c4f
fault-4-mongo-553578c6-e7ed-40ce-a43c-b00e7a4750a2
fault-2-mysql-e55986c7-dc6b-4c8b-b5b6-6ac6e0882a46
fault-3-mysql-56004555-cd5a-45d2-a030-71cd44c211db
"""


def _excluded_fault_vault_dirnames() -> frozenset[str]:
    out: list[str] = []
    for line in _RETRY_EXCLUDE_FAULT_VAULT_DIRNAMES_BLOCK.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return frozenset(out)


def retry_excluded_fault_vault_dirnames() -> frozenset[str]:
    """Dirnames skipped for gap counting and (optionally) for prior-fault prompts."""
    return _excluded_fault_vault_dirnames()


def counts_by_fault_type_and_service(vault: Path | None = None) -> dict[tuple[int, str], int]:
    vault = vault or default_vault_dir()
    excluded = _excluded_fault_vault_dirnames()
    counts: dict[tuple[int, str], int] = defaultdict(int)
    if not vault.is_dir():
        return counts
    for p in vault.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in excluded:
            continue
        if not name.startswith("fault-"):
            continue
        parts = name.split("-", 3)
        if len(parts) < 3:
            continue
        type_str, service = parts[1], parts[2]
        if not type_str.isdigit():
            continue
        counts[(int(type_str), service)] += 1
    return counts


def gaps_class_234(vault: Path | None = None) -> list[tuple[str, int]]:
    """(service, fault_class) pairs with fault_class in {2,3,4} and count 0."""
    counts = counts_by_fault_type_and_service(vault)
    out: list[tuple[str, int]] = []
    for svc in FAULT_234_SERVICES:
        for fc in (2, 3, 4):
            if counts[(fc, svc)] == 0:
                out.append((svc, fc))
    return sorted(out, key=lambda x: (x[0], x[1]))


def gaps_class_1(vault: Path | None = None) -> list[str]:
    """Service names with no fault-1-* vault folder."""
    counts = counts_by_fault_type_and_service(vault)
    return sorted(svc for svc in CHAOS_CLASS_1_SERVICES if counts[(1, svc)] == 0)


def format_gap_report(vault: Path | None = None) -> str:
    vault = vault or default_vault_dir()
    lines = [f"Vault: {vault}", ""]
    g1 = gaps_class_1(vault)
    lines.append(f"Class 1 gaps ({len(g1)}): {', '.join(g1) or '(none)'}")
    g234 = gaps_class_234(vault)
    lines.append(f"Class 2–4 gaps ({len(g234)}):")
    for svc, fc in g234:
        lines.append(f"  - {svc} type {fc}")
    if not g234:
        lines.append("  (none)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_gap_report())
