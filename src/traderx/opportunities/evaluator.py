from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import RiskPolicyVersion, TradingAccount
from traderx.market_data.model import Instrument
from traderx.market_research.model import ActiveMarketAssignment, AssignmentState
from traderx.opportunities.model import Opportunity, OpportunityScoreComponent, OpportunityState
from traderx.opportunities.ranking import rank_components
from traderx.opportunities.recommendation_model import Recommendation, RecommendationState
from traderx.portfolio.exposure import assess_exposure
from traderx.risk.manager import authorize
from traderx.risk.model import AccountSnapshot, RiskDecision, RiskSnapshot
from traderx.risk.sizing import size_position
from traderx.shared.types import DataQuality, RiskDecisionKind, RiskState, as_decimal, utc_now
from traderx.strategies.model import Strategy, StrategyLifecycle, StrategyVersion


@dataclass(frozen=True, slots=True)
class Evaluation:
    state: OpportunityState
    reason_codes: tuple[str, ...]


def evaluate_live_opportunity(
    *, active_market: bool, strategy_live_eligible: bool, data_verified: bool, signal_present: bool
) -> Evaluation:
    checks = (
        (active_market, "MARKET_NOT_ACTIVE"),
        (strategy_live_eligible, "STRATEGY_NOT_LIVE_ELIGIBLE"),
        (data_verified, "CRITICAL_DATA_UNAVAILABLE"),
        (signal_present, "NO_SIGNAL"),
    )
    failures = tuple(code for passed, code in checks if not passed)
    return Evaluation(
        OpportunityState.CANDIDATE if not failures else OpportunityState.NO_TRADE, failures
    )


def evaluate_current_opportunities(database: Session) -> list[Opportunity]:
    """Persist a point-in-time opportunity set; scoring never bypasses risk authorization."""

    now = utc_now()
    for old in database.scalars(
        select(Opportunity).where(
            Opportunity.expires_at <= now,
            Opportunity.state == OpportunityState.CANDIDATE,
        )
    ):
        old.state = OpportunityState.EXPIRED
    assignments = database.scalars(
        select(ActiveMarketAssignment).where(
            ActiveMarketAssignment.state == AssignmentState.ACTIVE,
            ActiveMarketAssignment.effective_to.is_(None),
        )
    ).all()
    latest_risk = database.scalar(
        select(RiskSnapshot).order_by(RiskSnapshot.calculated_at.desc()).limit(1)
    )
    account = database.scalar(select(TradingAccount).order_by(TradingAccount.created_at).limit(1))
    results: list[Opportunity] = []
    for assignment in assignments:
        instrument = database.get(Instrument, assignment.instrument_id)
        if instrument is None:
            continue
        strategies = database.scalars(
            select(StrategyVersion)
            .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
            .where(
                Strategy.instrument_id == instrument.id,
                StrategyVersion.lifecycle.in_(
                    [StrategyLifecycle.LIVE_APPROVED, StrategyLifecycle.LIVE]
                ),
            )
        ).all()
        for version in strategies:
            current_price = _current_price(instrument)
            data_verified = current_price is not None and _data_verified(instrument)
            signal_present = data_verified and _signal_present(
                version, current_price or Decimal("0")
            )
            evaluated = evaluate_live_opportunity(
                active_market=True,
                strategy_live_eligible=True,
                data_verified=data_verified,
                signal_present=signal_present,
            )
            components = {
                "signal_quality": Decimal("0.85") if signal_present else Decimal("0"),
                "data_freshness": Decimal("1") if data_verified else Decimal("0"),
                "portfolio_fit": Decimal("0.75")
                if latest_risk and latest_risk.capacity > 0
                else Decimal("0"),
            }
            opportunity_score = (
                rank_components(
                    components,
                    {
                        "signal_quality": Decimal("0.50"),
                        "data_freshness": Decimal("0.25"),
                        "portfolio_fit": Decimal("0.25"),
                    },
                )
                if evaluated.state == OpportunityState.CANDIDATE
                else None
            )
            opportunity = Opportunity(
                instrument_id=instrument.id,
                strategy_version_id=version.id,
                state=evaluated.state,
                score=opportunity_score,
                evidence={
                    "category": instrument.category,
                    "symbol": instrument.symbol,
                    "price": str(current_price) if current_price is not None else None,
                    "active_assignment_id": str(assignment.id),
                    "evaluated_at": now.isoformat(),
                    "score_is_separate_from_risk": True,
                },
                reason_codes=list(evaluated.reason_codes),
                expires_at=now + timedelta(minutes=15),
                created_at=now,
            )
            database.add(opportunity)
            database.flush()
            for name, value in components.items():
                database.add(
                    OpportunityScoreComponent(
                        opportunity_id=opportunity.id,
                        name=name,
                        value=value,
                        evidence={"method": "opportunity-score-v1"},
                    )
                )
            if evaluated.state == OpportunityState.CANDIDATE:
                _risk_authorize(
                    database, opportunity, version, instrument, latest_risk, account, now
                )
            results.append(opportunity)
    database.flush()
    return results


