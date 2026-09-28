"""AI strategy research, approval, canonicalization, and validation endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import current_actor, get_db, require_roles
from apps.worker.app.tasks.strategies import generate_strategy_draft, run_strategy_backtest
from apps.worker.app.tasks.strategy_monitoring import evaluate_strategy
from modules.backtesting.basis import resolve_backtest_basis
from modules.backtesting.promotion import typed_promotable
from modules.connections.models import ConnectionProvider
from modules.identity.authorization import Actor, Role
from modules.knowledge.ingestion import build_source_data
from modules.knowledge.openai_embeddings import embed_source_data
from modules.policy.effective_limits import strictest_applicable
from modules.policy.models import ConstraintKind, Enforcement
from modules.research.sessions import weekend_close
from modules.risk.authority import authoritative_risk_context
from modules.risk.engine import RiskEngine
from modules.risk.live_terms import load_live_trade_terms
from modules.risk.models import CandidateTrade, Direction
from modules.strategies.autonomy import automation_policy
from modules.strategies.compiler import compile_strategy
from modules.strategies.fingerprints import fingerprint
from modules.strategies.lifecycle import StrategyState, transition
from modules.strategies.monitoring import ENGINE, paper_gates, validation_passed
from modules.strategies.performance import select_strategy, strategy_library
from modules.strategies.research_pipeline import latest_strategy_context, resolve_strategy_basis
from modules.strategies.similarity import compare
from modules.trading.models import TradeConstruction
from modules.trading.ticket import build_trade_ticket
from modules.trading.trade_plans import build_trade_plan
from packages.shared.store import ResourceRecord, ResourceStore
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin

router = APIRouter(prefix="/strategies", tags=["Strategies"])


async def _locked_version(db: AsyncSession, strategy_id: UUID, owner_id: UUID):
    """Serialize lifecycle changes with the recurring monitor."""
    return await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.id == strategy_id,
            ResourceRecord.kind == "strategy_version",
            ResourceRecord.owner_id == owner_id,
        )
        .with_for_update()
    )


class DraftInput(BaseModel):
    origin: StrategyOrigin
    market_selection_id: UUID
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
    connection_id: UUID | None = None
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
    model_config = ConfigDict(extra="forbid")
    duration_days: int = Field(default=30, ge=1, le=90)
    notes: str | None = Field(default=None, max_length=2000)


class PaperEvidenceInput(BaseModel):
    """Completion reviews persisted observations; client-supplied metrics are rejected."""

    model_config = ConfigDict(extra="forbid")


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


@router.get("")
async def list_strategies(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    market_research_run_id: UUID | None = None,
):
    store = ResourceStore(db)
    records = await store.list("strategy_draft", actor.owner_id)
    result = []
    for item in records:
        if market_research_run_id is not None and item.data.get("research_basis", {}).get(
            "market_research_run_id"
        ) != str(market_research_run_id):
            continue
        public = item.public()
        public.pop("trade_setup", None)
        if item.state == "NO_TRADE":
            public["state"] = "NO_QUALIFYING_STRATEGY"
        if not public.get("evidence_pack") and item.data.get("research_run_id"):
            run = await store.get(
                "strategy_research_run", UUID(item.data["research_run_id"]), actor.owner_id
            )
            if run is not None:
                public["evidence_pack"] = run.data.get("evidence_pack")
                public["failure"] = public.get("failure") or run.data.get("failure")
        result.append(public)
    return result


@router.get("/versions")
async def list_strategy_versions(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_version", actor.owner_id)
    result = []
    for item in records:
        public = item.public()
        try:
            basis, _connection = await resolve_backtest_basis(db, actor.owner_id, item)
            public["backtest_basis"] = {"ready": True, **basis}
        except (KeyError, LookupError, RuntimeError, ValueError) as exc:
            public["backtest_basis"] = {"ready": False, "reason": str(exc)}
        result.append(public)
    return result


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
    return [
        {
            key: value
            for key, value in item.public().items()
            if key not in {"candles", "entry_intents", "recent_candles", "news_contexts"}
        }
        for item in records
    ]


@router.get("/monitoring")
async def list_monitoring(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    records = await ResourceStore(db).list("strategy_version", actor.owner_id)
    return [
        {
            "id": str(item.id),
            "state": item.state,
            "name": item.data.get("specification", {}).get("name"),
            "instrument": (item.data.get("specification", {}).get("instruments") or [None])[0],
            "account_id": item.data.get("research_basis", {}).get("account_id"),
            "latest_signal": item.data.get("latest_signal"),
            "last_evaluated_at": item.data.get("last_evaluated_at"),
            "strategy_health": item.data.get("strategy_health"),
            "strategy_selection": item.data.get("strategy_selection"),
        }
        for item in records
        if item.state in {"PAPER_TRADING", "APPROVED", "ACTIVE", "SUSPENDED"}
    ]


@router.get("/library")
async def list_strategy_library(
    actor: Annotated[Actor, Depends(current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Owner-scoped strategy/regime evidence, recent windows and selection decisions."""
    return await strategy_library(ResourceStore(db), actor.owner_id)


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
    return await latest_strategy_context(db, actor.owner_id)


