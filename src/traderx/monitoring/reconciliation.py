from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.market_data.model import Instrument
from traderx.monitoring.matching import classify_position, recommendation_match_confidence
from traderx.monitoring.monitor import evaluate_thesis
from traderx.monitoring.position_model import Position, TradeExecution
from traderx.monitoring.risk_projection import project_shared_risk
from traderx.monitoring.thesis_model import MonitoringObservation, TradeThesis
from traderx.opportunities.model import Opportunity
from traderx.opportunities.recommendation_model import Recommendation, RecommendationState
from traderx.risk.model import RiskSnapshot
from traderx.shared.types import as_decimal, utc_now


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    event_id: str
    sequence: int
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    accepted: tuple[ProviderEvent, ...]
    reason_codes: tuple[str, ...]


def reconcile(
    events: list[ProviderEvent],
    *,
    last_sequence: int,
    known_event_ids: frozenset[str] = frozenset(),
) -> ReconciliationResult:
    deduplicated: dict[str, ProviderEvent] = {}
    reasons: list[str] = []
    sequence_ids: dict[int, str] = {}
    for event in events:
        previous = deduplicated.get(event.event_id)
        if previous is not None and previous != event:
            reasons.append("CONTRADICTORY_PROVIDER_EVENT")
            continue
        other_id = sequence_ids.get(event.sequence)
        if other_id is not None and other_id != event.event_id:
            reasons.append("CONTRADICTORY_PROVIDER_SEQUENCE")
        sequence_ids[event.sequence] = event.event_id
        deduplicated[event.event_id] = event
    ordered = tuple(sorted(deduplicated.values(), key=lambda event: event.sequence))
    new_events = tuple(
        event
        for event in ordered
        if event.sequence > last_sequence and event.event_id not in known_event_ids
    )
    if new_events and new_events[0].sequence > last_sequence + 1:
        reasons.append("PROVIDER_SEQUENCE_GAP")
    if any(event.sequence <= last_sequence or event.event_id in known_event_ids for event in ordered):
        reasons.append("OVERLAPPING_WINDOW_DEDUPLICATED")
    return ReconciliationResult(new_events, tuple(sorted(set(reasons))))


def project_mt5_positions(
    database: Session,
    account: TradingAccount,
    positions: list[dict[str, object]],
    deals: list[dict[str, object]],
) -> list[Position]:
    """Project the complete read-only MT5 position set and append newly observed deals."""

    _reject_snapshot_contradictions(positions, deals)
    now = utc_now()
    instruments = {
        instrument.symbol: instrument for instrument in database.scalars(select(Instrument))
    }
    existing = {
        position.provider_position_id: position
        for position in database.scalars(select(Position).where(Position.account_id == account.id))
    }
    seen: set[str] = set()
    projected: list[Position] = []
    for source in positions:
        provider_id = _text(source, "identifier") or _text(source, "ticket")
        symbol = _text(source, "symbol")
        instrument = instruments.get(symbol)
        if not provider_id or instrument is None:
            continue
        seen.add(provider_id)
        direction = "LONG" if int(str(source.get("type", 0))) == 0 else "SHORT"
        opened_at = _from_milliseconds(source.get("time_msc"))
        open_price = _decimal(source.get("price_open"))
        stop = _decimal(source.get("stop_loss"))
        tick_value = _decimal(instrument.contract_spec.get("tick_value"), Decimal("1"))
        volume = _decimal(source.get("volume"))
        open_risk = abs(open_price - stop) * volume * tick_value if stop > 0 else Decimal("0")
        position = existing.get(provider_id)
        if position is None:
            recommendation, confidence = _match_recommendation(
                database, instrument.id, direction, open_price, opened_at
            )
            match = classify_position(
                recommendation_id=str(recommendation.id) if recommendation else None,
                confidence=confidence,
            )
            position = Position(
                account_id=account.id,
                instrument_id=instrument.id,
                provider_position_id=provider_id,
                direction=direction,
                volume=volume,
                open_risk=open_risk,
                classification=match.classification,
                matched_recommendation_id=recommendation.id if recommendation else None,
                match_confidence=match.confidence,
                classification_reason=match.reason,
                provider_revision=1,
                opened_at=opened_at,
                closed_at=None,
            )
            database.add(position)
            database.flush()
            if recommendation is not None:
                _freeze_recommendation_thesis(database, position, recommendation, now)
        else:
            position.volume = volume
            position.open_risk = open_risk
            position.provider_revision += 1
            position.closed_at = None
        projected.append(position)
        _append_health(database, position, source, now)
    for provider_id, position in existing.items():
        if provider_id not in seen and position.closed_at is None:
            position.closed_at = now
            position.provider_revision += 1
    _project_deals(database, projected + list(existing.values()), deals)
    _project_shared_position_risk(database, account, projected)
    database.flush()
    return projected


def position_payload(database: Session, position: Position) -> dict[str, object]:
    instrument = database.get(Instrument, position.instrument_id)
    return {
        "id": str(position.id),
        "provider_position_id": position.provider_position_id,
        "symbol": instrument.symbol if instrument else "UNKNOWN",
        "category": instrument.category if instrument else "UNKNOWN",
        "direction": position.direction,
        "volume": str(position.volume),
        "open_risk": str(position.open_risk),
        "classification": position.classification,
        "matched_recommendation_id": str(position.matched_recommendation_id)
        if position.matched_recommendation_id
        else None,
        "match_confidence": str(position.match_confidence),
        "classification_reason": position.classification_reason,
        "provider_revision": position.provider_revision,
        "opened_at": _aware(position.opened_at).isoformat(),
        "closed_at": _aware(position.closed_at).isoformat() if position.closed_at else None,
        "etag": f'"position-{position.id}-{position.version}"',
    }


