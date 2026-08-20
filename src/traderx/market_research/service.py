from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.broker_model import Mt5BridgeAgent
from traderx.integrations.model import Integration
from traderx.integrations.ports import SourceSemantics
from traderx.market_data.model import (
    DataQualityObservation,
    Instrument,
    InstrumentAlias,
    InstrumentStatus,
)
from traderx.market_data.source_evidence import ConflictState, SourceEvidence
from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.market_research.events import SOURCE_FALLBACK_SELECTED, emit_market_research_fact
from traderx.market_research.liquidity import assess_asset_liquidity
from traderx.market_research.model import (
    ActiveMarketAssignment,
    AssignmentState,
    CandidateAssessment,
    MarketResearchRun,
    ResearchRunState,
)
from traderx.market_research.source_selection import SourceSelection
from traderx.market_research.suitability import SuitabilityResult, score_candidate
from traderx.market_research.volatility import relative_range_volatility
from traderx.shared.events import append_outbox, event_envelope
from traderx.shared.types import (
    ConcurrentModification,
    DataQuality,
    InvalidTransition,
    MarketCategory,
    as_decimal,
    utc_now,
)


@dataclass(frozen=True, slots=True)
class ResearchCandidate:
    instrument_id: str
    eligibility: EligibilityInputs
    volatility: Decimal
    liquidity: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    instrument_id: str
    result: SuitabilityResult
    rank: int | None


def rank_candidates(
    candidates: list[ResearchCandidate], weights: dict[str, Decimal]
) -> list[RankedCandidate]:
    assessed = [
        (
            candidate,
            score_candidate(
                eligibility=evaluate_eligibility(candidate.eligibility),
                volatility=candidate.volatility,
                liquidity=candidate.liquidity,
                cost=candidate.cost,
                weights=weights,
            ),
        )
        for candidate in candidates
    ]
    eligible = sorted(
        (item for item in assessed if item[1].score is not None),
        key=lambda item: item[1].score or Decimal("0"),
        reverse=True,
    )
    ranks = {
        candidate.instrument_id: index for index, (candidate, _) in enumerate(eligible, start=1)
    }
    return [
        RankedCandidate(candidate.instrument_id, result, ranks.get(candidate.instrument_id))
        for candidate, result in assessed
    ]


DEFAULT_WEIGHTS = {
    "volatility": Decimal("0.50"),
    "liquidity": Decimal("0.35"),
    "cost": Decimal("0.15"),
}
METHOD_VERSION = "market-suitability-v1"
_FOREX_CODES = {
    "AUD",
    "CAD",
    "CHF",
    "EUR",
    "GBP",
    "JPY",
    "NZD",
    "USD",
    "ZAR",
}
_CRYPTO_CODES = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH"}
_COMMODITY_CODES = {"XAU", "XAG", "XPT", "XPD", "WTI", "XTI", "BRENT", "XBR", "NGAS"}


def normalize_category(value: str) -> MarketCategory:
    canonical = "CRYPTO" if value.upper() == "CRYPTOCURRENCY" else value.upper()
    try:
        return MarketCategory(canonical)
    except ValueError as error:
        raise InvalidTransition("market category must be COMMODITY, FOREX, or CRYPTO") from error


def classify_mt5_instrument(payload: dict[str, object]) -> MarketCategory | None:
    supplied = str(payload.get("category", "")).upper()
    if supplied:
        try:
            return normalize_category(supplied)
        except InvalidTransition:
            pass
    symbol = "".join(
        character for character in str(payload.get("symbol", "")).upper() if character.isalpha()
    )
    path = f"{payload.get('path', '')} {payload.get('description', '')}".lower()
    base = str(payload.get("currency_base", symbol[:3])).upper()
    quote = str(payload.get("currency_profit", symbol[3:6])).upper()
    if "crypto" in path or base in _CRYPTO_CODES or quote in _CRYPTO_CODES:
        return MarketCategory.CRYPTO
    if any(word in path for word in ("commodity", "metal", "energy")) or base in _COMMODITY_CODES:
        return MarketCategory.COMMODITY
    if "forex" in path or "fx" in path or (base in _FOREX_CODES and quote in _FOREX_CODES):
        return MarketCategory.FOREX
    return None


