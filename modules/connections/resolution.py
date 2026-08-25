"""Owner-scoped connection and encrypted credential resolution for adapters."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.connections.models import ConnectionProfile, ConnectionProvider
from modules.credentials.vault import EnvelopeCipher
from packages.shared.config import get_settings
from packages.shared.store import ResourceRecord


@dataclass(frozen=True)
class ResolvedConnection:
    id: UUID
    profile: ConnectionProfile
    secret: str | None


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(get_settings().secret_key.get_secret_value().encode())


async def resolve_connection(
    session: AsyncSession, owner_id: UUID, connection_id: UUID
) -> ResolvedConnection:
    connection = await session.scalar(
        select(ResourceRecord).where(
            ResourceRecord.id == connection_id,
            ResourceRecord.kind == "connection",
            ResourceRecord.owner_id == owner_id,
            ResourceRecord.state != "DELETED",
        )
    )
    if connection is None:
        raise LookupError("connection not found")
    profile = ConnectionProfile.model_validate(
        {
            key: connection.data.get(key)
            for key in ConnectionProfile.model_fields
            if key in connection.data
        }
    )
    if not profile.active:
        raise RuntimeError("connection is disabled")
    secret: str | None = None
    if profile.credential_id is not None:
        credential = await session.scalar(
            select(ResourceRecord).where(
                ResourceRecord.id == profile.credential_id,
                ResourceRecord.kind == "credential",
                ResourceRecord.owner_id == owner_id,
                ResourceRecord.state != "DELETED",
            )
        )
        if credential is None:
            raise LookupError("credential not found")
        secret = _cipher().decrypt(owner_id, credential.data["envelope"])
    return ResolvedConnection(connection.id, profile, secret)


async def find_connection(
    session: AsyncSession, owner_id: UUID, provider: ConnectionProvider
) -> ResolvedConnection | None:
    records = list(
        (
            await session.scalars(
                select(ResourceRecord).where(
                    ResourceRecord.kind == "connection",
                    ResourceRecord.owner_id == owner_id,
                    ResourceRecord.state != "DELETED",
                )
            )
        ).all()
    )
    for record in records:
        if record.data.get("provider") == provider.value and record.data.get("active", True):
            return await resolve_connection(session, owner_id, record.id)
    return None
