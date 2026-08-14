from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecoveryManifest:
    schema_version: str
    created_at: str
    record_counts: dict[str, int]
    evidence_checksums: dict[str, str]
    pending_outbox_ids: tuple[str, ...]
    resumable_jobs: dict[str, str]
    checksum: str


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    pending_outbox_ids: tuple[str, ...]
    resumable_jobs: dict[str, str]
    external_integrations_enabled: bool = False


def build_recovery_manifest(
    governed_records: dict[str, list[dict[str, object]]],
    *,
    outbox: list[dict[str, object]],
    jobs: list[dict[str, object]],
    created_at: datetime,
) -> RecoveryManifest:
    counts = {name: len(records) for name, records in sorted(governed_records.items())}
    checksums = {
        name: _digest(records) for name, records in sorted(governed_records.items())
    }
    pending = tuple(
        sorted(
            str(event["id"])
            for event in outbox
            if str(event.get("state")) in {"PENDING", "FAILED"}
        )
    )
    resumable = {
        str(job["id"]): str(job["state"])
        for job in sorted(jobs, key=lambda item: str(item["id"]))
        if str(job.get("state")) in {"QUEUED", "RUNNING", "PAUSED", "FAILED"}
    }
    unsigned = {
        "schema_version": "traderx-recovery-v1",
        "created_at": created_at.isoformat(),
        "record_counts": counts,
        "evidence_checksums": checksums,
        "pending_outbox_ids": pending,
        "resumable_jobs": resumable,
    }
    return RecoveryManifest(
        schema_version="traderx-recovery-v1",
        created_at=created_at.isoformat(),
        record_counts=counts,
        evidence_checksums=checksums,
        pending_outbox_ids=pending,
        resumable_jobs=resumable,
        checksum=_digest(unsigned),
    )


def verify_recovery_manifest(
    manifest: RecoveryManifest, governed_records: dict[str, list[dict[str, object]]]
) -> RecoveryPlan:
    unsigned = asdict(manifest)
    checksum = str(unsigned.pop("checksum"))
    if not hmac.compare_digest(checksum, _digest(unsigned)):
        raise ValueError("recovery manifest checksum does not match")
    counts = {name: len(records) for name, records in sorted(governed_records.items())}
    checksums = {
        name: _digest(records) for name, records in sorted(governed_records.items())
    }
    if counts != manifest.record_counts or checksums != manifest.evidence_checksums:
        raise ValueError("restored governed evidence does not match the backup manifest")
    return RecoveryPlan(tuple(manifest.pending_outbox_ids), dict(manifest.resumable_jobs))


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
