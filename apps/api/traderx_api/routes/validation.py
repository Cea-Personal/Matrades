from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter(prefix="/validation", tags=["Validation"])


class RunCommand(BaseModel):
    strategy_version_id: str
    manifest_hash: str


@router.post("/backtests", status_code=202)
def start_backtest(
    payload: RunCommand, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "job_type": "backtest",
        "strategy_version_id": payload.strategy_version_id,
        "manifest_hash": payload.manifest_hash,
        "idempotency_key": idempotency_key,
    }


@router.post("/runs", status_code=202)
def start_validation(
    payload: RunCommand, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "job_type": "validation",
        "strategy_version_id": payload.strategy_version_id,
        "manifest_hash": payload.manifest_hash,
        "idempotency_key": idempotency_key,
    }
