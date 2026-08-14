from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.journal.model import JournalEntry
from traderx.monitoring.position_model import Position, TradeExecution
from traderx.opportunities.model import Opportunity
from traderx.opportunities.recommendation_model import Recommendation
from traderx.paper.model import PaperRun
from traderx.shared.types import as_decimal, utc_now
from traderx.strategies.model import Strategy, StrategyVersion


@dataclass(frozen=True, slots=True)
class JournalProjection:
    gross_pnl: Decimal
    net_pnl: Decimal
    r_multiple: Decimal | None


def project_trade(
    *,
    entry: Decimal,
    exit: Decimal,
    units: Decimal,
    direction: str,
    costs: Decimal,
    initial_risk: Decimal,
) -> JournalProjection:
    sign = Decimal("1") if direction == "LONG" else Decimal("-1")
    gross = (exit - entry) * units * sign
    net = gross - costs
    return JournalProjection(gross, net, net / initial_risk if initial_risk > 0 else None)


def project_completed_activity(database: Session) -> list[JournalEntry]:
    """Create immutable journal rows once for closed broker positions and paper runs."""

    created: list[JournalEntry] = []
    for position in database.scalars(select(Position).where(Position.closed_at.is_not(None))):
        if database.scalar(select(JournalEntry.id).where(JournalEntry.position_id == position.id)):
            continue
        executions = database.scalars(
            select(TradeExecution)
            .where(TradeExecution.position_id == position.id)
            .order_by(TradeExecution.occurred_at)
        ).all()
        if len(executions) < 2:
            continue
        broker_profit = sum(
            (as_decimal(str(item.payload.get("profit", 0))) for item in executions),
            Decimal("0"),
        )
        broker_costs = sum(
            (
                as_decimal(str(item.payload.get("commission", 0)))
                + as_decimal(str(item.payload.get("swap", 0)))
                + as_decimal(str(item.payload.get("fee", 0)))
                for item in executions
            ),
            Decimal("0"),
        )
        if any("profit" in item.payload for item in executions):
            net = broker_profit + broker_costs
            initial_risk = as_decimal(str(position.open_risk))
            outcome = JournalProjection(
                broker_profit,
                net,
                net / initial_risk if initial_risk > 0 else None,
            )
        else:
            outcome = project_trade(
                entry=as_decimal(str(executions[0].price)),
                exit=as_decimal(str(executions[-1].price)),
                units=as_decimal(str(position.volume)),
                direction=position.direction,
                costs=Decimal("0"),
                initial_risk=as_decimal(str(position.open_risk)),
            )
        recommendation = (
            database.get(Recommendation, position.matched_recommendation_id)
            if position.matched_recommendation_id
            else None
        )
        opportunity = (
            database.get(Opportunity, recommendation.opportunity_id) if recommendation else None
        )
        entry = JournalEntry(
            position_id=position.id,
            paper_run_id=None,
            source_type=position.classification,
            instrument_id=position.instrument_id,
            gross_pnl=outcome.gross_pnl,
            net_pnl=outcome.net_pnl,
            r_multiple=outcome.r_multiple,
            evidence={
                "direction": position.direction,
                "provider_position_id": position.provider_position_id,
                "classification": position.classification,
                "execution_ids": [str(item.id) for item in executions],
                "strategy_version_id": (
                    str(opportunity.strategy_version_id) if opportunity else None
                ),
                "risk_band": _risk_band(as_decimal(str(position.open_risk))),
                "financial_source": (
                    "BROKER_DEAL_PROFIT_AND_COSTS"
                    if any("profit" in item.payload for item in executions)
                    else "PRICE_DIFFERENCE_FALLBACK"
                ),
            },
            correction_of_id=None,
            closed_at=position.closed_at,
        )
        database.add(entry)
        created.append(entry)
    for run in database.scalars(select(PaperRun).where(PaperRun.finished_at.is_not(None))):
        if database.scalar(select(JournalEntry.id).where(JournalEntry.paper_run_id == run.id)):
            continue
        version = database.get(StrategyVersion, run.strategy_version_id)
        strategy = database.get(Strategy, version.strategy_id) if version else None
        net = as_decimal(str(run.metrics.get("net_pnl", "0")))
        gross = as_decimal(str(run.metrics.get("gross_pnl", net)))
        multiple_value = run.metrics.get("r_multiple")
        entry = JournalEntry(
            position_id=None,
            paper_run_id=run.id,
            source_type="PAPER",
            instrument_id=strategy.instrument_id if strategy else None,
            gross_pnl=gross,
            net_pnl=net,
            r_multiple=(as_decimal(str(multiple_value)) if multiple_value is not None else None),
            evidence={
                "direction": version.definition.get("direction") if version else "UNKNOWN",
                "strategy_version_id": str(version.id) if version else None,
                "paper_evidence_hash": run.evidence_hash,
                "risk_band": str(run.metrics.get("risk_band", "UNRECORDED")),
                "regime": str(run.metrics.get("regime", "UNRECORDED")),
            },
            correction_of_id=None,
            closed_at=run.finished_at or utc_now(),
        )
        database.add(entry)
        created.append(entry)
    database.flush()
    return created


def _risk_band(open_risk: Decimal) -> str:
    if open_risk <= 0:
        return "UNVERIFIED"
    if open_risk < Decimal("50"):
        return "LOW"
    if open_risk < Decimal("200"):
        return "MEDIUM"
    return "HIGH"