def refresh_mt5_instrument_catalog(database: Session) -> int:
    """Upsert the latest broker-supplied read-only instrument catalog."""

    account = database.scalar(select(TradingAccount).order_by(TradingAccount.created_at).limit(1))
    if account is None or account.broker_integration_id is None:
        return 0
    integration = database.get(Integration, account.broker_integration_id)
    if integration is None or integration.state not in {"HEALTHY", "ENABLED"}:
        return 0
    agent = database.scalar(
        select(Mt5BridgeAgent).where(Mt5BridgeAgent.integration_id == integration.id)
    )
    if agent is None or agent.last_snapshot_at is None:
        return 0
    records = agent.latest_snapshot.get("instruments", [])
    if not isinstance(records, list):
        raise InvalidTransition("the MT5 instrument catalog is invalid")
    observed_at = _as_utc(agent.last_snapshot_at)
    imported = 0
    for raw_record in records:
        if not isinstance(raw_record, dict) or not str(raw_record.get("symbol", "")).strip():
            continue
        record = {str(key): value for key, value in raw_record.items()}
        category = classify_mt5_instrument(record)
        if category is None:
            continue
        native_symbol = str(record["symbol"]).strip()
        symbol = native_symbol.upper()
        instrument = database.scalar(select(Instrument).where(Instrument.symbol == symbol))
        safe_record = _json_safe(record)
        if instrument is None:
            instrument = Instrument(
                symbol=symbol,
                display_name=str(record.get("description") or native_symbol),
                category=category.value,
                status=InstrumentStatus.INACTIVE,
                contract_spec=safe_record,
                trading_hours={
                    "provider": integration.provider,
                    "observed_at": observed_at.isoformat(),
                },
            )
            database.add(instrument)
            database.flush()
        else:
            instrument.display_name = str(record.get("description") or instrument.display_name)
            instrument.category = category.value
            instrument.contract_spec = safe_record
            instrument.trading_hours = {
                "provider": integration.provider,
                "observed_at": observed_at.isoformat(),
            }
        alias = database.scalar(
            select(InstrumentAlias).where(
                InstrumentAlias.provider == integration.provider,
                InstrumentAlias.native_symbol == native_symbol,
            )
        )
        if alias is None:
            database.add(
                InstrumentAlias(
                    instrument_id=instrument.id,
                    provider=integration.provider,
                    native_symbol=native_symbol,
                    valid_from=observed_at,
                )
            )
        imported += 1
    database.flush()
    return imported