def thesis_payload(database: Session, position: Position) -> dict[str, object]:
    thesis = database.scalar(select(TradeThesis).where(TradeThesis.position_id == position.id))
    if thesis is None:
        return {
            "position_id": str(position.id),
            "immutable": True,
            "thesis": None,
            "observations": [],
        }
    observations = database.scalars(
        select(MonitoringObservation)
        .where(MonitoringObservation.thesis_id == thesis.id)
        .order_by(MonitoringObservation.observed_at)
    ).all()
    return {
        "position_id": str(position.id),
        "immutable": True,
        "thesis": {
            "id": str(thesis.id),
            "frozen_evidence": thesis.frozen_evidence,
            "created_at": _aware(thesis.created_at).isoformat(),
        },
        "observations": [
            {
                "id": str(item.id),
                "health": item.health,
                "evidence": item.evidence,
                "observed_at": _aware(item.observed_at).isoformat(),
            }
            for item in observations
        ],
    }


def _match_recommendation(
    database: Session, instrument_id: object, direction: str, price: Decimal, opened_at: datetime
) -> tuple[Recommendation | None, Decimal]:
    recommendations = database.scalars(
        select(Recommendation)
        .join(Opportunity, Opportunity.id == Recommendation.opportunity_id)
        .where(
            Opportunity.instrument_id == instrument_id,
            Recommendation.state == RecommendationState.ISSUED,
            Recommendation.created_at <= opened_at,
            Recommendation.expires_at >= opened_at,
        )
        .order_by(Recommendation.created_at.desc())
    ).all()
    for recommendation in recommendations:
        recommended_direction = str(recommendation.reason_trace.get("direction", "LONG"))
        confidence = recommendation_match_confidence(
            position_direction=direction,
            recommendation_direction=recommended_direction,
            position_price=price,
            recommendation_price=as_decimal(str(recommendation.entry)),
            position_opened_at=opened_at,
            recommendation_created_at=_aware(recommendation.created_at),
            recommendation_expires_at=_aware(recommendation.expires_at),
        )
        if confidence >= Decimal("0.8"):
            return recommendation, confidence
    return None, Decimal("0")


def _freeze_recommendation_thesis(
    database: Session, position: Position, recommendation: Recommendation, now: datetime
) -> None:
    database.add(
        TradeThesis(
            position_id=position.id,
            recommendation_id=recommendation.id,
            frozen_evidence={
                "entry": str(recommendation.entry),
                "stop": str(recommendation.stop),
                "targets": recommendation.targets,
                "invalidation": recommendation.invalidation,
                "reason_trace": recommendation.reason_trace,
                "recommendation_evidence_created_at": _aware(recommendation.created_at).isoformat(),
            },
            created_at=now,
        )
    )


def _append_health(
    database: Session, position: Position, source: dict[str, object], now: datetime
) -> None:
    thesis = database.scalar(select(TradeThesis).where(TradeThesis.position_id == position.id))
    if thesis is None:
        return
    stop = _decimal(thesis.frozen_evidence.get("stop"))
    entry = _decimal(thesis.frozen_evidence.get("entry"))
    current = _decimal(source.get("price_current"), entry)
    guidance = evaluate_thesis(
        current_price=current,
        invalidation_price=stop,
        favorable_distance=abs(entry - stop),
        direction=position.direction,
    )
    database.add(
        MonitoringObservation(
            thesis_id=thesis.id,
            health=guidance.health,
            evidence={"current_price": str(current), "reason_codes": list(guidance.reason_codes)},
            observed_at=now,
        )
    )


def _project_deals(
    database: Session, positions: list[Position], deals: list[dict[str, object]]
) -> None:
    by_provider = {position.provider_position_id: position for position in positions}
    known = set(database.scalars(select(TradeExecution.provider_deal_id)))
    for source in deals:
        deal_id = _text(source, "ticket")
        provider_position_id = _text(source, "position_id")
        position = by_provider.get(provider_position_id)
        if not deal_id or deal_id in known or position is None:
            continue
        database.add(
            TradeExecution(
                position_id=position.id,
                provider_deal_id=deal_id,
                occurred_at=_from_milliseconds(source.get("time_msc")),
                price=_decimal(source.get("price")),
                volume=_decimal(source.get("volume")),
                payload={str(key): value for key, value in source.items()},
            )
        )
        known.add(deal_id)


def _project_shared_position_risk(
    database: Session, account: TradingAccount, positions: list[Position]
) -> None:
    risk = database.scalar(
        select(RiskSnapshot)
        .where(RiskSnapshot.account_id == account.id)
        .order_by(RiskSnapshot.calculated_at.desc())
        .limit(1)
    )
    if risk is None:
        return
    project_shared_risk(risk, [as_decimal(str(position.open_risk)) for position in positions])


def _reject_snapshot_contradictions(
    positions: list[dict[str, object]], deals: list[dict[str, object]]
) -> None:
    for records, identity_fields, label in (
        (positions, ("identifier", "ticket"), "position"),
        (deals, ("ticket",), "deal"),
    ):
        seen: dict[str, dict[str, object]] = {}
        for source in records:
            identity = next(
                (_text(source, field) for field in identity_fields if _text(source, field)), ""
            )
            if not identity:
                continue
            previous = seen.get(identity)
            if previous is not None and previous != source:
                from traderx.shared.types import InvalidTransition

                raise InvalidTransition(f"contradictory MT5 {label} revisions were received")
            seen[identity] = source


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None else ""


def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    return as_decimal(str(value)) if value is not None and value != "" else default


def _from_milliseconds(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(str(value)) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return utc_now()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
