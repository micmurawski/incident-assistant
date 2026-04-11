"""Resolve repository root so paths work on any clone (e.g. o8s vs incident-assistant on EC2)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Override auto-detection when the repo lives outside the default layout:
#   export O8S_ROOT=/home/ec2-user/incident-assistant
# Aliases: INCIDENT_ASSISTANT_ROOT, REPO_ROOT
_ENV_KEYS = ("O8S_ROOT", "INCIDENT_ASSISTANT_ROOT", "REPO_ROOT")


@lru_cache
def get_repo_root() -> Path:
    """Directory that contains ``agent/pyproject.toml``, ``services/``, ``api_key.json``, etc."""
    for key in _ENV_KEYS:
        raw = os.environ.get(key)
        if raw:
            return Path(raw).expanduser().resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "agent" / "pyproject.toml").is_file():
            return p
    raise RuntimeError(
        "Cannot find repository root. Set O8S_ROOT (or INCIDENT_ASSISTANT_ROOT or REPO_ROOT) "
        "to the directory that contains agent/pyproject.toml."
    )


def api_key_path() -> Path:
    return get_repo_root() / "api_key.json"


def workspace_dir() -> Path:
    return get_repo_root() / "workspace"


def robot_shop_dir() -> Path:
    return get_repo_root() / "services" / "robot-shop"


def fault_vault_dir() -> Path:
    return get_repo_root() / "agent" / "fault_generator" / "fault-vault"
