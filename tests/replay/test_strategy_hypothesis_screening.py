from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from modules.backtesting.engine import BacktestCandle, BacktestConfiguration
from modules.strategies.ai_workflow import StrategyHypothesis
from modules.strategies.screening import screen_hypotheses
from packages.strategy_sdk.schema import StrategySpecification


def specification(name: str, entry_operator: str, entry_value: str, exit_operator: str) -> dict:
    return {
        "name": name,
        "origin": "AI_GENERATED",
        "family": "TREND",
        "horizon": "INTRADAY",
        "instruments": ["EUR/USD"],
        "entry": [{"feature": "momentum", "operator": entry_operator, "value": entry_value}],
        "exit": [{"feature": "momentum", "operator": exit_operator, "value": "0"}],
        "stop_loss": {"feature": "volatility", "operator": ">", "value": "0"},
        "risk_per_trade": "0.5",
    }


def hypothesis(identifier: str, raw: dict) -> StrategyHypothesis:
    return StrategyHypothesis(
        hypothesis_id=identifier,
        specification=StrategySpecification.model_validate(raw),
        rationale="Grounded research hypothesis",
        breakdown=["one", "two", "three"],
        evidence_refs=["market-1", "history-1"],
        agent_id="strategy_researcher",
    )


def candles() -> list[BacktestCandle]:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    closes = [100, 101, 102, 101, 100, 102, 104, 103, 101, 103, 105, 104, 102, 106, 108]
    return [
        BacktestCandle(
            observed_at=start + timedelta(hours=index * 4),
            open=Decimal(str(close)),
            high=Decimal(str(close + 1)),
            low=Decimal(str(close - 1)),
            close=Decimal(str(close)),
            volume=Decimal("1000"),
        )
        for index, close in enumerate(closes)
    ]


def test_screening_is_deterministic_and_rejects_zero_trade_hypotheses() -> None:
    hypotheses = [
        hypothesis("H1", specification("Momentum", ">", "0", "<")),
        hypothesis("H2", specification("Reversal", "<", "0", ">")),
        hypothesis("H3", specification("Impossible", ">", "1000", "<")),
    ]
    config = BacktestConfiguration(initial_equity=Decimal("10000"))
    first = screen_hypotheses(hypotheses, candles(), config)
    second = screen_hypotheses(hypotheses, candles(), config)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.selected_hypothesis_id in {"H1", "H2"}
    rejected = {item.hypothesis_id: item for item in first.results}
    assert rejected["H3"].eligible is False
    assert "zero trades" in rejected["H3"].reasons
    assert first.label == "PRELIMINARY_RESEARCH_SCREEN"
