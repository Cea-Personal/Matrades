"""Autonomous research-cycle and HIL-1 selection endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.research import DEFAULT_CATEGORIES, run_research_cycle
from modules.identity.authorization import Actor, Role
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
):
    records = await ResourceStore(db).list("research_run", actor.owner_id)
    return [
        {
            "run_id": str(item.id),
            "cycle_type": "market_research",
            "state": item.state,
            "completed_at": item.data.get("completed_at"),
            **item.data["artifact"],
        }
        for item in records
        if item.data.get("artifact")
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
        event_type="research.queued",
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

    if run.state not in {"MARKETS_PENDING_APPROVAL", "DEGRADED"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "research run is not awaiting HIL-1")
    if action == "APPROVE" and run.state == "DEGRADED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "degraded research cannot be approved; rerun, replace, or select no trade",
        )

    selected = {
        str(item["category"]): str(item["instrument"]) for item in run.data.get("candidates", [])
    }
    if action == "REPLACE":
        if payload.category is None or not payload.instrument:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "category and instrument required"
            )
        selected[payload.category.value] = payload.instrument.upper()
    elif action == "NO_TRADE":
        selected = {}
    elif action != "APPROVE":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported HIL-1 action")

    selection = await store.create(
        "market_selection",
        actor.owner_id,
        {
            "run_id": str(run.id),
            "selected": selected,
            "action": action,
            "reason": payload.reason,
            "research_fingerprints": [
                item.get("fingerprint") for item in run.data.get("candidates", [])
            ],
        },
        state="NO_TRADE" if action == "NO_TRADE" else "APPROVED",
        actor_id=actor.actor_id,
        event_type=f"market_selection.{action.lower()}",
    )
    return selection.public()


@router.get("/selections")
async def list_selections(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("market_selection", actor.owner_id)
    return [x.public() for x in records]
