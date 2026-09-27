"""Read native role settings afresh; never cache an edited agent file."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

NATIVE_AGENTS_DIR = Path(__file__).resolve().parents[2] / ".codex" / "agents"
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


def load_native_agent(logical_id: str, directory: Path | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", logical_id):
        raise ValueError("invalid native agent role")
    path = (directory or NATIVE_AGENTS_DIR) / f"{logical_id}.toml"
    try:
        config = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Native agent configuration unavailable: {path.name}") from exc
    if config.get("name") != logical_id:
        raise ValueError(f"Native agent name does not match {path.name}")
    for field in ("model", "description", "developer_instructions"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError(f"Native agent {logical_id} requires {field}")
    if config.get("model_reasoning_effort") not in REASONING_EFFORTS:
        raise ValueError(f"Native agent {logical_id} has invalid reasoning effort")
    if config.get("sandbox_mode") != "read-only":
        raise ValueError(f"Native agent {logical_id} must be read-only")
    return config
