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

    def read_manifest(self, *, owner_id: UUID, relative_path: str) -> dict[str, Any]:
        """Read one owner-scoped immutable manifest without permitting traversal."""
        candidate = (self.root / relative_path).resolve()
        owner_root = (self.root / str(owner_id)).resolve()
        if owner_root not in candidate.parents or candidate.name != "manifest.json":
            raise ValueError("unsafe research artifact path")
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileNotFoundError("research artifact manifest unavailable") from exc
        if payload.get("owner_id") != str(owner_id):
            raise ValueError("research artifact owner mismatch")
        return payload

    def list_manifests(self, *, owner_id: UUID) -> list[dict[str, Any]]:
        """List readable manifests for an owner, newest first."""
        owner_root = (self.root / str(owner_id)).resolve()
        if self.root not in owner_root.parents:
            raise ValueError("unsafe research artifact owner path")
        if not owner_root.exists():
            return []
        manifests: list[dict[str, Any]] = []
        for path in sorted(owner_root.glob("**/manifest.json"), reverse=True):
            try:
                relative = path.relative_to(self.root).as_posix()
                manifests.append(self.read_manifest(owner_id=owner_id, relative_path=relative))
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                continue
        return manifests
