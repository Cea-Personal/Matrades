from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.paper.evaluate", bind=True, acks_late=True)
def evaluate_paper_run(self, paper_run_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"paper_run_id": paper_run_id, "status": "QUEUED_FOR_CHECKPOINTED_EVALUATION"}
