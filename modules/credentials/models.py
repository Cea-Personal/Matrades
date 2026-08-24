from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ConnectionState(StrEnum):
    UNTESTED = "UNTESTED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


class CredentialVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    ciphertext: bytes
    nonce: bytes
    key_version: str
    masked_hint: str
    active: bool = True


class ProviderConnection(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    provider: str
    credential_id: UUID
    state: ConnectionState = ConnectionState.UNTESTED