def execute_market_research(
    database: Session,
    *,
    category: str,
    method_version: str,
    weights: dict[str, Decimal] | None = None,
    existing_run: MarketResearchRun | None = None,
    source_selection: SourceSelection | None = None,
) -> MarketResearchRun:
    canonical_category = normalize_category(category)
    selected_weights = weights or DEFAULT_WEIGHTS
    # Validate weights even when there are no candidates.
    if set(selected_weights) != set(DEFAULT_WEIGHTS) or sum(selected_weights.values()) != Decimal(
        "1"
    ):
        raise InvalidTransition("market suitability weights must sum to one")
    refresh_mt5_instrument_catalog(database)
    instruments = list(
        database.scalars(
            select(Instrument)
            .where(Instrument.category == canonical_category.value)
            .order_by(Instrument.symbol)
        )
    )
    now = utc_now()
    manifest = {
        "category": canonical_category.value,
        "method_version": method_version,
        "weights": {key: str(value) for key, value in sorted(selected_weights.items())},
        "instruments": [
            {"id": str(instrument.id), "version": instrument.version, "symbol": instrument.symbol}
            for instrument in instruments
        ],
    }
    run = existing_run or MarketResearchRun(
        category=canonical_category.value,
        method_version=method_version or METHOD_VERSION,
        input_manifest_hash=hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        state=ResearchRunState.QUEUED,
        created_at=now,
    )
    if existing_run is not None:
        if run.category != canonical_category.value:
            raise InvalidTransition("coordinated child category does not match research input")
        if run.state in {ResearchRunState.COMPLETED, ResearchRunState.BLOCKED}:
            return run
        run.method_version = method_version or run.method_version
        run.input_manifest_hash = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    else:
        database.add(run)
    if source_selection is not None:
        run.source_manifest = {
            "selected_role": source_selection.role.value if source_selection.role else None,
            "evidence": [item.as_manifest() for item in source_selection.evidence],
            "active_assignment_changed": False,
        }
        run.fallback_path = [
            {
                "role": step.role.value,
                "accepted": step.accepted,
                "reason_codes": list(step.reason_codes),
            }
            for step in source_selection.trail
        ]
        if source_selection.role is not None and source_selection.role.value.startswith("FALLBACK"):
            emit_market_research_fact(
                database,
                aggregate_type="market_research_run",
                aggregate_id=run.id,
                aggregate_version=run.version,
                event_type=SOURCE_FALLBACK_SELECTED,
                data={
                    "category": run.category,
                    "selected_role": source_selection.role.value,
                    "trail": run.fallback_path,
                    "active_assignment_changed": False,
                },
                now=now,
                correlation_id="market-research-worker",
            )
        if source_selection.blocked:
            run.state = ResearchRunState.BLOCKED
            run.block_reasons = list(source_selection.reason_codes)
            run.completed_at = now
            database.flush()
            return run
    run.state = ResearchRunState.RUNNING
    database.flush()

    pending: list[
        tuple[Instrument, EligibilityInputs, SuitabilityResult, tuple[str, ...], dict[str, str]]
    ] = []
    for instrument in instruments:
        candidate_evidence = (
            tuple(
                item
                for item in source_selection.evidence
                if item.canonical_instrument_id == str(instrument.id)
            )
            if source_selection is not None
            else None
        )
        eligibility_inputs, metrics, quality = _research_inputs(
            instrument, source_evidence=candidate_evidence
        )
        eligibility = evaluate_eligibility(eligibility_inputs)
        score = score_candidate(
            eligibility=eligibility,
            volatility=as_decimal(metrics["volatility"]),
            liquidity=as_decimal(metrics["liquidity"]),
            cost=as_decimal(metrics["cost_quality"]),
            weights=selected_weights,
        )
        pending.append((instrument, eligibility_inputs, score, eligibility.reason_codes, metrics))
        database.add(
            DataQualityObservation(
                instrument_id=instrument.id,
                purpose="MARKET_SELECTION",
                quality=quality.value,
                reason_codes=list(eligibility.reason_codes),
                observed_at=now,
            )
        )
    eligible = sorted(
        (item for item in pending if item[2].score is not None),
        key=lambda item: (item[2].score or Decimal("0"), item[0].symbol),
        reverse=True,
    )
    ranks = {instrument.id: index for index, (instrument, *_rest) in enumerate(eligible, 1)}
    for instrument, inputs, result, reason_codes, metrics in pending:
        database.add(
            CandidateAssessment(
                research_run_id=run.id,
                instrument_id=instrument.id,
                eligible=result.score is not None,
                gate_evidence={
                    "evaluation_order": [
                        "BROKER",
                        "BROKER_SPECIFICATION",
                        "SOURCE_EVIDENCE",
                        "DATA",
                        "LIQUIDITY",
                        "EXECUTION",
                        "SIZING",
                        "GAP",
                        "HOURS",
                        "PROP",
                        "VOLATILITY",
                        "SUITABILITY",
                    ],
                    "reason_codes": list(reason_codes),
                    "inputs": _json_safe(asdict(inputs)),
                },
                components=metrics,
                score=result.score,
                rank=ranks.get(instrument.id),
                confidence=result.confidence,
                explanation={
                    "method_version": method_version or METHOD_VERSION,
                    "weights": {key: str(value) for key, value in selected_weights.items()},
                    "eligibility_precedes_ranking": True,
                    "details": _json_safe(result.explanation),
                    "activation_requires_separate_human_confirmation": True,
                },
                source_evidence=(
                    [item.as_manifest() for item in source_selection.evidence]
                    if source_selection
                    else []
                ),
            )
        )
    deterministic_manifest = {
        "input_manifest_hash": run.input_manifest_hash,
        "category": run.category,
        "method_version": run.method_version,
        "results": [
            {
                "instrument_id": str(instrument.id),
                "eligible": result.score is not None,
                "reason_codes": reason_codes,
                "metrics": metrics,
                "score": str(result.score) if result.score is not None else None,
                "rank": ranks.get(instrument.id),
            }
            for instrument, _inputs, result, reason_codes, metrics in pending
        ],
    }
    run.deterministic_result_hash = hashlib.sha256(
        json.dumps(deterministic_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run.state = ResearchRunState.COMPLETED
    run.completed_at = now
    database.flush()
    return run


def market_research_report(database: Session, run_id: UUID) -> dict[str, object]:
    run = database.get(MarketResearchRun, run_id)
    if run is None:
        raise InvalidTransition("the requested market research run does not exist")
    rows = database.execute(
        select(CandidateAssessment, Instrument)
        .join(Instrument, Instrument.id == CandidateAssessment.instrument_id)
        .where(CandidateAssessment.research_run_id == run.id)
    ).all()
    candidates = [
        {
            "id": str(assessment.id),
            "instrument_id": str(instrument.id),
            "symbol": instrument.symbol,
            "display_name": instrument.display_name,
            "category": instrument.category,
            "eligible": assessment.eligible,
            "exclusions": assessment.gate_evidence.get("reason_codes", []),
            "components": assessment.components,
            "score": str(assessment.score) if assessment.score is not None else None,
            "rank": assessment.rank,
            "confidence": str(assessment.confidence),
            "explanation": assessment.explanation,
        }
        for assessment, instrument in rows
    ]
    candidates.sort(key=lambda item: (item["rank"] is None, item["rank"] or 999999, item["symbol"]))
    return {
        "id": str(run.id),
        "category": run.category,
        "state": run.state,
        "methodology_version": run.method_version,
        "input_manifest_hash": run.input_manifest_hash,
        "created_at": _as_utc(run.created_at).isoformat(),
        "completed_at": _as_utc(run.completed_at).isoformat() if run.completed_at else None,
        "candidates": candidates,
        "ranking_is_not_activation": True,
    }


def instrument_library_payload(
    database: Session, *, category: str | None = None, status: str | None = None
) -> list[dict[str, object]]:
    statement = select(Instrument).order_by(Instrument.category, Instrument.symbol)
    if category:
        statement = statement.where(Instrument.category == normalize_category(category).value)
    if status:
        statement = statement.where(Instrument.status == status.upper())
    result: list[dict[str, object]] = []
    for instrument in database.scalars(statement):
        aliases = list(
            database.scalars(
                select(InstrumentAlias)
                .where(InstrumentAlias.instrument_id == instrument.id)
                .order_by(InstrumentAlias.provider)
            )
        )
        quality = database.scalar(
            select(DataQualityObservation)
            .where(DataQualityObservation.instrument_id == instrument.id)
            .order_by(DataQualityObservation.observed_at.desc())
            .limit(1)
        )
        result.append(
            {
                "id": str(instrument.id),
                "symbol": instrument.symbol,
                "display_name": instrument.display_name,
                "category": instrument.category,
                "status": instrument.status,
                "data_status": _data_status(instrument.contract_spec),
                "contract_spec": instrument.contract_spec,
                "version": instrument.version,
                "quality_observed_at": _as_utc(quality.observed_at).isoformat()
                if quality
                else None,
                "quality_reason_codes": quality.reason_codes if quality else [],
                "source_coverage": [
                    {
                        "provider": alias.provider,
                        "provider_symbol": alias.native_symbol,
                        "venue": alias.venue,
                        "mapping_revision": alias.mapping_revision,
                        "mapping_status": "APPROVED" if alias.approved_at else "BROKER_AUTHORITY",
                        "entitlement_status": alias.provider_metadata.get(
                            "entitlement_status", "NOT_REQUIRED"
                        ),
                        "semantics": (
                            instrument.contract_spec.get("source_semantics", "BROKER_PROXY")
                            if alias.provider == "MT5_TERMINAL_BRIDGE"
                            else alias.provider_metadata.get("semantics", "UNAVAILABLE")
                        ),
                    }
                    for alias in aliases
                ],
                "capability_status": instrument.contract_spec.get("capability_status", {}),
            }
        )
    return result


def approve_active_market(
    database: Session,
    actor: Actor,
    *,
    category: str,
    candidate_assessment_id: UUID,
    expected_etag: str,
    replace: bool,
    reason: str,
    idempotency_key: str,
    correlation_id: str,
) -> ActiveMarketAssignment:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "active-market.activate", require_mfa=True)
    canonical_category = normalize_category(category)
    assessment = database.get(CandidateAssessment, candidate_assessment_id)
    if assessment is None or not assessment.eligible or assessment.rank is None:
        raise InvalidTransition("only an eligible ranked candidate can become active")
    instrument = database.get(Instrument, assessment.instrument_id)
    run = database.get(MarketResearchRun, assessment.research_run_id)
    if (
        instrument is None
        or run is None
        or run.state != ResearchRunState.COMPLETED
        or instrument.category != canonical_category.value
        or run.category != canonical_category.value
    ):
        raise InvalidTransition("candidate evidence does not match the requested category")
    current = database.scalar(
        select(ActiveMarketAssignment).where(
            ActiveMarketAssignment.category == canonical_category.value,
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
        )
    )
    current_version = current.version if current else 0
    required_etag = f'"active-{canonical_category.value}-{current_version}"'
    if expected_etag != required_etag:
        raise ConcurrentModification("the active market changed; refresh and review again")
    if current is not None and current.instrument_id != instrument.id and not replace:
        raise InvalidTransition("replacing an active market requires explicit replacement review")
    if current is not None and current.instrument_id == instrument.id:
        return current
    now = utc_now()
    previous_value: dict[str, object] | None = None
    if current is not None:
        previous_instrument = database.get(Instrument, current.instrument_id)
        previous_value = {
            "assignment_id": str(current.id),
            "instrument": previous_instrument.symbol
            if previous_instrument
            else str(current.instrument_id),
        }
        current.state = AssignmentState.REPLACED
        current.effective_to = now
        if previous_instrument is not None:
            previous_instrument.status = InstrumentStatus.INACTIVE
    assignment = ActiveMarketAssignment(
        category=canonical_category.value,
        instrument_id=instrument.id,
        candidate_assessment_id=assessment.id,
        state=AssignmentState.ACTIVE,
        effective_from=now,
        approved_by=actor.id,
        approval_reason=reason,
    )
    instrument.status = InstrumentStatus.ACTIVE
    database.add(assignment)
    database.flush()
    new_value = {
        "assignment_id": str(assignment.id),
        "instrument": instrument.symbol,
        "assessment_id": str(assessment.id),
        "rank": assessment.rank,
    }
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role.value,
            action="active-market.activate" if current is None else "active-market.replace",
            outcome="SUCCEEDED",
            target_type="active_market_assignment",
            target_id=assignment.id,
            target_version=assignment.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous_value,
            new_value=new_value,
            occurred_at=now,
        )
    )
    envelope = event_envelope(
        source="urn:traderx:markets",
        event_type="com.traderx.markets.active-assignment-approved.v1",
        subject=f"active-markets/{canonical_category.value}",
        data=new_value,
        now=now,
        correlation_id=correlation_id,
        actor_id=actor.id,
        aggregate_version=assignment.version,
    )
    append_outbox(
        database,
        aggregate_type="active_market_assignment",
        aggregate_id=assignment.id,
        aggregate_version=assignment.version,
        event_type=envelope["type"],
        envelope=envelope,
    )
    database.flush()
    return assignment


