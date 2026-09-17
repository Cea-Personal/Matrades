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
from modules.backtesting.promotion import typed_promotable
from modules.connections.models import ConnectionProvider
from modules.connections.resolution import resolve_connection
from modules.identity.authorization import Actor, Role
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.openai_embeddings import embed_source_data
from modules.risk.authority import authoritative_risk_context
from modules.risk.engine import RiskEngine
from modules.risk.models import CandidateTrade, Direction
from modules.strategies.compiler import compile_strategy
from modules.strategies.fingerprints import fingerprint
from modules.strategies.lifecycle import StrategyState, transition
from modules.strategies.research_pipeline import resolve_strategy_basis
from modules.strategies.similarity import compare
from modules.trading.models import TradeConstruction
from modules.trading.trade_plans import build_trade_plan
from packages.shared.store import ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin

router = APIRouter(prefix="/strategies", tags=["Strategies"])


class DraftInput(BaseModel):
    origin: StrategyOrigin
    description: str | None = Field(default=None, max_length=5000)
    knowledge_source_id: UUID | None = None

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


class PaperTradingInput(BaseModel):
    observation_start: AwareDatetime
    observation_end: AwareDatetime
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def chronological_window(self) -> PaperTradingInput:
        if self.observation_start >= self.observation_end:
            raise ValueError("paper-trading observation window must be chronological")
        return self


