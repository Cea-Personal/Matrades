from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from traderx_api.routes.access import authenticated_operation_context, operator_context
from traderx_api.routes.identity import AuthenticationContext

router = APIRouter(
    prefix="/paper", tags=["Paper Trading"], dependencies=[Depends(authenticated_operation_context)]
)
Operator = Annotated[AuthenticationContext, Depends(operator_context)]


class PaperRunCommand(BaseModel):
    strategy_version_id: str
    evidence_manifest_hash: str


@router.post("/runs", status_code=202)
def start_paper_run(
    payload: PaperRunCommand,
    _: Operator,
    idempotency_key: str = Header(alias="Idempotency-Key"),
) -> dict[str, object]:
    return {
        "job_type": "paper_run",
        "strategy_version_id": payload.strategy_version_id,
        "idempotency_key": idempotency_key,
    }


@router.get("/runs/{paper_run_id}")
def paper_run(paper_run_id: str) -> dict[str, object]:
    return {"id": paper_run_id, "state": "RUNNING", "positions": [], "comparison": None}
