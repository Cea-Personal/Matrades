from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("")
def jobs() -> dict[str, object]:
    return {"items": []}


@router.post("/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str) -> dict[str, object]:
    return {"job_id": job_id, "status": "CANCEL_REQUESTED_AT_SAFE_BOUNDARY"}
