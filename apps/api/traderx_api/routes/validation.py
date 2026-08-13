from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/validation", tags=["Validation"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


class RunCommand(BaseModel):
    strategy_version_id: str
    manifest_hash: str


@router.post("/backtests", status_code=202)
def start_backtest(
    payload: RunCommand,
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "job_type": "backtest",
        "strategy_version_id": payload.strategy_version_id,
        "manifest_hash": payload.manifest_hash,
        "idempotency_key": idempotency_key,
    }


@router.post("/runs", status_code=202)
def start_validation(
    payload: RunCommand,
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "job_type": "validation",
        "strategy_version_id": payload.strategy_version_id,
        "manifest_hash": payload.manifest_hash,
        "idempotency_key": idempotency_key,
    }