def active_markets_payload(database: Session) -> list[dict[str, object]]:
    rows = database.execute(
        select(ActiveMarketAssignment, Instrument)
        .join(Instrument, Instrument.id == ActiveMarketAssignment.instrument_id)
        .where(ActiveMarketAssignment.state == AssignmentState.ACTIVE)
        .order_by(ActiveMarketAssignment.category)
    ).all()
    return [
        {
            "id": str(assignment.id),
            "category": assignment.category,
            "instrument_id": str(instrument.id),
            "symbol": instrument.symbol,
            "state": assignment.state,
            "version": assignment.version,
            "etag": f'"active-{assignment.category}-{assignment.version}"',
            "effective_from": _as_utc(assignment.effective_from).isoformat(),
            "approval_reason": assignment.approval_reason,
        }
        for assignment, instrument in rows
    ]


def deactivate_active_market(
    database: Session,
    actor: Actor,
    *,
    category: str,
    expected_etag: str,
    reason: str,
    idempotency_key: str,
    correlation_id: str,
) -> ActiveMarketAssignment:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "active-market.deactivate", require_mfa=True)
    canonical_category = normalize_category(category)
    current = database.scalar(
        select(ActiveMarketAssignment).where(
            ActiveMarketAssignment.category == canonical_category.value,
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
        )
    )
    if current is None:
        raise InvalidTransition("there is no active market in this category")
    required_etag = f'"active-{canonical_category.value}-{current.version}"'
    if expected_etag != required_etag:
        raise ConcurrentModification("the active market changed; refresh and review again")
    instrument = database.get(Instrument, current.instrument_id)
    now = utc_now()
    previous_value = {
        "assignment_id": str(current.id),
        "instrument": instrument.symbol if instrument else str(current.instrument_id),
        "state": current.state,
    }
    current.state = AssignmentState.DEACTIVATED
    current.effective_to = now
    if instrument is not None:
        instrument.status = InstrumentStatus.INACTIVE
    new_value = {**previous_value, "state": AssignmentState.DEACTIVATED.value}
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role.value,
            action="active-market.deactivate",
            outcome="SUCCEEDED",
            target_type="active_market_assignment",
            target_id=current.id,
            target_version=current.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous_value,
            new_value=new_value,
            occurred_at=now,
        )
    )
    envelope = event_envelope(
        source="urn:traderx:markets",
        event_type="com.traderx.markets.active-assignment-deactivated.v1",
        subject=f"active-markets/{canonical_category.value}",
        data=new_value,
        now=now,
        correlation_id=correlation_id,
        actor_id=actor.id,
        aggregate_version=current.version,
    )
    append_outbox(
        database,
        aggregate_type="active_market_assignment",
        aggregate_id=current.id,
        aggregate_version=current.version,
        event_type=envelope["type"],
        envelope=envelope,
    )
    database.flush()
    return current


