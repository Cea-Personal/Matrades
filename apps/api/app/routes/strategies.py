"""AI strategy research, approval, canonicalization, and validation endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.strategies import generate_strategy_draft, run_strategy_backtest
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import find_connection, resolve_connection
from modules.identity.authorization import Actor, Role
from modules.knowledge.ingestion import build_source_data
from modules.strategies.compiler import compile_strategy
from modules.strategies.evidence import resolve_approved_candidate
from modules.strategies.fingerprints import fingerprint
from modules.strategies.lifecycle import StrategyState, transition
from modules.strategies.similarity import compare
from packages.shared.config import settings
from packages.shared.store import ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin

router = APIRouter(prefix="/strategies", tags=["Strategies"])


class DraftInput(BaseModel):
    origin: StrategyOrigin
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def assisted_description(self) -> DraftInput:
        if self.origin == StrategyOrigin.AI_ASSISTED and not (self.description or "").strip():
            raise ValueError("AI-assisted strategy creation requires a human description")
        return self


class StrategyProposalDecision(BaseModel):
    action: str
    reason: str | None = Field(default=None, max_length=1000)


class BacktestInput(BaseModel):
    connection_id: UUID
    instrument: str = Field(min_length=2, max_length=32)
    start_at: AwareDatetime
    end_at: AwareDatetime
    timeframe: str = "1h"
    initial_equity: Decimal = Field(default=Decimal("10000"), gt=0)
    spread: Decimal = Field(default=Decimal("0"), ge=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal = Field(default=Decimal("0"), ge=0)
    max_daily_loss: Decimal = Field(default=Decimal("1000000"), gt=0)
    max_total_loss: Decimal = Field(default=Decimal("1000000"), gt=0)

    @model_validator(mode="after")
    def chronological_window(self) -> BacktestInput:
        if self.start_at >= self.end_at:
            raise ValueError("backtest start must be before end")
        if self.timeframe not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            raise ValueError("unsupported timeframe")
        return self


class TransitionInput(BaseModel):
    target: StrategyState


def _dispatch_generation(run_id: UUID) -> None:
    generate_strategy_draft.apply_async(args=[str(run_id)], countdown=1)


def _dispatch_backtest(run_id: UUID) -> None:
    run_strategy_backtest.apply_async(args=[str(run_id)], countdown=1)


async def _resolve_strategy_basis(db: AsyncSession, owner_id: UUID) -> dict[str, str]:
    store = ResourceStore(db)
    selections = [
        item for item in await store.list("market_selection", owner_id) if item.state == "APPROVED"
    ]
    if not selections:
        raise ValueError("approve a fresh autonomous market research selection first")
    selection = selections[0]
    research_run = await store.get("research_run", UUID(str(selection.data["run_id"])), owner_id)
    if research_run is None:
        raise ValueError("the approved market research run is unavailable")
    candidate = resolve_approved_candidate(
        selection.data,
        research_run.data,
        now=datetime.now(UTC),
        max_age=timedelta(hours=settings.strategy_research_max_market_age_hours),
    )
    provider = (
        ConnectionProvider.COINBASE
        if candidate.category == "CRYPTO"
        else ConnectionProvider.TWELVE_DATA
    )
    connection = await find_connection(db, owner_id, provider)
    if connection is None:
        raise ValueError(f"configure an active {provider.value} historical data connection first")
    account = await store.get("account", UUID(candidate.account_id), owner_id)
    if account is None or account.state == "DELETED":
        raise ValueError("the market research account is unavailable")
    return {
        "market_selection_id": str(selection.id),
        "market_research_run_id": str(research_run.id),
        "account_id": candidate.account_id,
        "instrument": candidate.instrument,
        "category": candidate.category,
        "market_observed_at": candidate.fingerprint.observed_at.isoformat(),
        "historical_connection_id": str(connection.id),
        "historical_provider": provider.value,
    }


@router.get("")
async def list_strategies(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_draft", actor.owner_id)
    return [item.public() for item in records]


@router.get("/versions")
async def list_strategy_versions(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_version", actor.owner_id)
    return [item.public() for item in records]


@router.get("/backtests")
async def list_backtests(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_backtest", actor.owner_id)
    return [item.public() for item in records]


@router.get("/research-artifacts")
async def list_strategy_research_artifacts(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    records = [
        *await store.list("strategy_research_run", actor.owner_id),
        *await store.list("strategy_backtest", actor.owner_id),
    ]
    return [
        {
            "run_id": str(item.id),
            "cycle_type": (
                "strategy_research" if item.kind == "strategy_research_run" else "strategy_backtest"
            ),
            "state": item.state,
            "completed_at": item.data.get("completed_at"),
            **item.data["artifact"],
        }
        for item in records
        if item.data.get("artifact")
    ]


@router.get("/research-context")
async def strategy_research_context(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        basis = await _resolve_strategy_basis(db, actor.owner_id)
    except (KeyError, LookupError, RuntimeError, ValueError) as exc:
        return {"ready": False, "reason": str(exc)}
    return {"ready": True, "reason": None, **basis}


@router.post("/drafts", status_code=status.HTTP_202_ACCEPTED)
async def create_draft(
    payload: DraftInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    try:
        basis = await _resolve_strategy_basis(db, actor.owner_id)
    except (KeyError, LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    draft = await store.create(
        "strategy_draft",
        actor.owner_id,
        {
            "origin": payload.origin.value,
            "description": payload.description,
            "specification": None,
            "proposed_specification": None,
            "research_basis": basis,
            "revision": 1,
            "lifecycle_state": "QUEUED",
            "provenance": {
                "actor_id": str(actor.actor_id),
                "origin": payload.origin.value,
                "human_approval": None,
            },
        },
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="strategy_draft.created",
    )
    run = await store.create(
        "strategy_research_run",
        actor.owner_id,
        {
            "draft_id": str(draft.id),
            "origin": payload.origin.value,
            "description": payload.description,
            "trigger": "USER",
            **basis,
        },
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="strategy_research.queued",
    )
    await store.update(
        draft,
        {**draft.data, "research_run_id": str(run.id)},
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="strategy_research.linked",
    )
    await db.commit()
    _dispatch_generation(run.id)
    return draft.public()


@router.post("/drafts/{draft_id}/proposal-decision")
async def decide_strategy_proposal(
    draft_id: UUID,
    payload: StrategyProposalDecision,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    draft = await store.get("strategy_draft", draft_id, actor.owner_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy draft not found")
    if draft.state != "AWAITING_STRATEGY_APPROVAL":
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy is not awaiting approval")
    action = payload.action.upper()
    if action == "REJECT":
        updated = await store.update(
            draft,
            {
                **draft.data,
                "lifecycle_state": "REJECTED",
                "decision_reason": payload.reason,
                "provenance": {
                    **draft.data.get("provenance", {}),
                    "human_approval": "REJECTED",
                    "decision_actor_id": str(actor.actor_id),
                },
            },
            state="REJECTED",
            actor_id=actor.actor_id,
            event_type="strategy_suggestion.rejected",
        )
        return updated.public()
    if action != "APPROVE":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported decision")
    raw_proposal = draft.data.get("proposed_specification")
    specification = StrategySpecification.model_validate(raw_proposal)
    updated = await store.update(
        draft,
        {
            **draft.data,
            "specification": specification.model_dump(mode="json"),
            "lifecycle_state": StrategyState.DRAFT,
            "decision_reason": payload.reason,
            "provenance": {
                **draft.data.get("provenance", {}),
                "human_approval": "APPROVED",
                "decision_actor_id": str(actor.actor_id),
                "approved_at": datetime.now(UTC).isoformat(),
            },
        },
        state=StrategyState.DRAFT,
        actor_id=actor.actor_id,
        event_type="strategy_suggestion.accepted",
    )
    return updated.public()


@router.put("/drafts/{draft_id}")
async def save_draft(
    draft_id: UUID,
    specification: StrategySpecification,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("strategy_draft", draft_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy draft not found")
    if item.state not in {StrategyState.DRAFT, StrategyState.SPECIFIED}:
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy proposal must be approved first")
    if specification.origin.value != item.data.get("origin"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "strategy origin is immutable")
    updated = await store.update(
        item,
        {
            **item.data,
            "specification": specification.model_dump(mode="json"),
            "revision": int(item.data.get("revision", 1)) + 1,
        },
        actor_id=actor.actor_id,
        event_type="strategy_rule.revised",
    )
    return updated.public()


@router.post("/similarity")
async def similarity(
    left: StrategySpecification,
    right: StrategySpecification,
    _: Annotated[Actor, Depends(current_actor)],
):
    result = compare(left, right)
    return {
        **result,
        "classification": (
            "EXACT_DUPLICATE"
            if result["exact"]
            else "STRUCTURAL_VARIANT"
            if result["structural"] >= 0.7
            else "DISTINCT"
        ),
        "allowed_actions": ["REVIEW_EXISTING", "BRANCH_VERSION", "KEEP_DISTINCT"],
    }


@router.post("/submit/{draft_id}")
async def submit(
    draft_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    draft = await store.get("strategy_draft", draft_id, actor.owner_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy draft not found")
    raw_specification = draft.data.get("specification")
    if (
        raw_specification is None
        or draft.data.get("provenance", {}).get("human_approval") != "APPROVED"
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "approved strategy required")
    specification = StrategySpecification.model_validate(raw_specification)
    identity = fingerprint(specification)
    for existing in await store.list("strategy_version", actor.owner_id):
        if existing.data.get("fingerprint") == identity:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"message": "exact canonical duplicate", "existing_id": str(existing.id)},
            )
    compiled = compile_strategy(specification)
    version = await store.create(
        "strategy_version",
        actor.owner_id,
        {
            "strategy_id": str(draft.id),
            "strategy_version": 1,
            "specification": specification.model_dump(mode="json"),
            "fingerprint": identity,
            "artifact_version": "strategy-evaluator-v1",
            "generated_code": compiled.generated_code,
            "generated_code_language": "python",
            "artifact_hash": compiled.artifact_hash,
            "origin": draft.data["origin"],
            "lifecycle_state": StrategyState.SPECIFIED,
        },
        state=StrategyState.SPECIFIED,
        actor_id=actor.actor_id,
        event_type="strategy_version.created",
    )
    strategy_content = (
        f"Strategy: {specification.name}\n"
        f"Family: {specification.family.value}\n"
        f"Origin: {specification.origin.value}\n\n"
        f"Specification:\n{specification.model_dump_json(indent=2)}\n\n"
        f"Generated evaluator code:\n{compiled.generated_code}"
    )
    strategy_source = await store.create(
        "knowledge_source",
        actor.owner_id,
        {
            **build_source_data(
                name=f"Generated strategy — {specification.name}",
                content=strategy_content,
                media_type="text/plain",
                category="strategies",
                tags=["generated-strategy", specification.family.value, specification.origin.value],
                source_kind="GENERATED_STRATEGY",
                external_id=str(version.id),
            ),
            "linked_strategy_version_id": str(version.id),
        },
        state="ACTIVE",
        actor_id=actor.actor_id,
        event_type="strategy_knowledge.indexed",
    )
    await store.update(
        version,
        {**version.data, "knowledge_source_id": str(strategy_source.id)},
        actor_id=actor.actor_id,
        event_type="strategy_knowledge.linked",
    )
    await store.update(
        draft,
        {**draft.data, "lifecycle_state": StrategyState.SPECIFIED, "version_id": str(version.id)},
        state=StrategyState.SPECIFIED,
        actor_id=actor.actor_id,
        event_type="strategy_completeness.evaluated",
    )
    return version.public()


@router.post("/{strategy_id}/backtests", status_code=status.HTTP_202_ACCEPTED)
async def create_backtest(
    strategy_id: UUID,
    payload: BacktestInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    try:
        connection = await resolve_connection(db, actor.owner_id, payload.connection_id)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if connection.profile.provider not in {
        ConnectionProvider.TWELVE_DATA,
        ConnectionProvider.COINBASE,
    }:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "backtests require a Twelve Data or Coinbase connection",
        )
    record = await store.create(
        "strategy_backtest",
        actor.owner_id,
        {
            "strategy_version_id": str(strategy_id),
            **payload.model_dump(mode="json"),
            "trigger": "USER",
        },
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="backtest.queued",
    )
    await db.commit()
    _dispatch_backtest(record.id)
    return record.public()


@router.post("/{strategy_id}/transitions")
async def transition_strategy(
    strategy_id: UUID,
    payload: TransitionInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    item = await store.get("strategy_version", strategy_id, actor.owner_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    try:
        target = transition(StrategyState(item.state), payload.target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    updated = await store.update(
        item,
        {**item.data, "lifecycle_state": target},
        state=target,
        actor_id=actor.actor_id,
        event_type="strategy.lifecycle_transitioned",
    )
    return updated.public()


@router.post("/promote/{strategy_id}")
async def promote(
    strategy_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await ResourceStore(db).get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "backtest validation alone cannot promote; paper-trading evidence is still required",
    )
