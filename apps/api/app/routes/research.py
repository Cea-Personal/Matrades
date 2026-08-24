from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.analysis.context import context_features
from modules.analysis.daily_research import rank_session
from modules.analysis.models import RankedMarket
from modules.analysis.regime import classify
from modules.analysis.technical import indicators
from modules.identity.authorization import Actor, Role
from packages.shared.domain_types import utc_now
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/research", tags=["Research"])


class CandidateEvidence(BaseModel):
    instrument: str
    category: str
    closes: list[float] = Field(min_length=3)
    macro: float = Field(ge=-1, le=1)
    event_risk: float = Field(ge=0, le=1)
    sentiment: float = Field(ge=-1, le=1)
    positioning: float = Field(ge=-1, le=1)
    correlation: float = Field(ge=-1, le=1)
    fresh: bool = True
    source_version: str = "manual-v1"


class ResearchInput(BaseModel):
    candidates: list[CandidateEvidence]


class SelectionInput(BaseModel):
    action: str = "APPROVE"
    category: str | None = None
    instrument: str | None = None
    reason: str | None = None


def _rank(item: CandidateEvidence) -> RankedMarket:
    technical = indicators(item.closes)
    contextual = context_features(
        macro=item.macro,
        event_risk=item.event_risk,
        sentiment=item.sentiment,
        positioning=item.positioning,
        correlation=item.correlation,
    )
    agreement = 1 - min(1.0, abs(item.macro - item.sentiment) / 2)
    regime = classify(
        technical["momentum"] / max(abs(technical["mean"]), 1e-9),
        technical["volatility"] / max(abs(technical["mean"]), 1e-9),
        agreement,
    )
    score = (
        technical["momentum"] / max(abs(technical["mean"]), 1e-9)
        + contextual["macro"]
        + contextual["sentiment"]
        + contextual["positioning"]
        - contextual["event_risk"]
        - abs(contextual["correlation"]) * 0.25
    )
    return RankedMarket(
        instrument=item.instrument.upper(),
        category=item.category.lower(),
        score=round(score, 6),
        evidence=[
            f"regime={regime.value}",
            f"momentum={technical['momentum']:.6f}",
            f"volatility={technical['volatility']:.6f}",
            f"macro={item.macro:.2f}",
            f"sentiment={item.sentiment:.2f}",
            f"event_risk={item.event_risk:.2f}",
        ],
        fresh=item.fresh,
    )


@router.get("/runs")
async def list_runs(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [x.public() for x in await ResourceStore(db).list("research_run", actor.owner_id)]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def run_research(
    payload: ResearchInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ranked = [_rank(item) for item in payload.candidates]
    state, selected = rank_session(ranked)
    source_versions = {
        f"{item.category}:{item.instrument}": item.source_version for item in payload.candidates
    }
    data = {
        "state": state.value,
        "candidates": [item.model_dump(mode="json") for item in selected],
        "all_candidates": [item.model_dump(mode="json") for item in ranked],
        "source_versions": source_versions,
        "completed_at": utc_now().isoformat(),
        "degraded_reason": (
            "one or more critical observations are stale" if state.value == "DEGRADED" else None
        ),
    }
    record = await ResourceStore(db).create(
        "research_run",
        actor.owner_id,
        data,
        state=state.value,
        actor_id=actor.actor_id,
        event_type=f"research.{state.value.lower()}",
    )
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
        cloned = await store.create(
            "research_run",
            actor.owner_id,
            {**run.data, "state": "QUEUED", "rerun_of": str(run.id)},
            state="QUEUED",
            actor_id=actor.actor_id,
            event_type="research.queued",
        )
        return cloned.public()
    selected = {
        item["category"]: item["instrument"] for item in run.data.get("candidates", [])
    }
    if action == "REPLACE":
        if not payload.category or not payload.instrument:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "category and instrument required"
            )
        selected[payload.category.lower()] = payload.instrument.upper()
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