@router.post("/drafts", status_code=status.HTTP_202_ACCEPTED)
async def create_draft(
    payload: DraftInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    store = ResourceStore(db)
    context = await latest_strategy_context(db, actor.owner_id)
    selected = next(
        (
            item
            for item in context["selections"]
            if item["market_selection_id"] == str(payload.market_selection_id)
        ),
        None,
    )
    if selected is None or not selected["ready"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            selected["reason"]
            if selected
            else "choose a ready pair from the latest market research cycle",
        )
    basis = await resolve_strategy_basis(db, actor.owner_id, payload.market_selection_id)
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
                "strategy_pipeline": {
                    **draft.data.get("strategy_pipeline", {}),
                    "stages": {
                        **draft.data.get("strategy_pipeline", {}).get("stages", {}),
                        "proposal_approval": "REJECTED",
                        "formal_backtest": "BLOCKED",
                    },
                },
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
            "strategy_pipeline": {
                **draft.data.get("strategy_pipeline", {}),
                "stages": {
                    **draft.data.get("strategy_pipeline", {}).get("stages", {}),
                    "proposal_approval": "ACCEPTED",
                    "formal_backtest": "WAITING_FOR_VERSION",
                },
            },
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
    provenance = draft.data.get("provenance", {})
    approved = provenance.get("human_approval") == "APPROVED"
    if provenance.get("approval_authority") == "AUTOMATION_POLICY":
        basis = draft.data.get("research_basis", {})
        account = await store.get("account", UUID(basis["account_id"]), actor.owner_id)
        approved = bool(
            account and account.state != "DELETED" and automation_policy(account.data).enabled
        )
    if raw_specification is None or not approved:
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
    pipeline = {
        **draft.data.get("strategy_pipeline", {}),
        "stages": {
            **draft.data.get("strategy_pipeline", {}).get("stages", {}),
            "proposal_approval": "ACCEPTED",
            "formal_backtest": "READY_TO_RUN",
        },
    }
    version = await store.create(
        "strategy_version",
        actor.owner_id,
        {
            "strategy_id": str(draft.id),
            "strategy_version": 1,
            "specification": specification.model_dump(mode="json"),
            "fingerprint": identity,
            "artifact_version": specification.evaluator_version,
            "research_selection_cut_at": draft.data.get("holdout_evidence", {}).get("end_at"),
            "generated_code": compiled.generated_code,
            "generated_code_language": "python",
            "artifact_hash": compiled.artifact_hash,
            "origin": draft.data["origin"],
            "approval_authority": provenance.get("approval_authority", "HUMAN"),
            "lifecycle_state": StrategyState.IMPLEMENTED,
            "validation_evidence": {"compiler": True},
            "strategy_pipeline": pipeline,
            "research_basis": draft.data.get("research_basis", {}),
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
        {
            **draft.data,
            "lifecycle_state": StrategyState.SPECIFIED,
            "version_id": str(version.id),
            "strategy_pipeline": pipeline,
        },
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
    strategy = await _locked_version(db, strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    if strategy.state in {"ACTIVE", "PAPER_TRADING", "BACKTESTING", "RETIRED"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Finish paper/backtesting or suspend monitoring before starting another backtest",
        )
    try:
        basis, connection = await resolve_backtest_basis(db, actor.owner_id, strategy)
    except (LookupError, RuntimeError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if (
        payload.connection_id is not None
        and str(payload.connection_id) != basis["historical_connection_id"]
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "historical connection must match the strategy account/lane provider binding",
        )
    if payload.instrument != basis["instrument"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "instrument must match the strategy research selection",
        )
    if payload.instrument not in strategy.data["specification"]["instruments"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "instrument is not in the approved strategy"
        )
    if (
        connection.profile.provider == ConnectionProvider.MT5_BRIDGE
        and payload.timeframe != basis["historical_timeframe"]
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"MT5 published history uses {basis['historical_timeframe']}; select that timeframe",
        )
    effective_end_at = min(payload.end_at, datetime.now(UTC))
    if payload.start_at >= effective_end_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "backtest window must include historical time"
        )
    record = await store.create(
        "strategy_backtest",
        actor.owner_id,
        {
            "strategy_version_id": str(strategy_id),
            **payload.model_dump(mode="json"),
            "end_at": effective_end_at.isoformat(),
            "requested_end_at": payload.end_at.isoformat(),
            "connection_id": basis["historical_connection_id"],
            "account_id": basis["account_id"],
            "connection_binding_id": basis["connection_binding_id"],
            "trigger": "USER",
        },
        state="QUEUED",
        actor_id=actor.actor_id,
        event_type="backtest.queued",
    )
    await store.update(
        strategy,
        {
            **strategy.data,
            "lifecycle_state": StrategyState.BACKTESTING,
            "latest_backtest_id": str(record.id),
            "latest_backtest_state": "QUEUED",
            "latest_signal": None,
            "validation_evidence": {"compiler": True},
        },
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
    item = await _locked_version(db, strategy_id, actor.owner_id)
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
        {**item.data, "lifecycle_state": target, "latest_signal": None},
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
    """Begin forward observations using the validated version and backtest costs."""
    store = ResourceStore(db)
    strategy = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.id == strategy_id,
            ResourceRecord.kind == "strategy_version",
            ResourceRecord.owner_id == actor.owner_id,
        )
        .with_for_update()
    )
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
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
    if strategy.state != StrategyState.VALIDATING:
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy is not ready for paper trading")
    evidence = dict(strategy.data.get("validation_evidence", {}))
    if not validation_passed(evidence):
        raise HTTPException(status.HTTP_409_CONFLICT, "all formal validation gates must pass first")
    basis, _connection = await resolve_backtest_basis(db, actor.owner_id, strategy)
    if not strategy.data.get("latest_backtest_id"):
        raise HTTPException(status.HTTP_409_CONFLICT, "A passing formal backtest is required")
    backtest = await store.get(
        "strategy_backtest", UUID(strategy.data["latest_backtest_id"]), actor.owner_id
    )
    if backtest is None or backtest.state != "PASSED":
        raise HTTPException(status.HTTP_409_CONFLICT, "A passing formal backtest is required")
    if backtest.data.get("strategy_version_id") != str(strategy_id) or backtest.data.get(
        "artifact_hash"
    ) != strategy.data.get("artifact_hash"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The passing backtest does not match this strategy implementation",
        )
    now = datetime.now(UTC)
    paper_run = await store.create(
        "strategy_paper_run",
        actor.owner_id,
        {
            "strategy_version_id": str(strategy_id),
            "started_at": now.isoformat(),
            "entry_cutoff": (now + timedelta(days=payload.duration_days)).isoformat(),
            "observation_start": now.isoformat(),
            "engine": ENGINE,
            "artifact_hash": strategy.data["artifact_hash"],
            "timeframe": backtest.data["timeframe"],
            "account_id": basis["account_id"],
            "instrument": basis["instrument"],
            "notes": payload.notes,
            "configuration": {
                key: backtest.data[key]
                for key in (
                    "initial_equity",
                    "spread",
                    "commission",
                    "slippage",
                    "max_daily_loss",
                    "max_total_loss",
                )
                if key in backtest.data
            }
            | {"tick_size": basis.get("tick_size")},
            "candles": [],
            "entry_intents": {},
            "trades": [],
            "open_positions": [],
            "trade_count": 0,
            "data_complete": True,
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
        event_type="strategy.paper_trading.monitoring",
    )
    await db.commit()
    evaluate_strategy.apply_async(args=[str(strategy_id)], countdown=1)
    return paper_run.public()


@router.post("/{strategy_id}/paper-trading/{paper_run_id}/stop-entries")
async def stop_paper_entries(
    strategy_id: UUID,
    paper_run_id: UUID,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strategy = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.id == strategy_id,
            ResourceRecord.kind == "strategy_version",
            ResourceRecord.owner_id == actor.owner_id,
        )
        .with_for_update()
    )
    store = ResourceStore(db)
    run = await store.get("strategy_paper_run", paper_run_id, actor.owner_id)
    if strategy is None or run is None or run.data.get("strategy_version_id") != str(strategy_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper session not found")
    if strategy.state != "PAPER_TRADING" or run.state != "RUNNING":
        raise HTTPException(status.HTTP_409_CONFLICT, "Paper session is not running")
    updated = await store.update(
        run,
        {**run.data, "entry_cutoff": datetime.now(UTC).isoformat()},
        actor_id=actor.actor_id,
        event_type="strategy.paper_entries.stopped",
    )
    return {"id": str(updated.id), "state": updated.state}


@router.post("/{strategy_id}/paper-trading/{paper_run_id}/complete")
async def complete_paper_trading(
    strategy_id: UUID,
    paper_run_id: UUID,
    payload: PaperEvidenceInput,
    actor: Annotated[Actor, Depends(require_roles(Role.OWNER, Role.OPERATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Review only worker-recorded forward paper results."""
    store = ResourceStore(db)
    strategy = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.id == strategy_id,
            ResourceRecord.kind == "strategy_version",
            ResourceRecord.owner_id == actor.owner_id,
        )
        .with_for_update()
    )
    paper_run = await store.get("strategy_paper_run", paper_run_id, actor.owner_id)
    if strategy is None or paper_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper-trading run not found")
    if paper_run.data.get("strategy_version_id") != str(strategy_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "paper run is linked to another strategy")
    if strategy.data.get("paper_run_id") != str(paper_run_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only the current paper session can be reviewed"
        )
    if strategy.state != StrategyState.PAPER_TRADING or paper_run.state not in {
        "RUNNING",
        "QUEUED",
    }:
        raise HTTPException(status.HTTP_409_CONFLICT, "paper-trading run is not active")
    if paper_run.data.get("engine") != ENGINE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Start a new forward paper session; manually entered metrics cannot approve a strategy",
        )
    if paper_run.data.get("open_positions") or paper_run.data.get("pending_entries"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Paper entries or positions are still open")
    if paper_run.data.get("failure"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Resolve the paper monitoring failure before review"
        )
    cutoff = datetime.fromisoformat(paper_run.data["entry_cutoff"])
    if datetime.now(UTC) < cutoff:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Stop new paper entries or wait for the observation window to end before review",
        )
    if paper_run.data.get("artifact_hash") != strategy.data.get("artifact_hash"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Paper evidence belongs to a different implementation"
        )
    specification = StrategySpecification.model_validate(strategy.data["specification"])
    if compile_strategy(specification).artifact_hash != strategy.data.get("artifact_hash"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Strategy implementation changed; revalidate it"
        )
    gates = paper_gates(paper_run.data)
    passed = all(gates.values())
    evidence = {
        **strategy.data.get("validation_evidence", {}),
        "paper": passed,
        "paper_forward": passed,
    }
    pipeline = {
        **strategy.data.get("strategy_pipeline", {}),
        "stages": {
            **strategy.data.get("strategy_pipeline", {}).get("stages", {}),
            "paper_trading": "PASSED" if passed else "FAILED",
            "live_monitoring": "READY_TO_ACTIVATE" if passed else "BLOCKED",
            "approved_trade_plan": "WAITING_FOR_LIVE_SIGNAL" if passed else "BLOCKED",
        },
    }
    updated_run = await store.update(
        paper_run,
        {
            **paper_run.data,
            "reviewed_by": str(actor.actor_id),
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
            "lifecycle_state": StrategyState.APPROVED if passed else StrategyState.VALIDATING,
            "validation_evidence": evidence,
            "latest_signal": None,
            "monitoring_timeframe": paper_run.data["timeframe"],
            "strategy_pipeline": pipeline,
        },
        state=StrategyState.APPROVED if passed else StrategyState.VALIDATING,
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
    strategy = await _locked_version(db, strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    if strategy.state != StrategyState.ACTIVE or not strategy.data.get(
        "validation_evidence", {}
    ).get("paper_forward"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Activate the paper-validated strategy and wait for a fresh live signal first",
        )
    specification = StrategySpecification.model_validate(strategy.data["specification"])
    if compile_strategy(specification).artifact_hash != strategy.data.get("artifact_hash"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Strategy implementation changed; revalidate it"
        )
    draft = await store.get(
        "strategy_draft", UUID(str(strategy.data["strategy_id"])), actor.owner_id
    )
    if draft is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "strategy research draft is unavailable")
    if weekend_close(specification.asset_class, datetime.now(UTC)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "market session is closed; refresh prices after reopening before creating a Trade Plan",
        )
    setup = dict(strategy.data.get("latest_signal") or {})
    if (
        setup.get("status") != "SIGNAL"
        or setup.get("mode") != "LIVE"
        or setup.get("artifact_hash") != strategy.data.get("artifact_hash")
        or not setup.get("expires_at")
        or datetime.fromisoformat(setup["expires_at"]) <= datetime.now(UTC)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A fresh signal from the active strategy monitor is required"
        )
    if payload.entry is not None or payload.stop_loss is not None or payload.take_profits:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Trade levels must come from the validated strategy's live signal",
        )
    if specification.instrument_type == "CFD":
        selection = setup.get("strategy_selection") or {}
        basis, _ = await resolve_backtest_basis(db, actor.owner_id, strategy)
        scope = {
            "account_id": basis["account_id"],
            "instrument": basis["instrument"],
            "timeframe": strategy.data.get("monitoring_timeframe") or basis["historical_timeframe"],
            "connection_id": basis["historical_connection_id"],
            "venue_instrument_id": specification.venue_instrument_id,
            "specification_version_id": specification.specification_version_id,
        }
        current = select_strategy(
            await strategy_library(store, actor.owner_id), scope, setup.get("regime_key", "UNKNOWN")
        )
        if selection.get("scope") != scope or current["selected_version_id"] != str(strategy.id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This CFD strategy is no longer the eligible selection for the current regime",
            )
    raw_targets = [
        Decimal(str(item["price"]))
        for item in setup.get("take_profits", [])
        if isinstance(item, dict) and item.get("price") is not None
    ]
    entry = payload.entry or (Decimal(str(setup["entry"])) if setup.get("entry") else None)
    stop_loss = payload.stop_loss or (
        Decimal(str(setup["stop_loss"])) if setup.get("stop_loss") else None
    )
    invalidation = payload.invalidation or str(setup.get("invalidation") or "strategy invalidation")
    if entry is None or stop_loss is None or not raw_targets:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a fresh strategy signal with entry, stop loss, and targets is required",
        )
    basis = dict(draft.data.get("research_basis", {}))
    required = ("account_id", "market_selection_id", "category")
    if any(not basis.get(key) for key in required):
        raise HTTPException(status.HTTP_409_CONFLICT, "typed market strategy basis is incomplete")
    if (
        specification.asset_class is None
        or specification.instrument_type is None
        or specification.quantity_unit is None
        or specification.venue_instrument_id is None
        or specification.specification_version_id is None
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "typed instrument identity is required")
    listing_id = UUID(specification.venue_instrument_id)
    specification_id = UUID(specification.specification_version_id)
    direction = (
        Direction.BUY
        if specification.trade_rules and specification.trade_rules.direction == "LONG"
        else Direction.SELL
    )
    distance = abs(entry - stop_loss)
    if distance <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "entry and stop loss must differ")
    if (direction is Direction.BUY and stop_loss >= entry) or (
        direction is Direction.SELL and stop_loss <= entry
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "stop loss is on the wrong side of entry"
        )
    if any(
        (direction is Direction.BUY and target <= entry)
        or (direction is Direction.SELL and target >= entry)
        for target in raw_targets
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "target is on the wrong side of entry"
        )
    account_id = UUID(str(basis["account_id"]))
    try:
        terms = await load_live_trade_terms(
            db,
            actor.owner_id,
            account_id,
            listing_id,
            specification_id,
            specification.instrument_type,
        )
        if terms.quantity_unit is not specification.quantity_unit:
            raise ValueError("strategy quantity unit differs from broker lot unit")
        candidate = CandidateTrade(
            instrument=specification.instruments[0],
            direction=direction,
            market_category=str(basis["category"]).lower(),
            requested_size=terms.maximum_stepped_size(),
            entry_price=entry,
            stop_loss=stop_loss,
            risk_per_unit=distance * terms.contract_multiplier,
            size_increment=terms.quantity_step,
            asset_class=specification.asset_class,
            instrument_type=specification.instrument_type,
            venue_instrument_id=listing_id,
            specification_version_id=specification_id,
            quantity_unit=terms.quantity_unit,
            contract_multiplier=terms.contract_multiplier,
            tick_size=terms.tick_size,
            tick_value=terms.tick_value,
        )
        context = await authoritative_risk_context(db, actor.owner_id, account_id, candidate)
        if not context.account_currency_verified:
            raise ValueError("fresh MT5 broker account currency is required for live sizing")
        limit = strictest_applicable(context.constraints).get(ConstraintKind.MAX_RISK_PER_TRADE)
        if limit is None or limit.enforcement is not Enforcement.HARD or limit.value <= 0:
            raise ValueError(
                "configure a positive MAX_RISK_PER_TRADE limit in account currency "
                "before live Trade Plans"
            )
        risk = RiskEngine().evaluate(context, candidate)
        ticket = (
            build_trade_ticket(
                terms=terms,
                instrument_type=specification.instrument_type,
                direction=direction,
                entry=entry,
                stop=stop_loss,
                targets=raw_targets,
                fractions=[
                    Decimal(str(item["fraction"])) if item.get("fraction") is not None else None
                    for item in setup.get("take_profits", [])
                    if isinstance(item, dict) and item.get("price") is not None
                ],
                risk_limit=limit.value,
                risk=risk,
            )
            if risk.approved_size > 0
            else None
        )
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
        approved_size=risk.approved_size if risk.approved_size > 0 else terms.quantity_minimum,
        quantity_unit=specification.quantity_unit,
        asset_class=specification.asset_class,
        instrument_type=specification.instrument_type,
        venue_instrument_id=listing_id,
        specification_version_id=specification_id,
    )
    plan = build_trade_plan(
        owner_id=actor.owner_id,
        account_id=account_id,
        construction=construction,
        strategy_version_id=strategy_id,
        market_fingerprint_id=UUID(str(basis["market_selection_id"])),
        risk=risk,
        ticket=ticket,
        evidence_refs=tuple(
            [f"strategy:{strategy_id}", *[str(item) for item in draft.data.get("evidence", [])]]
        ),
        expires_at=min(
            datetime.now(UTC) + timedelta(minutes=10), datetime.fromisoformat(setup["expires_at"])
        ),
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
    strategy = await _locked_version(db, strategy_id, actor.owner_id)
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    evidence = dict(strategy.data.get("validation_evidence", {}))
    profile_complete = bool(strategy.data.get("specification")) and bool(
        strategy.data.get("artifact_hash")
    )
    if (
        not evidence.get("paper_forward")
        or StrategyState(strategy.state) not in {StrategyState.APPROVED, StrategyState.SUSPENDED}
        or not typed_promotable(evidence, profile_complete=profile_complete)
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "promotion requires complete compatible backtest, validation, policy, "
            "and paper evidence",
        )
    specification = StrategySpecification.model_validate(strategy.data["specification"])
    if strategy.data.get("strategy_health", {}).get("suspend"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This version lost its recent edge; research and validate a new version "
            "before activation",
        )
    if compile_strategy(specification).artifact_hash != strategy.data.get("artifact_hash"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Strategy implementation changed; revalidate it"
        )
    updated = await store.update(
        strategy,
        {
            **strategy.data,
            "lifecycle_state": StrategyState.ACTIVE,
            "activated_at": datetime.now(UTC).isoformat(),
            "latest_signal": None,
        },
        state=StrategyState.ACTIVE,
        actor_id=actor.actor_id,
        event_type="strategy.promoted_after_evidence",
    )
    return updated.public()
