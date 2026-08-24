from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RuleStatus(StrEnum):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class PropFirm(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str


class PropProgram(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    firm_id: UUID
    name: str


class PropRule(BaseModel):
    kind: str
    value: Decimal
    unit: str
    enforcement: str = "HARD"


class RuleSet(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    program_id: UUID
    version: int
    rules: list[PropRule]
    status: RuleStatus = RuleStatus.DRAFT
    source_reference: str | None = None


class GuardrailProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    account_id: UUID | None = None
    rules: list[PropRule]
    version: int = 1
