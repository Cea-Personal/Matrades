from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from traderx.backtesting.engine import Bar, replay
from traderx.backtesting.execution import FillPolicy
from traderx.backtesting.report import report
from traderx.market_data.model import Instrument
from traderx.shared.types import InvalidTransition, as_decimal, utc_now
from traderx.strategies.model import Strategy, StrategyLifecycle, StrategyVersion
from traderx.validation.model import BacktestRun, EvidenceState, ValidationRun
from traderx.validation.monte_carlo import BootstrapMode, stressed_bootstrap
from traderx.validation.out_of_sample import chronological_split, rolling_walk_forward
from traderx.validation.portfolio import PortfolioSignal, simulate_shared_account
from traderx.validation.stability import assess_parameter_stability


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    state: EvidenceState
    reason_codes: tuple[str, ...]


def aggregate_validation(
    *, out_of_sample_passed: bool, stability: str, portfolio_safe: bool, monte_carlo_passed: bool
) -> ValidationDecision:
    failures: list[str] = []
    warnings: list[str] = []
    if not out_of_sample_passed:
        failures.append("OUT_OF_SAMPLE_FAILED")
    if stability == "SENSITIVE":
        warnings.append("PARAMETER_SENSITIVITY_WARNING")
    elif stability != "STABLE":
        failures.append("PARAMETER_STABILITY_FAILED")
    if not portfolio_safe:
        failures.append("PORTFOLIO_SAFETY_FAILED")
    if not monte_carlo_passed:
        failures.append("TAIL_RISK_FAILED")
    state = EvidenceState.FAIL if failures else EvidenceState.WARNING if warnings else EvidenceState.PASS
    return ValidationDecision(state, tuple((*failures, *warnings)))


