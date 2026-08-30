"""Verification of MT5 bridge signatures against UI-managed credentials."""

from __future__ import annotations

import hashlib
import hmac
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProvider
from modules.credentials.vault import EnvelopeCipher
from packages.shared.config import get_settings
from packages.shared.store import ResourceRecord


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())


def _signed_payload(body: bytes, timestamp: str, nonce: str) -> bytes:
    return timestamp.encode() + b"." + nonce.encode() + b"." + body


async def verify_ui_managed_mt5_signature(
    session: AsyncSession,
    *,
    body: bytes,
    timestamp: str,
    nonce: str,
    signature: str,
    window: int = 30,
) -> UUID | None:
    """Return the matching active credential ID without exposing its secret."""
    try:
        if abs(time.time() - int(timestamp)) > window:
            return None
    except (TypeError, ValueError):
        return None

    records = list(
        (
            await session.scalars(
                select(ResourceRecord).where(
                    ResourceRecord.kind.in_(("connection", "credential")),
                    ResourceRecord.state != "DELETED",
                )
            )
        ).all()
    )
    linked_credential_ids: set[UUID] = set()
    for record in records:
        if record.kind != "connection":
            continue
        data = record.data
        if (
            data.get("provider") != ConnectionProvider.MT5_BRIDGE.value
            or not data.get("active", True)
            or not data.get("credential_id")
        ):
            continue
        try:
            linked_credential_ids.add(UUID(str(data["credential_id"])))
        except ValueError:
            continue

    signed = _signed_payload(body, timestamp, nonce)
    matched: UUID | None = None
    cipher = _cipher()
    for record in records:
        if record.kind != "credential" or record.id not in linked_credential_ids:
            continue
        if record.data.get("provider") != ConnectionProvider.MT5_BRIDGE.value:
            continue
        try:
            secret = cipher.decrypt(record.owner_id, record.data["envelope"])
        except Exception:  # noqa: BLE001, S112 - invalid envelopes are not authoritative
            continue
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            matched = record.id
    return matched
