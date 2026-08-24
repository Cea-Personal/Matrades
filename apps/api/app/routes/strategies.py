from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from modules.backtesting.ledger import TradeResult, metrics
from modules.backtesting.promotion import promotable
from modules.backtesting.stress import monte_carlo
from modules.backtesting.validation import walk_forward
from modules.identity.authorization import Actor, Role
from modules.strategies.fingerprints import fingerprint
from modules.strategies.lifecycle import StrategyState, transition
from modules.strategies.similarity import compare
from packages.shared.store import ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin

router = APIRouter(prefix="/strategies", tags=["Strategies"])


class DraftInput(BaseModel):
    origin: StrategyOrigin
    input_text: str | None = None
    specification: StrategySpecification | None = None


class ValidationTrade(BaseModel):
    pnl: Decimal
    risk: Decimal
    mae: Decimal = Decimal("0")
    mfe: Decimal = Decimal("0")
    instrument: str | None = None
    regime: str | None = None
    session: str | None = None


class ValidationInput(BaseModel):
    trades: list[ValidationTrade]
    chronological_returns: list[float]
    costs_applied: bool = True
    point_in_time_safe: bool = True
    out_of_sample_passed: bool
    policy_passed: bool
    paper_passed: bool


class TransitionInput(BaseModel):
    target: StrategyState


@router.get("")
async def list_strategies(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_draft", actor.owner_id)
    return [x.public() for x in records]


@router.post("/drafts", status_code=status.HTTP_201_CREATED)
async def create_draft(
    payload: DraftInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    data = {
        "origin": payload.origin,
        "input_text": payload.input_text,
        "specification": (
            payload.specification.model_dump(mode="json") if payload.specification else None
        ),
        "revision": 1,
        "lifecycle_state": StrategyState.DRAFT,
        "provenance": {
            "actor_id": str(actor.actor_id),
            "origin": payload.origin,
            "accepted_suggestions": [],
        },
    }
    item = await ResourceStore(db).create(
        "strategy_draft",
        actor.owner_id,
        data,
        state=StrategyState.DRAFT,
        actor_id=actor.actor_id,
        event_type="strategy_draft.created",
    )
    return item.public()


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
        raise HTTPException(status.HTTP_409_CONFLICT, "active strategy rules are immutable")
    data = {
        **item.data,
        "specification": specification.model_dump(mode="json"),
        "revision": int(item.data.get("revision", 1)) + 1,
    }
    updated = await store.update(
        item, data, actor_id=actor.actor_id, event_type="strategy_rule.revised"
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
    if raw_specification is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "strategy is incomplete")
    specification = StrategySpecification.model_validate(raw_specification)
    identity = fingerprint(specification)
    for existing in await store.list("strategy_version", actor.owner_id):
        if existing.data.get("fingerprint") == identity:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"message": "exact canonical duplicate", "existing_id": str(existing.id)},
            )
    version = await store.create(
        "strategy_version",
        actor.owner_id,
        {
            "strategy_id": str(draft.id),
            "strategy_version": 1,
            "specification": specification.model_dump(mode="json"),
            "fingerprint": identity,
            "artifact_version": "strategy-evaluator-v1",
            "origin": draft.data["origin"],
            "lifecycle_state": StrategyState.SPECIFIED,
        },
        state=StrategyState.SPECIFIED,
        actor_id=actor.actor_id,
        event_type="strategy_version.created",
    )
    await store.update(
        draft,
        {**draft.data, "lifecycle_state": StrategyState.SPECIFIED, "version_id": str(version.id)},
        state=StrategyState.SPECIFIED,
        actor_id=actor.actor_id,
        event_type="strategy_completeness.evaluated",
    )
    return version.public()


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


@router.post("/{strategy_id}/validate")
async def validate_strategy(
    strategy_id: UUID,
    payload: ValidationInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    trade_metrics = metrics(
        [TradeResult(item.pnl, item.risk, item.mae, item.mfe) for item in payload.trades]
    )
    try:
        walk_forward_result = walk_forward(payload.chronological_returns)
        walk_forward_passed = walk_forward_result["worst"] >= 0
    except ValueError:
        walk_forward_result = {"mean": 0.0, "worst": 0.0}
        walk_forward_passed = False
    stress_result = monte_carlo(payload.chronological_returns)
    gates = {
        "backtest": bool(payload.trades) and payload.costs_applied and payload.point_in_time_safe,
        "out_of_sample": payload.out_of_sample_passed,
        "walk_forward": walk_forward_passed,
        "stress": stress_result["p05"] >= 0,
        "policy": payload.policy_passed,
        "paper": payload.paper_passed,
    }
    evidence = await store.create(
        "strategy_validation",
        actor.owner_id,
        {
            "strategy_version_id": str(strategy.id),
            "metrics": {key: str(value) for key, value in trade_metrics.items()},
            "attribution": [
                {
                    "instrument": item.instrument,
                    "regime": item.regime,
                    "session": item.session,
                    "pnl": str(item.pnl),
                }
                for item in payload.trades
            ],
            "walk_forward": walk_forward_result,
            "monte_carlo": stress_result,
            "gates": gates,
            "promotable": promotable(gates),
        },
        state="PASSED" if promotable(gates) else "FAILED",
        actor_id=actor.actor_id,
        event_type="validation_stage.completed",
    )
    return evidence.public()


@router.post("/promote/{strategy_id}")
async def promote(
    strategy_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    validations = await store.list("strategy_validation", actor.owner_id)
    evidence = next(
        (
            item
            for item in validations
            if item.data.get("strategy_version_id") == str(strategy.id)
            and item.data.get("promotable")
        ),
        None,
    )
    if evidence is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "all validation and paper gates must pass")
    updated = await store.update(
        strategy,
        {**strategy.data, "lifecycle_state": StrategyState.APPROVED},
        state=StrategyState.APPROVED,
        actor_id=actor.actor_id,
        event_type="strategy.promotion_decided",
    )
    return updated.public()
