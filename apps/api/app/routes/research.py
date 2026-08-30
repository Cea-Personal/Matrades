"""Autonomous research-cycle endpoints with read-only legacy selection history."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.research import DEFAULT_CATEGORIES, run_research_cycle
from modules.identity.authorization import Actor, Role
from modules.research.matrix import ALL_LANES
from modules.research.models import MarketCategory
from modules.research.scheduling import default_schedule, next_run_at
from packages.shared.config import settings
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/research", tags=["Research"])


class ResearchRunRequest(BaseModel):
    account_id: UUID
    market_categories: list[MarketCategory] = Field(
        default_factory=lambda: list(DEFAULT_CATEGORIES), min_length=1
    )


class SelectionInput(BaseModel):
    action: str = "APPROVE"
    category: MarketCategory | None = None
    instrument: str | None = Field(default=None, min_length=2, max_length=32)
    reason: str | None = Field(default=None, max_length=1000)


def _run_data(payload: ResearchRunRequest, trigger: str) -> dict:
    return {
        "account_id": str(payload.account_id),
        "market_categories": [item.value for item in dict.fromkeys(payload.market_categories)],
        "matrix_version": 1,
        "lanes": [lane.model_dump(mode="json") for lane in ALL_LANES],
        "trigger": trigger,
        "candidates": [],
        "missing_categories": [],
        "degraded_reasons": [],
    }


def _dispatch(run_id: UUID) -> None:
    # A short delay lets the request transaction commit before the worker reads it.
    run_research_cycle.apply_async(args=[str(run_id)], countdown=1)


@router.get("/schedule")
async def research_schedule(
    _: Annotated[Actor, Depends(current_actor)],
) -> dict:
    schedule = default_schedule(
        enabled=settings.research_schedule_enabled,
        run_at=f"{settings.research_schedule_hour_utc:02d}:{settings.research_schedule_minute_utc:02d}",
    )
    next_run = next_run_at(schedule)
    return {
        "enabled": settings.research_schedule_enabled,
        "timezone": "UTC",
        "next_run_at": next_run.isoformat() if next_run else None,
        "scope": "PER_ACCOUNT",
        "scheduler_interval_seconds": 60,
        "default_schedule": schedule,
        "market_categories": [item.value for item in DEFAULT_CATEGORIES],
    }


@router.get("/runs")
async def list_runs(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [x.public() for x in await ResourceStore(db).list("research_run", actor.owner_id)]


@router.get("/artifacts")
async def list_research_artifacts(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    account_id: Annotated[UUID | None, Query()] = None,
):
    records = await ResourceStore(db).list("research_run", actor.owner_id)
    return [
        {
            "run_id": str(item.id),
            "account_id": item.data.get("account_id"),
            "cycle_type": "market_research",
            "state": item.state,
            "completed_at": item.data.get("completed_at") or item.updated_at.isoformat(),
            **item.data["artifact"],
        }
        for item in records
        if item.data.get("artifact")
        and (account_id is None or item.data.get("account_id") == str(account_id))
    ]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def run_research(
    payload: ResearchRunRequest,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    account = await store.get("account", payload.account_id, actor.owner_id)
    if account is None or account.state == "DELETED":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    record = await store.create(
        "research_run",
        actor.owner_id,
        _run_data(payload, "MANUAL"),
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="research.queued_typed_matrix",
    )
    _dispatch(record.id)
    return record.public()


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await ResourceStore(db).get("research_run", run_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return item.public()


@router.post("/runs/{run_id}/decisions")
async def decide_selection(
    run_id: UUID,
    payload: SelectionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    run = await store.get("research_run", run_id, actor.owner_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    action = payload.action.upper()
    if action == "RERUN":
        rerun_request = ResearchRunRequest(
            account_id=UUID(str(run.data["account_id"])),
            market_categories=run.data.get(
                "market_categories", [item.value for item in DEFAULT_CATEGORIES]
            ),
        )
        cloned = await store.create(
            "research_run",
            actor.owner_id,
            {**_run_data(rerun_request, "RERUN"), "rerun_of": str(run.id)},
            state="QUEUED",
            actor_id=actor.actor_id,
            event_type="research.queued",
        )
        _dispatch(cloned.id)
        return cloned.public()

    raise HTTPException(
        status.HTTP_410_GONE,
        "research candidates progress autonomously; manual selection writes are retired",
    )


@router.get("/selections")
async def list_selections(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("market_selection", actor.owner_id)
    return [x.public() for x in records]
