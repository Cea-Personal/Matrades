from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.backtesting.engine import Bar
from traderx.backtesting.execution import FillPolicy
from traderx.backtesting.report import exact_risk_units
from traderx.journal.projector import project_completed_activity
from traderx.market_data.model import Instrument
from traderx.paper.engine import simulate_current_data
from traderx.paper.evidence import PaperEligibility, assess_paper_evidence
from traderx.paper.model import PaperComparison, PaperRun, PaperTradeReference
from traderx.shared.types import InvalidTransition, as_decimal, utc_now
from traderx.strategies.model import Strategy, StrategyLifecycle, StrategyVersion
from traderx.validation.model import BacktestRun, EvidenceState, ValidationRun


@dataclass(frozen=True, slots=True)
class PaperTerminalDisposition:
    state: str
    reason_codes: tuple[str, ...]


def terminal_disposition(evidence: PaperEligibility) -> PaperTerminalDisposition:
    return PaperTerminalDisposition(evidence.disposition, evidence.reason_codes)


def execute_paper_run(
    database: Session,
    *,
    strategy_version_id: UUID,
    validation_run_id: UUID,
    evidence_manifest_hash: str | None,
) -> PaperRun:
    """Run a deterministic, simulated-only paper evaluation from current broker observations."""

    version = database.get(StrategyVersion, strategy_version_id)
    validation = database.get(ValidationRun, validation_run_id)
    if (
        version is None
        or validation is None
        or validation.strategy_version_id != strategy_version_id
    ):
        raise InvalidTransition("paper trading requires validation for this exact strategy version")
    if validation.state != EvidenceState.PASS:
        raise InvalidTransition("paper trading requires passing validation evidence")
    if evidence_manifest_hash and evidence_manifest_hash != validation.manifest_hash:
        raise InvalidTransition("paper trading evidence manifest no longer matches validation")
    strategy = database.get(Strategy, version.strategy_id)
    instrument = database.get(Instrument, strategy.instrument_id) if strategy else None
    if instrument is None:
        raise InvalidTransition("paper trading requires the strategy instrument")
    source_closes = instrument.contract_spec.get("closes", [])
    closes = (
        [as_decimal(str(value)) for value in source_closes]
        if isinstance(source_closes, list)
        else []
    )
    if len(closes) < 3:
        raise InvalidTransition("paper trading requires current market observations")

    direction = str(version.definition.get("direction", "LONG"))
    if direction == "BOTH":
        direction = "LONG"
    stop_fraction = _nested_decimal(version.definition, "stop", "value", Decimal("0.01"))
    reward_ratio = _nested_decimal(version.definition, "target", "value", Decimal("2"))
    spread = max(
        Decimal("0"),
        _optional_decimal(instrument.contract_spec.get("ask"))
        - _optional_decimal(instrument.contract_spec.get("bid")),
    )
    policy = FillPolicy(spread=spread, commission_per_unit=Decimal("0"), slippage_bps=Decimal("1"))
    risk_fraction = as_decimal(str(version.definition.get("risk_fraction", "0.01")))
    start = utc_now()
    trades = []
    # Each rolling slice is an independent current-data signal evaluation. The
    # same canonical fill engine and conservative stop-first policy are reused.
    for index in range(len(closes) - 2):
        entry = closes[index]
        distance = entry * stop_fraction
        stop = entry - distance if direction == "LONG" else entry + distance
        target = (
            entry + distance * reward_ratio
            if direction == "LONG"
            else entry - distance * reward_ratio
        )
        bars = _bars(closes[index : index + 3], start + timedelta(hours=index))
        units, sizing_quality = _risk_units(
            instrument.contract_spec,
            equity=Decimal("100000"),
            risk_fraction=risk_fraction,
            stop_distance=distance,
        )
        if units <= 0:
            continue
        simulated = simulate_current_data(
            bars,
            direction=direction,
            units=units,
            stop=stop,
            target=target,
            policy=policy,
        )
        if simulated:
            trades.append((simulated[0], stop, target))

    historical = database.scalar(
        select(BacktestRun).where(BacktestRun.id == validation.backtest_run_id).limit(1)
    )
    historical_expectancy = (
        as_decimal(str(historical.metrics.get("average_r", "0"))) if historical else Decimal("0")
    )
    paper_pnls = [trade.pnl for trade, _, _ in trades]
    paper_expectancy = (
        sum(paper_pnls, Decimal("0")) / Decimal(len(paper_pnls)) if paper_pnls else Decimal("0")
    )
    duration_days = max(1, (len(closes) - 1) // 24)
    maximum_divergence = Decimal("0.50")
    eligibility = assess_paper_evidence(
        trades=len(trades),
        duration_days=duration_days,
        historical_expectancy=historical_expectancy,
        paper_expectancy=paper_expectancy,
        maximum_divergence=maximum_divergence,
        validation_passed=True,
    )
    manifest = {
        "strategy_definition_hash": version.definition_hash,
        "validation_manifest_hash": validation.manifest_hash,
        "instrument_id": str(instrument.id),
        "instrument_version": instrument.version,
        "observations": [str(value) for value in closes],
        "execution_model": policy.version,
    }
    evidence_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    now = utc_now()
    run = PaperRun(
        strategy_version_id=version.id,
        validation_run_id=validation.id,
        state=eligibility.disposition,
        started_at=start,
        finished_at=now,
        metrics={
            "trades": len(trades),
            "duration_days": duration_days,
            "paper_expectancy": str(paper_expectancy),
            "historical_expectancy": str(historical_expectancy),
            "net_pnl": str(sum(paper_pnls, Decimal("0"))),
            "execution_model": policy.version,
            "same_bar_policy": "STOP_FIRST",
            "gross_pnl": str(sum((trade.gross_pnl for trade, _, _ in trades), Decimal("0"))),
            "total_costs": str(sum((trade.costs for trade, _, _ in trades), Decimal("0"))),
            "risk_fraction": str(risk_fraction),
            "risk_band": "LOW" if risk_fraction <= Decimal("0.005") else "STANDARD",
            "sizing_quality": sizing_quality if trades else "NO_TRADES",
            "maximum_concurrent_positions": 1,
        },
        criteria={
            "minimum_trades": 20,
            "minimum_duration_days": 14,
            "maximum_divergence": str(maximum_divergence),
            "reason_codes": list(eligibility.reason_codes),
            "eligible": eligibility.eligible,
        },
        evidence_hash=evidence_hash,
    )
    database.add(run)
    database.flush()
    for trade, stop, target in trades:
        database.add(
            PaperTradeReference(
                paper_run_id=run.id,
                entry=trade.entry,
                exit=trade.exit,
                stop=stop,
                target=target,
                units=trade.units,
                direction=trade.direction,
                pnl=trade.pnl,
                created_at=trade.entered_at,
            )
        )
    comparison = PaperComparison(
        paper_run_id=run.id,
        historical_manifest_hash=historical.manifest_hash
        if historical
        else validation.manifest_hash,
        divergence=abs(paper_expectancy - historical_expectancy),
        criteria=run.criteria,
        disposition=eligibility.disposition,
    )
    database.add(comparison)
    version.lifecycle = (
        StrategyLifecycle.AWAITING_APPROVAL
        if eligibility.eligible
        else StrategyLifecycle.PAPER_TRADING
    )
    database.flush()
    project_completed_activity(database)
    return run


def paper_run_payload(database: Session, run: PaperRun) -> dict[str, object]:
    trades = database.scalars(
        select(PaperTradeReference)
        .where(PaperTradeReference.paper_run_id == run.id)
        .order_by(PaperTradeReference.created_at)
    ).all()
    comparison = database.scalar(
        select(PaperComparison).where(PaperComparison.paper_run_id == run.id)
    )
    return {
        "id": str(run.id),
        "strategy_version_id": str(run.strategy_version_id),
        "validation_run_id": str(run.validation_run_id),
        "state": run.state,
        "metrics": run.metrics,
        "criteria": run.criteria,
        "evidence_hash": run.evidence_hash,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "comparison": {
            "divergence": str(comparison.divergence),
            "historical_manifest_hash": comparison.historical_manifest_hash,
            "disposition": comparison.disposition,
        }
        if comparison
        else None,
        "positions": [],
        "history": [
            {
                "id": str(trade.id),
                "entry": str(trade.entry),
                "exit": str(trade.exit) if trade.exit is not None else None,
                "stop": str(trade.stop),
                "target": str(trade.target),
                "units": str(trade.units),
                "direction": trade.direction,
                "pnl": str(trade.pnl),
                "created_at": _iso(trade.created_at),
            }
            for trade in trades
        ],
        "etag": f'"paper-run-{run.id}-{run.version}"',
    }


def _bars(closes: list[Decimal], start: datetime) -> list[Bar]:
    return [
        Bar(
            timestamp=start + timedelta(hours=index),
            open=value,
            high=value * Decimal("1.003"),
            low=value * Decimal("0.997"),
            close=value,
        )
        for index, value in enumerate(closes)
    ]


def _nested_decimal(payload: dict[str, object], group: str, key: str, default: Decimal) -> Decimal:
    value = payload.get(group)
    return as_decimal(str(value.get(key, default))) if isinstance(value, dict) else default


def _optional_decimal(value: object) -> Decimal:
    return as_decimal(str(value)) if value is not None else Decimal("0")


def _risk_units(
    spec: dict[str, object],
    *,
    equity: Decimal,
    risk_fraction: Decimal,
    stop_distance: Decimal,
) -> tuple[Decimal, str]:
    tick_size = _optional_decimal(spec.get("tick_size"))
    tick_value = _optional_decimal(spec.get("tick_value"))
    volume_step = _optional_decimal(spec.get("volume_step"))
    if min(tick_size, tick_value, volume_step) <= 0:
        return Decimal("1"), "FALLBACK_UNIT_FIXTURE"
    units = exact_risk_units(
        equity=equity,
        risk_fraction=risk_fraction,
        stop_distance=stop_distance,
        value_per_price_unit=tick_value / tick_size,
        volume_step=volume_step,
    )
    volume_min = _optional_decimal(spec.get("volume_min"))
    volume_max = _optional_decimal(spec.get("volume_max"))
    if volume_min > 0 and units < volume_min:
        return Decimal("0"), "BELOW_MINIMUM_VOLUME"
    if volume_max > 0:
        units = min(units, volume_max)
    return units, "VERIFIED"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
