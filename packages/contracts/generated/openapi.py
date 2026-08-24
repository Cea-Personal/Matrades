"""Generated boundary models for the V1 decision endpoints.

Source: specs/001-matrades-product-platform/contracts/openapi.yaml
"""
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class RiskDecision(StrEnum):
    PASS = "PASS"  # noqa: S105 - risk decision label, not a credential
    REDUCE_SIZE = "REDUCE_SIZE"
    HARD_BLOCK = "HARD_BLOCK"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] = {}


class CandidateRisk(BaseModel):
    instrument: str
    direction: str
    requested_size: Decimal
    entry_price: Decimal
    stop_loss: Decimal
