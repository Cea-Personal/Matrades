"""Durable JSON-backed command aggregate helpers.

The API stores the typed command and its outbox intent in the same
``ResourceStore`` transaction. Workers lease by optimistic version so a
restart cannot dispatch the same command concurrently.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from packages.shared.outbox import OutboxRecord
from packages.shared.store import ResourceRecord, ResourceStore


async def persist_command(
    store: ResourceStore,
    *,
    owner_id: UUID,
    command: Any,
    actor_id: UUID | None = None,
) -> ResourceRecord:
    existing = await store.get("execution_command", command.id, owner_id)
    if existing is not None:
        if existing.data.get("idempotency_key") != command.idempotency_key:
            raise ValueError("command id is bound to a different idempotency identity")
        return existing
    for item in await store.list("execution_command", owner_id):
        if item.data.get("idempotency_key") != command.idempotency_key:
            continue
        if item.data.get("requested_postcondition") != command.requested_postcondition:
            raise ValueError("idempotency key is bound to a different command payload")
        return item
    record = await store.create(
        "execution_command",
        owner_id,
        command.model_dump(mode="json"),
        state=command.state.value,
        record_id=command.id,
        actor_id=actor_id,
        event_type="execution.command.queued",
    )
    store.session.add(
        OutboxRecord(
            event_id=UUID(str(command.id)),
            owner_id=owner_id,
            event_type="execution.command.queued",
            payload=json.dumps(command.model_dump(mode="json"), sort_keys=True).encode(),
        )
    )
    await store.session.flush()
    return record


async def lease_command(
    store: ResourceStore,
    *,
    owner_id: UUID,
    command_id: UUID,
    worker_id: str,
    lease_seconds: int = 30,
) -> ResourceRecord | None:
    record = await store.get("execution_command", command_id, owner_id)
    if record is None or record.state not in {"QUEUED", "AUTHORIZED"}:
        return None
    lease_until = datetime.now(UTC) + timedelta(seconds=max(5, lease_seconds))
    data = {
        **record.data,
        "state": "DISPATCHING",
        "lease": {"worker_id": worker_id, "expires_at": lease_until.isoformat()},
        "attempt_count": int(record.data.get("attempt_count", 0)) + 1,
    }
    return await store.update(
        record,
        data,
        state="DISPATCHING",
        expected_version=record.version,
        event_type="execution.command.leased",
        evidence={"worker_id": worker_id, "lease_expires_at": lease_until.isoformat()},
    )


def lease_expired(record: ResourceRecord, *, now: datetime | None = None) -> bool:
    lease = record.data.get("lease") or {}
    raw = lease.get("expires_at")
    if not raw:
        return True
    expires = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    observed = now or datetime.now(UTC)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= observed


__all__ = ["lease_command", "lease_expired", "persist_command"]