def execute_backtest(
    database: Session,
    *,
    strategy_version_id: UUID,
    requested_manifest_hash: str | None = None,
) -> BacktestRun:
    version, instrument = _version_and_instrument(database, strategy_version_id)
    closes = _closes(instrument)
    if len(closes) < 10:
        raise InvalidTransition("the strategy instrument has insufficient historical observations")
    definition = version.definition
    direction = str(definition.get("direction", "LONG"))
    if direction == "BOTH":
        direction = "LONG"
    entry = closes[0]
    stop_fraction = _nested_decimal(definition, "stop", "value", Decimal("0.01"))
    reward_ratio = _nested_decimal(definition, "target", "value", Decimal("2"))
    stop_distance = entry * stop_fraction
    stop = entry - stop_distance if direction == "LONG" else entry + stop_distance
    target = (
        entry + stop_distance * reward_ratio
        if direction == "LONG"
        else entry - stop_distance * reward_ratio
    )
    bars = _bars(closes)
    spread = _optional_decimal(
        instrument.contract_spec.get("ask"), Decimal("0")
    ) - _optional_decimal(instrument.contract_spec.get("bid"), Decimal("0"))
    policy = FillPolicy(
        spread=max(Decimal("0"), spread),
        commission_per_unit=Decimal("0"),
        slippage_bps=Decimal("1"),
    )
    trades = replay(
        bars,
        direction=direction,
        units=Decimal("1"),
        policy=policy,
        stop=stop,
        target=target,
    )
    metrics = report(
        trades,
        initial_equity=Decimal("100000"),
        risk_per_trade=stop_distance,
    )
    manifest = {
        "strategy_definition_hash": version.definition_hash,
        "instrument_id": str(instrument.id),
        "instrument_version": instrument.version,
        "observations": [str(value) for value in closes],
        "execution_model": policy.version,
        "requested_manifest_hash": requested_manifest_hash,
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run = BacktestRun(
        strategy_version_id=version.id,
        manifest_hash=manifest_hash,
        execution_model_version=policy.version,
        artifact_ref=None,
        metrics={
            "net_pnl": str(metrics.net_pnl),
            "win_rate": str(metrics.win_rate),
            "average_r": str(metrics.average_r),
            "maximum_drawdown": str(metrics.maximum_drawdown),
            "gross_pnl": str(metrics.gross_pnl),
            "total_costs": str(metrics.total_costs),
            "profit_factor": str(metrics.profit_factor) if metrics.profit_factor is not None else None,
            "maximum_mae": str(metrics.maximum_mae),
            "maximum_mfe": str(metrics.maximum_mfe),
            "equity_curve": [str(value) for value in metrics.equity_curve],
            "r_distribution": [str(value) for value in metrics.r_distribution],
            "trades": metrics.trades,
            "direction": direction,
            "entry": str(trades[0].entry) if trades else None,
            "exit": str(trades[0].exit) if trades else None,
            "stop": str(stop),
            "target": str(target),
            "same_bar_policy": "STOP_FIRST",
        },
        state=EvidenceState.PASS,
        created_at=utc_now(),
    )
    database.add(run)
    version.lifecycle = StrategyLifecycle.VALIDATING
    database.flush()
    return run


def execute_validation(
    database: Session,
    *,
    strategy_version_id: UUID,
    backtest_run_id: UUID,
    seed: int,
    requested_manifest_hash: str | None = None,
) -> ValidationRun:
    version, instrument = _version_and_instrument(database, strategy_version_id)
    backtest = database.get(BacktestRun, backtest_run_id)
    if (
        backtest is None
        or backtest.strategy_version_id != version.id
        or backtest.state != EvidenceState.PASS
    ):
        raise InvalidTransition("validation requires a completed backtest for this exact version")
    closes = _closes(instrument)
    splits = chronological_split(closes)
    direction = str(version.definition.get("direction", "LONG"))
    if direction == "BOTH":
        direction = "LONG"
    out_of_sample_passed = _segment_passed(splits.out_of_sample, direction)
    segment_outcomes = [
        _segment_return(segment, direction)
        for segment in (splits.development, splits.validation, splits.out_of_sample)
        if len(segment) >= 2
    ]
    stability = assess_parameter_stability(segment_outcomes, threshold=Decimal("0.50"))
    returns = [
        (current - previous) / previous
        for previous, current in zip(closes, closes[1:], strict=False)
        if previous > 0
    ]
    simulations_by_mode = {
        mode.value: stressed_bootstrap(
            returns,
            trials=100,
            seed=seed,
            mode=mode,
            block_size=5,
            cost_stress=Decimal("0.00001"),
            gap_stress=Decimal("0.0001"),
        )
        for mode in BootstrapMode
    }
    simulations = [value for values in simulations_by_mode.values() for value in values]
    monte_carlo_passed = min(simulations) > Decimal("-0.20")
    portfolio = simulate_shared_account(
        [PortfolioSignal(str(version.id), Decimal("1"), Decimal("0.01"), Decimal("0"))],
        capacity=2,
        correlation_limit=Decimal("0.75"),
        maximum_open_risk=Decimal("0.02"),
    )
    portfolio_safe = len(portfolio.selected) == 1 and not portfolio.prop_breach
    decision = aggregate_validation(
        out_of_sample_passed=out_of_sample_passed,
        stability=stability.classification,
        portfolio_safe=portfolio_safe,
        monte_carlo_passed=monte_carlo_passed,
    )
    evidence = {
        "out_of_sample": {
            "state": "PASS" if out_of_sample_passed else "FAIL",
            "observations": len(splits.out_of_sample),
        },
        "walk_forward": {
            "state": "PASS" if len(segment_outcomes) == 3 else "FAIL",
            "windows": len(
                rolling_walk_forward(
                    closes,
                    training_size=max(2, len(closes) // 2),
                    validation_size=max(1, len(closes) // 6),
                    out_of_sample_size=max(1, len(closes) // 6),
                    step=max(1, len(closes) // 12),
                )
            ),
            "returns": [str(value) for value in segment_outcomes],
        },
        "parameter_stability": {
            "state": stability.classification,
            "dispersion": str(stability.dispersion),
            "positive_fraction": str(stability.positive_fraction),
            "trials": stability.trials,
        },
        "monte_carlo": {
            "state": "PASS" if monte_carlo_passed else "FAIL",
            "seed": seed,
            "trials": len(simulations),
            "modes": {key: len(values) for key, values in simulations_by_mode.items()},
            "minimum_terminal_return": str(min(simulations)),
            "p05_terminal_return": str(sorted(simulations)[max(0, len(simulations) // 20 - 1)]),
            "maximum_terminal_return": str(max(simulations)),
        },
        "portfolio": {
            "state": "PASS" if portfolio_safe else "FAIL",
            "maximum_positions": 2,
            "selected_signals": len(portfolio.selected),
            "peak_open_risk": str(portfolio.peak_open_risk),
            "blocked": [list(item) for item in portfolio.blocked],
        },
        "reason_codes": list(decision.reason_codes),
    }
    manifest = {
        "strategy_definition_hash": version.definition_hash,
        "backtest_manifest_hash": backtest.manifest_hash,
        "instrument_version": instrument.version,
        "seed": seed,
        "requested_manifest_hash": requested_manifest_hash,
    }
    run = ValidationRun(
        strategy_version_id=version.id,
        backtest_run_id=backtest.id,
        manifest_hash=hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        seed=seed,
        evidence=evidence,
        state=decision.state,
        created_at=utc_now(),
    )
    database.add(run)
    version.lifecycle = (
        StrategyLifecycle.BACKTEST_PASSED
        if decision.state == EvidenceState.PASS
        else StrategyLifecycle.FAILED
    )
    database.flush()
    return run


def backtest_payload(run: BacktestRun) -> dict[str, object]:
    return {
        "id": str(run.id),
        "strategy_version_id": str(run.strategy_version_id),
        "manifest_hash": run.manifest_hash,
        "execution_model_version": run.execution_model_version,
        "metrics": run.metrics,
        "state": run.state,
        "created_at": run.created_at.isoformat(),
    }


def validation_payload(run: ValidationRun) -> dict[str, object]:
    return {
        "id": str(run.id),
        "strategy_version_id": str(run.strategy_version_id),
        "backtest_run_id": str(run.backtest_run_id),
        "manifest_hash": run.manifest_hash,
        "seed": run.seed,
        "evidence": run.evidence,
        "state": run.state,
        "created_at": run.created_at.isoformat(),
    }


def _version_and_instrument(
    database: Session, strategy_version_id: UUID
) -> tuple[StrategyVersion, Instrument]:
    version = database.get(StrategyVersion, strategy_version_id)
    if version is None:
        raise InvalidTransition("the requested strategy version does not exist")
    strategy = database.get(Strategy, version.strategy_id)
    instrument = database.get(Instrument, strategy.instrument_id) if strategy else None
    if strategy is None or instrument is None:
        raise InvalidTransition("the strategy has no valid instrument")
    return version, instrument


def _closes(instrument: Instrument) -> list[Decimal]:
    values = instrument.contract_spec.get("closes", [])
    if not isinstance(values, list):
        return []
    try:
        return [as_decimal(str(value)) for value in values]
    except ValueError:
        return []


def _bars(closes: list[Decimal]) -> list[Bar]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars: list[Bar] = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        high = max(previous, close)
        low = min(previous, close)
        padding = max(close * Decimal("0.0001"), Decimal("0.00001"))
        bars.append(
            Bar(start + timedelta(hours=index), previous, high + padding, low - padding, close)
        )
    return bars


def _nested_decimal(
    definition: dict[str, object], section: str, key: str, default: Decimal
) -> Decimal:
    value = definition.get(section)
    if not isinstance(value, dict):
        return default
    return _optional_decimal(value.get(key), default)


def _optional_decimal(value: object, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        return as_decimal(str(value))
    except ValueError:
        return default


def _segment_return(values: list[Decimal], direction: str) -> Decimal:
    if len(values) < 2 or values[0] == 0:
        return Decimal("0")
    # Normalize by interval count before comparing unequal chronological windows.
    result = (values[-1] - values[0]) / values[0] / Decimal(len(values) - 1)
    return result if direction == "LONG" else -result


def _segment_passed(values: list[Decimal], direction: str) -> bool:
    return len(values) >= 2 and _segment_return(values, direction) > 0