def opportunity_payload(database: Session, opportunity: Opportunity) -> dict[str, object]:
    instrument = database.get(Instrument, opportunity.instrument_id)
    components = database.scalars(
        select(OpportunityScoreComponent).where(
            OpportunityScoreComponent.opportunity_id == opportunity.id
        )
    ).all()
    risk = database.scalar(
        select(RiskDecision).where(RiskDecision.opportunity_id == opportunity.id)
    )
    recommendation = database.scalar(
        select(Recommendation).where(Recommendation.opportunity_id == opportunity.id)
    )
    return {
        "id": str(opportunity.id),
        "instrument_id": str(opportunity.instrument_id),
        "symbol": instrument.symbol if instrument else "UNKNOWN",
        "category": instrument.category if instrument else "UNKNOWN",
        "strategy_version_id": str(opportunity.strategy_version_id),
        "state": opportunity.state,
        "score": str(opportunity.score) if opportunity.score is not None else None,
        "score_components": {component.name: str(component.value) for component in components},
        "evidence": opportunity.evidence,
        "reason_codes": opportunity.reason_codes,
        "risk_decision": {
            "decision": risk.decision,
            "requested_risk": str(risk.requested_risk),
            "permitted_risk": str(risk.permitted_risk),
            "reason_codes": risk.reason_codes,
        }
        if risk
        else {"decision": "BLOCKED", "reason_codes": ["NO_CURRENT_RISK_DECISION"]},
        "recommendation_id": str(recommendation.id) if recommendation else None,
        "expires_at": _iso(opportunity.expires_at),
        "created_at": _iso(opportunity.created_at),
    }


def recommendation_payload(database: Session, opportunity: Opportunity) -> dict[str, object]:
    recommendation = database.scalar(
        select(Recommendation).where(Recommendation.opportunity_id == opportunity.id)
    )
    if recommendation is None:
        risk = database.scalar(
            select(RiskDecision).where(RiskDecision.opportunity_id == opportunity.id)
        )
        return {
            "opportunity_id": str(opportunity.id),
            "state": "NO_RECOMMENDATION",
            "reason_codes": risk.reason_codes if risk else ["NO_CURRENT_RISK_DECISION"],
            "no_execution_capability": True,
        }
    if (
        _aware(recommendation.expires_at) <= utc_now()
        and recommendation.state == RecommendationState.ISSUED
    ):
        recommendation.state = RecommendationState.EXPIRED
    return {
        "id": str(recommendation.id),
        "opportunity_id": str(opportunity.id),
        "state": recommendation.state,
        "entry": str(recommendation.entry),
        "stop": str(recommendation.stop),
        "targets": recommendation.targets,
        "volume": str(recommendation.volume),
        "invalidation": recommendation.invalidation,
        "reason_trace": recommendation.reason_trace,
        "expires_at": _iso(recommendation.expires_at),
        "created_at": _iso(recommendation.created_at),
        "manual_execution_only": True,
        "no_execution_capability": True,
    }


