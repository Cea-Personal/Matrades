from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter(prefix="/paper", tags=["Paper Trading"])


class PaperRunCommand(BaseModel):
    strategy_version_id: str
    evidence_manifest_hash: str


@router.post("/runs", status_code=202)
def start_paper_run(
    payload: PaperRunCommand, idempotency_key: str = Header(alias="Idempotency-Key")
) -> dict[str, object]:
    return {
        "job_type": "paper_run",
        "strategy_version_id": payload.strategy_version_id,
        "idempotency_key": idempotency_key,
    }


@router.get("/runs/{paper_run_id}")
def paper_run(paper_run_id: str) -> dict[str, object]:
    return {"id": paper_run_id, "state": "RUNNING", "positions": [], "comparison": None}