class PaperEvidenceInput(BaseModel):
    trade_count: int = Field(ge=0)
    net_profit: Decimal
    profit_factor: Decimal = Field(ge=0)
    max_drawdown: Decimal = Field(ge=0)
    policy_passed: bool
    source: str = Field(min_length=3, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class TradePlanInput(BaseModel):
    """Current signal levels used to build a risk-validated, non-authorized plan."""

    entry: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profits: list[Decimal] | None = Field(default=None, min_length=1, max_length=5)
    invalidation: str | None = Field(default=None, min_length=3, max_length=1000)

    @model_validator(mode="after")
    def ordered_levels(self) -> TradePlanInput:
        if self.take_profits and any(item <= 0 for item in self.take_profits):
            raise ValueError("take-profit prices must be positive")
        return self


def _dispatch_generation(run_id: UUID) -> None:
    generate_strategy_draft.apply_async(args=[str(run_id)], countdown=1)


def _dispatch_backtest(run_id: UUID) -> None:
    run_strategy_backtest.apply_async(args=[str(run_id)], countdown=1)


async def _resolve_strategy_basis(db: AsyncSession, owner_id: UUID) -> dict[str, str]:
    return await resolve_strategy_basis(db, owner_id)


@router.get("")
async def list_strategies(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    market_research_run_id: UUID | None = None,
):
    records = await ResourceStore(db).list("strategy_draft", actor.owner_id)
    return [
        item.public()
        for item in records
        if market_research_run_id is None
        or item.data.get("research_basis", {}).get("market_research_run_id")
        == str(market_research_run_id)
    ]


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


@router.get("/paper-trading")
async def list_paper_trading_runs(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_paper_run", actor.owner_id)
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
    source = None
    if payload.knowledge_source_id is not None:
        source = await store.get("knowledge_source", payload.knowledge_source_id, actor.owner_id)
        if source is None or source.state != "ACTIVE":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "knowledge source not found")
        if source.data.get("source_kind") != "YOUTUBE_TRANSCRIPT":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "strategy extraction accepts indexed YouTube transcript sources only",
            )
        if not source.data.get("segments"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "the selected transcript has no indexed segments",
            )
    research_basis = {
        **basis,
        **(
            {
                "knowledge_source_id": str(source.id),
                "knowledge_source_name": source.data.get("name"),
                "knowledge_source_kind": source.data.get("source_kind"),
            }
            if source is not None
            else {}
        ),
    }
    draft = await store.create(
        "strategy_draft",
        actor.owner_id,
        {
            "origin": payload.origin.value,
            "description": payload.description,
            "specification": None,
            "proposed_specification": None,
            "research_basis": research_basis,
            "knowledge_source_id": str(source.id) if source is not None else None,
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
            **research_basis,
            "knowledge_source_id": str(source.id) if source is not None else None,
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
            "lifecycle_state": StrategyState.IMPLEMENTED,
            "validation_evidence": {"compiler": True},
            "strategy_pipeline": draft.data.get("strategy_pipeline", {}),
            "knowledge_source_id": draft.data.get("knowledge_source_id"),
            "transcript_evidence_refs": [
                item.get("reference_id")
                for item in draft.data.get("evidence_pack", {}).get("knowledge_context", [])
                if item.get("reference_id")
            ],
        },
        state=StrategyState.IMPLEMENTED,
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
    strategy_knowledge_data = await embed_source_data(
        db,
        actor.owner_id,
        build_source_data(
            name=f"Generated strategy — {specification.name}",
            content=strategy_content,
            media_type="text/plain",
            category="strategies",
            tags=["generated-strategy", specification.family.value, specification.origin.value],
            source_kind="GENERATED_STRATEGY",
            external_id=str(version.id),
        ),
    )
    strategy_source = await store.create(
        "knowledge_source",
        actor.owner_id,
        {
            **strategy_knowledge_data,
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
    await store.update(
        strategy,
        {**strategy.data, "lifecycle_state": StrategyState.BACKTESTING},
        state=StrategyState.BACKTESTING,
        actor_id=actor.actor_id,
        event_type="strategy.backtesting_started",
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
        if payload.target in {
            StrategyState.PAPER_TRADING,
            StrategyState.APPROVED,
            StrategyState.ACTIVE,
        }:
            raise ValueError("evidence-gated stages are advanced only by recorded validation work")
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


@router.post("/{strategy_id}/paper-trading", status_code=status.HTTP_202_ACCEPTED)
async def start_paper_trading(
    strategy_id: UUID,
    payload: PaperTradingInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Open a paper session only after the provider-backed validation gates pass."""
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    if strategy.state != StrategyState.VALIDATING:
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy is not ready for paper trading")
    evidence = dict(strategy.data.get("validation_evidence", {}))
    if not all(
        evidence.get(stage, False)
        for stage in ("backtest", "out_of_sample", "walk_forward", "stress", "policy")
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "all formal validation gates must pass first")
    existing = next(
        (
            item
            for item in await store.list("strategy_paper_run", actor.owner_id)
            if item.data.get("strategy_version_id") == str(strategy_id)
            and item.state in {"QUEUED", "RUNNING"}
        ),
        None,
    )
    if existing is not None:
        return existing.public()
    paper_run = await store.create(
        "strategy_paper_run",
        actor.owner_id,
        {
            "strategy_version_id": str(strategy_id),
            **payload.model_dump(mode="json"),
            "trigger": "VALIDATION_GATE",
            "evidence_class": "PAPER",
        },
        state="RUNNING",
        actor_id=actor.actor_id,
        event_type="strategy.paper_trading.started",
    )
    pipeline = {
        **strategy.data.get("strategy_pipeline", {}),
        "stages": {
            **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
            "paper_trading": "RUNNING",
        },
    }
    await store.update(
        strategy,
        {
            **strategy.data,
            "lifecycle_state": StrategyState.PAPER_TRADING,
            "strategy_pipeline": pipeline,
            "paper_run_id": str(paper_run.id),
        },
        state=StrategyState.PAPER_TRADING,
        actor_id=actor.actor_id,
        event_type="strategy.paper_trading.awaiting_evidence",
    )
    return paper_run.public()


@router.post("/{strategy_id}/paper-trading/{paper_run_id}/complete")
async def complete_paper_trading(
    strategy_id: UUID,
    paper_run_id: UUID,
    payload: PaperEvidenceInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record observed paper outcomes; the server, not the agent, decides the gate."""
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    paper_run = await store.get("strategy_paper_run", paper_run_id, actor.owner_id)
    if strategy is None or paper_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper-trading run not found")
    if paper_run.data.get("strategy_version_id") != str(strategy_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "paper run is linked to another strategy")
    if strategy.state != StrategyState.PAPER_TRADING or paper_run.state not in {
        "RUNNING",
        "QUEUED",
    }:
        raise HTTPException(status.HTTP_409_CONFLICT, "paper-trading run is not active")
    gates = {
        "minimum_trade_count": payload.trade_count >= 10,
        "positive_net_profit": payload.net_profit > 0,
        "profit_factor": payload.profit_factor >= 1,
        "policy": payload.policy_passed,
    }
    passed = all(gates.values())
    evidence = {**strategy.data.get("validation_evidence", {}), "paper": passed}
    pipeline = {
        **strategy.data.get("strategy_pipeline", {}),
        "stages": {
            **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
            "paper_trading": "PASSED" if passed else "FAILED",
            "approved_trade_plan": "READY_TO_CREATE" if passed else "BLOCKED",
        },
    }
    updated_run = await store.update(
        paper_run,
        {
            **paper_run.data,
            **payload.model_dump(mode="json"),
            "gates": gates,
            "completed_at": datetime.now(UTC).isoformat(),
        },
        state="PASSED" if passed else "FAILED",
        actor_id=actor.actor_id,
        event_type="strategy.paper_trading.completed",
    )
    updated_strategy = await store.update(
        strategy,
        {
            **strategy.data,
            "lifecycle_state": StrategyState.APPROVED if passed else StrategyState.DEGRADED,
            "validation_evidence": evidence,
            "strategy_pipeline": pipeline,
        },
        state=StrategyState.APPROVED if passed else StrategyState.DEGRADED,
        actor_id=actor.actor_id,
        event_type="strategy.paper_validation.completed",
    )
    return {
        "paper_run": updated_run.public(),
        "strategy": updated_strategy.public(),
        "gates": gates,
    }


@router.post("/{strategy_id}/trade-plans", status_code=status.HTTP_201_CREATED)
async def create_approved_trade_plan(
    strategy_id: UUID,
    payload: TradePlanInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a current, risk-validated Trade Plan without authorizing execution."""
    store = ResourceStore(db)
    strategy = await store.get("strategy_version", strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    if strategy.state != StrategyState.APPROVED or not strategy.data.get(
        "validation_evidence", {}
    ).get("paper"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "paper validation must approve the strategy first",
        )
    specification = StrategySpecification.model_validate(strategy.data["specification"])
    draft = await store.get(
        "strategy_draft", UUID(str(strategy.data["strategy_id"])), actor.owner_id
    )
    if draft is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy research draft is unavailable")
    setup = dict(draft.data.get("trade_setup") or {})
    raw_targets = payload.take_profits or [
        Decimal(str(item["price"]))
        for item in setup.get("take_profits", [])
        if isinstance(item, dict) and item.get("price") is not None
    ]
    entry = payload.entry or (Decimal(str(setup["entry"])) if setup.get("entry") else None)
    stop_loss = payload.stop_loss or (
        Decimal(str(setup["stop_loss"])) if setup.get("stop_loss") else None
    )
    invalidation = payload.invalidation or str(
        setup.get("invalidation") or "strategy invalidation"
    )
    if entry is None or stop_loss is None or not raw_targets:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a fresh strategy signal with entry, stop loss, and targets is required",
        )
    basis = dict(draft.data.get("research_basis", {}))
    required = ("account_id", "market_selection_id", "category")
    if any(not basis.get(key) for key in required):
        raise HTTPException(status.HTTP_409_CONFLICT, "typed market strategy basis is incomplete")
    typed = (
        specification.asset_class,
        specification.instrument_type,
        specification.quantity_unit,
        specification.venue_instrument_id,
        specification.specification_version_id,
    )
    if any(value is None for value in typed):
        raise HTTPException(status.HTTP_409_CONFLICT, "typed instrument identity is required")
    direction = (
        Direction.BUY
        if specification.trade_rules and specification.trade_rules.direction == "LONG"
        else Direction.SELL
    )
    distance = abs(entry - stop_loss)
    if distance <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "entry and stop loss must differ")
    candidate = CandidateTrade(
        instrument=specification.instruments[0],
        direction=direction,
        market_category=str(basis["category"]).lower(),
        requested_size=Decimal("1"),
        entry_price=entry,
        stop_loss=stop_loss,
        risk_per_unit=distance,
        asset_class=specification.asset_class,
        instrument_type=specification.instrument_type,
        venue_instrument_id=UUID(str(specification.venue_instrument_id)),
        specification_version_id=UUID(str(specification.specification_version_id)),
        quantity_unit=specification.quantity_unit,
    )
    try:
        context = await authoritative_risk_context(
            db, actor.owner_id, UUID(str(basis["account_id"])), candidate
        )
        risk = RiskEngine().evaluate(context, candidate)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    construction = TradeConstruction(
        instrument=candidate.instrument,
        direction=candidate.direction,
        entry=entry,
        stop_loss=stop_loss,
        targets=raw_targets,
        invalidation=invalidation,
        # Keep the construction structurally valid for a BLOCKED plan; the
        # builder replaces this with zero when risk authority hard-blocks it.
        approved_size=risk.approved_size if risk.approved_size > 0 else Decimal("1"),
        quantity_unit=specification.quantity_unit,
        asset_class=specification.asset_class,
        instrument_type=specification.instrument_type,
        venue_instrument_id=candidate.venue_instrument_id,
        specification_version_id=candidate.specification_version_id,
    )
    plan = build_trade_plan(
        owner_id=actor.owner_id,
        account_id=UUID(str(basis["account_id"])),
        construction=construction,
        strategy_version_id=strategy_id,
        market_fingerprint_id=UUID(str(basis["market_selection_id"])),
        risk=risk,
        evidence_refs=tuple(
            [f"strategy:{strategy_id}", *[str(item) for item in draft.data.get("evidence", [])]]
        ),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    record = await store.create(
        "trade_plan",
        actor.owner_id,
        plan.model_dump(mode="json"),
        state=plan.state.value,
        record_id=plan.id,
        actor_id=actor.actor_id,
        event_type="strategy.approved_trade_plan.created",
    )
    pipeline = {
        **strategy.data.get("strategy_pipeline", {}),
        "stages": {
            **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
            "approved_trade_plan": plan.state.value,
        },
    }
    await store.update(
        strategy,
        {**strategy.data, "approved_trade_plan_id": str(plan.id), "strategy_pipeline": pipeline},
        actor_id=actor.actor_id,
        event_type="strategy.approved_trade_plan.linked",
    )
    return record.public()


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
    evidence = dict(strategy.data.get("validation_evidence", {}))
    profile_complete = bool(strategy.data.get("specification")) and bool(
        strategy.data.get("artifact_hash")
    )
    if StrategyState(strategy.state) is not StrategyState.APPROVED or not typed_promotable(
        evidence, profile_complete=profile_complete
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "promotion requires complete compatible backtest, validation, policy, "
            "and paper evidence",
        )
    updated = await store.update(
        strategy,
        {**strategy.data, "lifecycle_state": StrategyState.ACTIVE},
        state=StrategyState.ACTIVE,
        actor_id=actor.actor_id,
        event_type="strategy.promoted_after_evidence",
    )
    return updated.public()
