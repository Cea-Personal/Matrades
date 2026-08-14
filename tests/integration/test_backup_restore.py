import base64
import os
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from traderx.integrations.crypto import SecretBox
from traderx.shared.recovery import (
    RecoveryManifest,
    build_recovery_manifest,
    verify_recovery_manifest,
)


def test_encrypted_backup_payload_restores_with_authenticated_envelope() -> None:
    box = SecretBox(base64.urlsafe_b64encode(os.urandom(32)).decode())
    envelope = box.encrypt({"backup": "manifest"}, aad="backup:1")
    assert box.decrypt(envelope) == {"backup": "manifest"}


def test_encrypted_restore_verifies_evidence_and_recovers_outbox_and_jobs_fail_closed() -> None:
    records = {
        "audit_events": [
            {"id": "audit-1", "action": "risk.lockdown", "integrity_hash": "audit-hash"}
        ],
        "journal_entries": [
            {"id": "journal-1", "evidence_hash": "journal-hash", "net_pnl": "25.00"}
        ],
        "active_market_assignments": [
            {"id": "assignment-1", "instrument_id": "instrument-1", "state": "ACTIVE"}
        ],
    }
    manifest = build_recovery_manifest(
        records,
        outbox=[
            {"id": "event-1", "state": "PENDING"},
            {"id": "event-2", "state": "PUBLISHED"},
        ],
        jobs=[
            {"id": "job-1", "state": "PAUSED"},
            {"id": "job-2", "state": "COMPLETED"},
        ],
        created_at=datetime(2026, 8, 14, tzinfo=UTC),
    )
    box = SecretBox(base64.urlsafe_b64encode(os.urandom(32)).decode(), key_version="kms-v2")
    encrypted = box.encrypt(asdict(manifest), aad="backup:release-candidate-1")
    restored = RecoveryManifest(**box.decrypt(encrypted))
    plan = verify_recovery_manifest(restored, records)
    assert plan.pending_outbox_ids == ("event-1",)
    assert plan.resumable_jobs == {"job-1": "PAUSED"}
    assert plan.external_integrations_enabled is False

    tampered = {**records, "journal_entries": [{"id": "journal-1", "net_pnl": "25000"}]}
    with pytest.raises(ValueError, match="does not match"):
        verify_recovery_manifest(restored, tampered)