def _research_inputs(
    instrument: Instrument,
    *,
    source_evidence: tuple[SourceEvidence, ...] | None = None,
) -> tuple[EligibilityInputs, dict[str, str], DataQuality]:
    spec = instrument.contract_spec
    closes = _decimal_list(spec.get("closes"))
    tick_volumes = _decimal_list(spec.get("tick_volumes"))
    bid = _optional_decimal(spec.get("bid"))
    ask = _optional_decimal(spec.get("ask"))
    data_verified = len(closes) >= 61 and all(close > 0 for close in closes)
    broker_turnover = sum(tick_volumes, Decimal("0"))
    broker_depth = broker_turnover / Decimal(len(tick_volumes)) if tick_volumes else Decimal("0")
    if bid is not None and ask is not None and ask >= bid and bid + ask > 0:
        spread_bps = (ask - bid) / ((ask + bid) / Decimal("2")) * Decimal("10000")
    else:
        spread_bps = Decimal("999999")
    sizing_supported = all(
        (_optional_decimal(spec.get(field)) or Decimal("0")) > 0
        for field in ("tick_size", "tick_value", "contract_size", "volume_min", "volume_step")
    )
    returns = [
        abs((current - previous) / previous)
        for previous, current in zip(closes, closes[1:], strict=False)
        if previous > 0
    ]
    gap_risk_acceptable = bool(returns) and max(returns) <= Decimal("0.20")
    try:
        trade_mode = int(str(spec.get("trade_mode", 0)))
    except (TypeError, ValueError):
        trade_mode = 0
    turnover = broker_turnover
    depth = broker_depth
    liquidity = Decimal("0")
    liquidity_evidence: tuple[str, ...] = ("BROKER_ACTIVITY_PROXY",)
    mandatory_source_complete = True
    source_conflict = False
    actual_liquidity_required_met = True
    if source_evidence is None:
        liquidity = max(
            Decimal("0"),
            min(Decimal("1"), Decimal("1") - spread_bps / Decimal("50")),
        )
        liquidity = liquidity * Decimal("0.7") + min(
            Decimal("1"), turnover / Decimal("100000")
        ) * Decimal("0.3")
    else:
        qualified = [
            item for item in source_evidence if item.capability == "LIQUIDITY" and item.qualifies
        ]
        mandatory_source_complete = bool(qualified)
        source_conflict = any(
            item.conflict_state == ConflictState.MATERIAL_CONFLICT for item in source_evidence
        )
        actual = any(item.semantics == SourceSemantics.ACTUAL for item in qualified)
        broker_proxy = any(item.semantics == SourceSemantics.BROKER_PROXY for item in qualified)
        category = MarketCategory(instrument.category)
        specialist_metrics: dict[str, str] = {}
        for item in source_evidence:
            if item.canonical_instrument_id != str(instrument.id):
                continue
            if item.capability == "LIQUIDITY":
                specialist_metrics.update(item.measures)
            elif item.measures.get("value") is not None:
                specialist_metrics[item.capability] = item.measures["value"]
        external_turnover = _optional_decimal(specialist_metrics.get("TRADED_VOLUME"))
        external_depth = _optional_decimal(specialist_metrics.get("ORDER_BOOK"))
        open_interest = _optional_decimal(specialist_metrics.get("OPEN_INTEREST"))
        if category == MarketCategory.COMMODITY:
            if actual and external_turnover is not None:
                turnover = external_turnover
            depth = external_depth or open_interest or Decimal("0")
            actual_liquidity_required_met = bool(actual and open_interest and turnover > 0)
            if actual_liquidity_required_met:
                assessed = assess_asset_liquidity(
                    category=category,
                    turnover=turnover,
                    spread_bps=spread_bps,
                    quoted_depth=external_depth,
                    open_interest=open_interest,
                )
                liquidity = assessed.execution_quality
                liquidity_evidence = assessed.evidence
            elif broker_proxy and broker_turnover > 0 and broker_depth > 0:
                turnover = broker_turnover
                depth = broker_depth
                assessed = assess_asset_liquidity(
                    category=category,
                    turnover=turnover,
                    spread_bps=spread_bps,
                    tick_volume=broker_depth,
                    commodity_broker_proxy=True,
                )
                liquidity = assessed.execution_quality
                liquidity_evidence = assessed.evidence
                actual_liquidity_required_met = True
        elif category == MarketCategory.CRYPTO:
            if actual and external_turnover is not None:
                turnover = external_turnover
            depth = external_depth or Decimal("0")
            actual_liquidity_required_met = bool(actual and external_depth and turnover > 0)
            if actual_liquidity_required_met:
                assessed = assess_asset_liquidity(
                    category=category,
                    turnover=turnover,
                    spread_bps=spread_bps,
                    quoted_depth=external_depth,
                )
                liquidity = assessed.execution_quality
                liquidity_evidence = assessed.evidence
        elif mandatory_source_complete and broker_turnover > 0 and broker_depth > 0:
            # Forex liquidity remains broker-account specific even when aggregate evidence
            # supplements the run. Venue volume/depth never replaces MT5 spread and
            # quote/tick activity or becomes a claimed consolidated FX order book.
            turnover = broker_turnover
            depth = broker_depth
            assessed = assess_asset_liquidity(
                category=category,
                turnover=turnover,
                spread_bps=spread_bps,
                tick_volume=broker_depth,
            )
            liquidity = assessed.execution_quality
            liquidity_evidence = assessed.evidence
            actual_liquidity_required_met = True
        elif category == MarketCategory.FOREX:
            actual_liquidity_required_met = False
    inputs = EligibilityInputs(
        broker_available=instrument.status != InstrumentStatus.QUARANTINED,
        data_verified=data_verified,
        turnover=turnover,
        spread_bps=spread_bps,
        depth=depth,
        sizing_supported=sizing_supported,
        gap_risk_acceptable=gap_risk_acceptable,
        hours_supported=trade_mode in {1, 2, 4},
        prop_permitted=bool(spec.get("prop_permitted", True)),
        mandatory_source_evidence_complete=mandatory_source_complete,
        source_conflict=source_conflict,
        actual_liquidity_required_met=actual_liquidity_required_met,
    )
    volatility = Decimal("0")
    if data_verified:
        volatility_metrics = relative_range_volatility(closes[-61:])
        volatility = min(
            Decimal("1"),
            (volatility_metrics.short + volatility_metrics.medium + volatility_metrics.long)
            / Decimal("3")
            * Decimal("100"),
        )
    cost_quality = max(Decimal("0"), min(Decimal("1"), Decimal("1") - spread_bps / Decimal("50")))
    metrics = {
        "volatility": str(volatility),
        "liquidity": str(liquidity),
        "cost_quality": str(cost_quality),
        "spread_bps": str(spread_bps),
        "turnover": str(turnover),
        "depth": str(depth),
        "liquidity_method_version": "asset-liquidity-v1",
        "liquidity_evidence": ",".join(liquidity_evidence),
    }
    quality = (
        DataQuality.VERIFIED
        if data_verified and spread_bps <= Decimal("50") and mandatory_source_complete
        else DataQuality.QUARANTINED
    )
    return inputs, metrics, quality


def _data_status(spec: dict[str, object]) -> str:
    closes = spec.get("closes")
    return "VERIFIED" if isinstance(closes, list) and len(closes) >= 61 else "INSUFFICIENT"


def _decimal_list(value: object) -> list[Decimal]:
    if not isinstance(value, list):
        return []
    result: list[Decimal] = []
    for item in value:
        try:
            result.append(as_decimal(cast(Decimal | str | int, item)))
        except (TypeError, ValueError):
            return []
    return result


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return as_decimal(cast(Decimal | str | int, value))
    except (TypeError, ValueError):
        return None


def _json_safe(value: object) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