def _risk_authorize(
    database: Session,
    opportunity: Opportunity,
    version: StrategyVersion,
    instrument: Instrument,
    risk: RiskSnapshot | None,
    account: TradingAccount | None,
    now: datetime,
) -> None:
    if risk is None or account is None or risk.quality != DataQuality.VERIFIED:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = ["RISK_SNAPSHOT_UNVERIFIED"]
        return
    remaining = min(
        as_decimal(str(risk.remaining_daily_margin)),
        as_decimal(str(risk.remaining_drawdown_margin)),
    )
    account_snapshot = (
        database.get(AccountSnapshot, risk.account_snapshot_id)
        if risk.account_snapshot_id
        else None
    )
    policy = (
        database.get(RiskPolicyVersion, account.risk_policy_id) if account.risk_policy_id else None
    )
    if account_snapshot is None or policy is None:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = ["RISK_POLICY_OR_EQUITY_UNAVAILABLE"]
        return
    requested = max(
        Decimal("0"),
        min(
            remaining,
            as_decimal(str(account_snapshot.equity))
            * as_decimal(str(policy.maximum_risk_per_trade)),
        ),
    )
    exposure = assess_exposure(
        correlation=Decimal("0"),
        common_factor_overlap=Decimal("0"),
        correlation_limit=Decimal("0.75"),
        factor_limit=Decimal("0.75"),
    )
    managed = authorize(
        requested_risk=requested,
        risk_state=RiskState(risk.state),
        capacity=risk.capacity,
        exposure_acceptable=exposure.acceptable,
        remaining_margin=remaining,
    )
    decision = RiskDecision(
        account_id=account.id,
        risk_snapshot_id=risk.id,
        opportunity_id=opportunity.id,
        decision=managed.decision,
        requested_risk=requested,
        permitted_risk=managed.permitted_risk,
        reason_codes=list(managed.reason_codes),
        calculated_at=now,
    )
    database.add(decision)
    database.flush()
    if managed.decision == RiskDecisionKind.BLOCKED:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = list(managed.reason_codes)
        return
    entry = _current_price(instrument)
    if entry is None:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = ["CRITICAL_DATA_UNAVAILABLE"]
        return
    stop_fraction = _nested_decimal(version.definition, "stop", "value", Decimal("0.01"))
    reward = _nested_decimal(version.definition, "target", "value", Decimal("2"))
    direction = str(version.definition.get("direction", "LONG"))
    if direction == "BOTH":
        direction = "LONG"
    distance = entry * stop_fraction
    stop_price = entry - distance if direction == "LONG" else entry + distance
    target = entry + distance * reward if direction == "LONG" else entry - distance * reward
    specification = instrument.contract_spec
    tick_size = _optional_decimal(specification.get("tick_size"), Decimal("0"))
    tick_value = _optional_decimal(specification.get("tick_value"), Decimal("0"))
    point_value = tick_value / tick_size if tick_size > 0 and tick_value > 0 else Decimal("0")
    profit_currency = str(specification.get("currency_profit", account.currency)).upper()
    if point_value <= 0:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = ["INSTRUMENT_SIZING_DATA_UNAVAILABLE"]
        return
    volume = size_position(
        permitted_risk=managed.permitted_risk,
        entry=entry,
        stop=stop_price,
        point_value=point_value,
        minimum=_optional_decimal(specification.get("volume_min"), Decimal("0.01")),
        step=_optional_decimal(specification.get("volume_step"), Decimal("0.01")),
        conversion_quality_verified=profit_currency == account.currency.upper(),
    )
    if volume <= 0:
        opportunity.state = OpportunityState.NO_TRADE
        opportunity.reason_codes = ["VOLUME_BELOW_BROKER_MINIMUM"]
        return
    database.add(
        Recommendation(
            opportunity_id=opportunity.id,
            risk_decision_id=decision.id,
            state=RecommendationState.ISSUED,
            entry=entry,
            stop=stop_price,
            volume=volume,
            targets=[str(target)],
            invalidation=version.definition.get("invalidation", {}),
            reason_trace={
                "score": str(opportunity.score),
                "risk_decision": managed.decision,
                "risk_reason_codes": list(managed.reason_codes),
                "direction": direction,
                "strategy_definition_hash": version.definition_hash,
            },
            expires_at=opportunity.expires_at,
            created_at=now,
        )
    )


def _current_price(instrument: Instrument) -> Decimal | None:
    closes = instrument.contract_spec.get("closes")
    if isinstance(closes, list) and closes:
        return as_decimal(str(closes[-1]))
    bid = instrument.contract_spec.get("bid")
    ask = instrument.contract_spec.get("ask")
    if bid is not None and ask is not None:
        return (as_decimal(str(bid)) + as_decimal(str(ask))) / Decimal("2")
    return None


def _data_verified(instrument: Instrument) -> bool:
    closes = instrument.contract_spec.get("closes")
    return isinstance(closes, list) and len(closes) >= 10


def _signal_present(version: StrategyVersion, price: Decimal) -> bool:
    conditions = version.definition.get("conditions", [])
    if not isinstance(conditions, list) or not conditions:
        return False
    condition = conditions[0]
    if not isinstance(condition, dict):
        return False
    threshold = _optional_decimal(condition.get("value"), price)
    operator = str(condition.get("operator", ">"))
    return (
        price > threshold
        if operator == ">"
        else price < threshold
        if operator == "<"
        else price == threshold
    )


def _nested_decimal(payload: dict[str, object], group: str, key: str, default: Decimal) -> Decimal:
    value = payload.get(group)
    return as_decimal(str(value.get(key, default))) if isinstance(value, dict) else default


def _optional_decimal(value: object, default: Decimal) -> Decimal:
    return as_decimal(str(value)) if value is not None else default


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat()
