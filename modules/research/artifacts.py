"""Immutable timestamped filesystem archive for research-cycle evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ResearchArtifactReference:
    relative_path: str
    checksum: str
    manifest_name: str = "manifest.json"


class ResearchCycleArchive:
    ALLOWED_TYPES = {"market_research", "strategy_research", "strategy_backtest"}

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_cycle(
        self,
        *,
        owner_id: UUID,
        cycle_type: str,
        cycle_id: UUID,
        occurred_at: datetime,
        details: dict[str, Any],
    ) -> ResearchArtifactReference:
        if cycle_type not in self.ALLOWED_TYPES:
            raise ValueError("unsupported research cycle type")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("research cycle timestamp must be timezone-aware")
        timestamp = occurred_at.strftime("%Y%m%dT%H%M%S.%fZ")
        relative = (
            Path(str(owner_id))
            / cycle_type
            / occurred_at.strftime("%Y/%m/%d")
            / f"{timestamp}_{cycle_id}"
        )
        folder = (self.root / relative).resolve()
        if self.root not in folder.parents:
            raise ValueError("unsafe research artifact path")
        folder.mkdir(parents=True, exist_ok=True)
        manifest_path = folder / "manifest.json"
        base = {
            "cycle_id": str(cycle_id),
            "cycle_type": cycle_type,
            "owner_id": str(owner_id),
            "occurred_at": occurred_at.isoformat(),
            "details": details,
        }
        canonical = json.dumps(base, sort_keys=True, separators=(",", ":"), default=str)
        checksum = hashlib.sha256(canonical.encode()).hexdigest()
        manifest = {**base, "checksum": checksum}
        encoded = json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text())
            if existing.get("checksum") != checksum:
                raise FileExistsError("research artifact is immutable")
        else:
            manifest_path.write_text(encoded)
        return ResearchArtifactReference(relative.as_posix(), checksum)

