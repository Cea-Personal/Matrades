from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/accounts", tags=["Accounts and Risk"])


class AccountCommand(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    currency: str = Field(min_length=3, max_length=3)
    starting_balance: Decimal = Field(gt=0)


@router.get("")
def list_accounts() -> list[dict[str, object]]:
    return []


@router.post("", status_code=201)
def create_account(
    payload: AccountCommand, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "idempotency_key": idempotency_key,
        "name": payload.name,
        "currency": payload.currency.upper(),
        "status": "DRAFT",
    }


@router.get("/{account_id}/risk")
def current_risk(account_id: UUID, response: Response) -> dict[str, object]:
    response.headers["ETag"] = '"risk-0"'
    return {
        "account_id": str(account_id),
        "state": "LOCKDOWN",
        "capacity": 0,
        "quality": "UNKNOWN",
        "reason_codes": ["NO_VERIFIED_ACCOUNT_SNAPSHOT"],
    }


@router.put("/{account_id}/prop-profile")
def replace_prop_profile(
    account_id: UUID,
    payload: dict[str, object],
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "account_id": str(account_id),
        "version": if_match,
        "idempotency_key": idempotency_key,
        "accepted": True,
        "payload": payload,
    }


@router.put("/{account_id}/risk-policy")
def replace_risk_policy(
    account_id: UUID,
    payload: dict[str, object],
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "account_id": str(account_id),
        "version": if_match,
        "idempotency_key": idempotency_key,
        "accepted": True,
        "payload": payload,
    }
