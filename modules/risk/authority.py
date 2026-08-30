from __future__ import annotations

from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.accounts.models import AccountSnapshot
from modules.accounts.snapshots import validate_snapshot
from modules.policy.models import EffectiveConstraint
from modules.risk.models import CandidateTrade, Direction, OpenPositionRisk, RiskContext
from modules.risk.reservations import (
    ACTIVE_RESERVATION_STATES,
    PositionRiskReservationRecord,
)
from packages.broker_sdk.schemas import BrokerSnapshot
from packages.shared.store import ResourceRecord, ResourceStore


def _category(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "")
    if normalized.startswith(("BTC", "ETH", "SOL", "XRP")):
        return "crypto"
    if normalized.startswith(("XAU", "XAG", "XPT", "XPD")):
        return "metals"
    return "forex"


def _currency_exposures(symbol: str) -> dict[str, Decimal]:
    normalized = symbol.upper().replace("-", "")
    if len(normalized) >= 6 and normalized[:6].isalpha():
        return {normalized[:3]: Decimal("1"), normalized[3:6]: Decimal("-1")}
    return {}


def _position_uuid(position_id: str) -> UUID:
    try:
        return UUID(position_id)
    except ValueError:
        return uuid5(NAMESPACE_URL, f"mt5-position:{position_id}")


async def authoritative_risk_context(
    db: AsyncSession,
    owner_id: UUID,
    account_id: UUID,
    candidate: CandidateTrade,
) -> RiskContext:
    """Build a fail-closed risk context from locked, persisted authority records."""
    account = await db.scalar(
        select(ResourceRecord)
        .where(
            ResourceRecord.id == account_id,
            ResourceRecord.owner_id == owner_id,
            ResourceRecord.kind == "account",
            ResourceRecord.state == "ACTIVE",
        )
        .with_for_update()
    )
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "active account not found")
    store = ResourceStore(db)
    snapshots = [
        item
        for item in await store.list("broker_snapshot", owner_id)
        if item.data.get("account_id") == str(account_id)
    ]
    if not snapshots:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "fresh broker equity snapshot required before risk evaluation",
        )
    broker = BrokerSnapshot.model_validate(snapshots[0].data)
    account_snapshot = AccountSnapshot(
        account_id=account_id,
        starting_balance=Decimal(str(account.data["starting_balance"])),
        current_balance=broker.balance,
        current_equity=broker.equity,
        floating_pnl=broker.equity - broker.balance,
        realized_daily_pnl=broker.realized_daily_pnl,
        observed_at=broker.observed_at,
        source="MT5_READ_ONLY_BRIDGE",
        source_version=f"sequence:{broker.sequence}",
    )
    try:
        validate_snapshot(account_snapshot, account_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    constraints: list[EffectiveConstraint] = []
    for kind, source_prefix in (("prop_ruleset", "prop"), ("guardrail", "internal")):
        for record in await store.list(kind, owner_id):
            if record.state != "ACTIVE":
                continue
            if record.data.get("account_id") not in {None, str(account_id)}:
                continue
            for rule in record.data.get("rules", []):
                constraints.append(
                    EffectiveConstraint(
                        kind=rule["kind"],
                        value=Decimal(str(rule["value"])),
                        source=f"{source_prefix}:{record.data.get('name', record.id)}",
                        source_version=str(record.version),
                        reason=str(
                            rule.get("reason")
                            or record.data.get("source_reference")
                            or "active policy"
                        ),
                        enforcement=rule.get("enforcement", "HARD"),
                    )
                )
    max_concurrent = min(
        (int(item.value) for item in constraints if item.kind.value == "MAX_CONCURRENT_TRADES"),
        default=3,
    )
    correlated_limit = min(
        (item.value for item in constraints if item.kind.value == "MAX_CORRELATED_RISK"),
        default=None,
    )
    positions = [
        OpenPositionRisk(
            position_id=_position_uuid(position.position_id),
            instrument=position.symbol,
            direction=Direction(position.direction.value),
            market_category=_category(position.symbol),
            currency_exposures=_currency_exposures(position.symbol),
            remaining_loss_to_stop=(
                abs(position.entry_price - position.stop_loss) * position.volume
                if position.stop_loss is not None
                else None
            ),
            unrealized_pnl=position.pnl,
        )
        for position in broker.positions
    ]
    exposure_groups = {
        f"category:{candidate.market_category}",
        *(f"currency:{key}" for key in candidate.currency_exposures),
    }
    specification_records = [
        *await store.list("instrument_specification", owner_id),
        *await store.list("typed_instrument", owner_id),
    ]
    specifications: dict[str, dict[str, Decimal | str]] = {}
    current_source_cut_id: str | None = None
    for record in specification_records:
        raw = record.data.get("specification", record.data)
        specification_id = raw.get("id") or record.data.get("specification_version_id")
        if specification_id is None:
            continue
        if str(raw.get("venue_instrument_id")) != str(candidate.venue_instrument_id):
            continue
        specifications[str(specification_id)] = {
            "freshness": str(raw.get("freshness", "INVALID")),
            "source_cut_id": str(
                raw.get("source_cut_id") or raw.get("provenance", {}).get("source_cut_id") or ""
            ),
            "contract_multiplier": Decimal(str(raw.get("contract_multiplier", "1"))),
            "tick_size": Decimal(str(raw.get("tick_size", "0"))),
            "tick_value": Decimal(str(raw.get("tick_value", "0") or "0")),
        }
        source_cut = specifications[str(specification_id)].get("source_cut_id")
        if source_cut:
            current_source_cut_id = str(source_cut)
    active_reservations = list(
        (
            await db.scalars(
                select(PositionRiskReservationRecord.amount).where(
                    PositionRiskReservationRecord.owner_id == owner_id,
                    PositionRiskReservationRecord.account_id == account_id,
                    PositionRiskReservationRecord.state.in_(ACTIVE_RESERVATION_STATES),
                )
            )
        ).all()
    )
    return RiskContext(
        account=account_snapshot,
        constraints=constraints,
        positions=positions,
        correlation_caps=(
            {group: correlated_limit for group in exposure_groups}
            if correlated_limit is not None
            else {}
        ),
        static_max_concurrent_trades=max_concurrent,
        include_unrealized_profit=False,
        instrument_specifications=specifications,
        current_source_cut_id=current_source_cut_id,
        active_reservations=[Decimal(str(item)) for item in active_reservations],
    )
