from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AwareDateTime, utc_now


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID = Field(default_factory=uuid4)
    email: str
    password_hash: str
    email_verified: bool = False
    mfa_enabled: bool = False


class Session(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    created_at: AwareDateTime = Field(default_factory=utc_now)
    expires_at: AwareDateTime
    revoked_at: AwareDateTime | None = None
    step_up_at: AwareDateTime | None = None


class MfaEnrollment(BaseModel):
    user_id: UUID
    encrypted_secret: str
    verified: bool = False
    recovery_code_hashes: list[str] = []
