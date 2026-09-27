"""Deterministic preliminary screening on data withheld from strategy agents."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from modules.backtesting.engine import (
    BacktestCandle,
    BacktestConfiguration,
    PointInTimeBacktester,
)
from modules.strategies.ai_workflow import StrategyHypothesis


class HypothesisScreenResult(BaseModel):
    hypothesis_id: str
    eligible: bool
    score: Decimal
    reasons: list[str] = Field(default_factory=list)
    trade_count: int
    net_profit: Decimal
    passed_gates: int
    gates: dict[str, bool]
    family: str
    regime_performance: dict = Field(default_factory=dict)


class PreliminaryScreen(BaseModel):
    label: str = "PRELIMINARY_RESEARCH_SCREEN"
    formal_validation: bool = False
    selected_hypothesis_id: str | None
    results: list[HypothesisScreenResult]


def screen_hypotheses(
    hypotheses: list[StrategyHypothesis],
    holdout: list[BacktestCandle],
    configuration: BacktestConfiguration,
    *,
    calendar: list[dict] | None = None,
) -> PreliminaryScreen:
    results: list[HypothesisScreenResult] = []
    for hypothesis in sorted(hypotheses, key=lambda item: item.hypothesis_id):
        backtest = PointInTimeBacktester().run(
            hypothesis.specification, holdout, configuration, calendar=calendar
        )
        net_profit = Decimal(backtest.metrics["net_profit"])
        passed_gates = sum(backtest.gates.values())
        reasons: list[str] = []
        if backtest.trade_count == 0:
            reasons.append("zero trades")
        if net_profit <= 0:
            reasons.append("non-positive net profit after costs")
        eligible = not reasons
        score = Decimal(backtest.metrics["r"])
        results.append(
            HypothesisScreenResult(
                hypothesis_id=hypothesis.hypothesis_id,
                eligible=eligible,
                score=score,
                reasons=reasons,
                trade_count=backtest.trade_count,
                net_profit=net_profit,
                passed_gates=passed_gates,
                gates=backtest.gates,
                family=hypothesis.specification.family.value,
                regime_performance=backtest.regime_performance,
            )
        )
    eligible_results = [item for item in results if item.eligible]
    selected = (
        sorted(
            eligible_results, key=lambda item: (-item.passed_gates, -item.score, item.hypothesis_id)
        )[0]
        if eligible_results
        else None
    )
    return PreliminaryScreen(
        selected_hypothesis_id=selected.hypothesis_id if selected else None,
        results=results,
    )


def retain_family_alternatives(
    hypotheses: list[StrategyHypothesis], screen: PreliminaryScreen
) -> list[StrategyHypothesis]:
    """Retain positive CFD family/direction alternatives, not just one global winner."""
    by_id = {h.hypothesis_id: h for h in hypotheses}
    chosen = {}
    for result in sorted(
        screen.results, key=lambda r: (-r.passed_gates, -r.score, r.hypothesis_id)
    ):
        hypothesis = by_id[result.hypothesis_id]
        spec = hypothesis.specification
        if not result.eligible or spec.instrument_type != "CFD" or spec.trade_rules is None:
            continue
        chosen.setdefault((spec.family.value, spec.trade_rules.direction), hypothesis)
    return list(chosen.values())
