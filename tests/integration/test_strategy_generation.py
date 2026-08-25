from __future__ import annotations

from copy import deepcopy

import pytest

from modules.strategies.ai_workflow import StrategyGenerationWorkflow
from packages.strategy_sdk.taxonomy import StrategyOrigin


def strategy(name: str) -> dict:
    return {
        "name": name,
        "family": "TREND",
        "horizon": "INTRADAY",
        "instruments": ["EUR/USD"],
        "regimes": ["TRENDING"],
        "data_dependencies": ["historical:history-1"],
        "entry": [{"feature": "momentum", "operator": ">", "value": "0"}],
        "confirmations": [],
        "filters": [],
        "exit": [{"feature": "momentum", "operator": "<", "value": "0"}],
        "invalidation": [],
        "stop_loss": {"feature": "volatility", "operator": ">", "value": "0"},
        "take_profit": [{"feature": "momentum", "operator": ">=", "value": "0"}],
        "position_management": {
            "move_to_break_even": True,
            "trailing_stop": False,
            "partial_take_profit": False,
        },
        "sessions": ["LONDON"],
        "event_rules": ["block_high_impact_events"],
        "risk_per_trade": "0.5",
        "parameters": {},
    }


def evidence_pack() -> dict:
    return {
        "selection_id": "selection-1",
        "research_run_id": "market-run-1",
        "account_id": "account-1",
        "instrument": "EUR/USD",
        "category": "FOREX",
        "market_fingerprint": {
            "regime": "TRENDING",
            "observed_at": "2026-08-25T08:00:00Z",
            "source": "TWELVE_DATA",
            "source_version": "v1",
        },
        "historical_discovery": {
            "reference_id": "history-1",
            "candle_count": 70,
            "start_at": "2026-07-01T00:00:00Z",
            "end_at": "2026-08-10T00:00:00Z",
            "summary": {"return": "0.02", "volatility": "0.004"},
        },
        "references": [
            {"id": "market-1", "kind": "market_fingerprint", "summary": "Trending"},
            {"id": "history-1", "kind": "historical_discovery", "summary": "70 candles"},
        ],
    }


class FixtureStrategyAgents:
    def __init__(self, *, invalid_reference: bool = False) -> None:
        self.invoked: list[str] = []
        self.payload: dict = {}
        self.invalid_reference = invalid_reference

    async def invoke(self, logical_id: str, payload: dict, output_schema: dict) -> dict:
        self.invoked.append(logical_id)
        self.payload = payload
        assert payload["origin"] in {"AI_GENERATED", "AI_ASSISTED"}
        assert output_schema["properties"]["hypotheses"]["minItems"] == 3
        hypotheses = []
        for index in range(3):
            hypotheses.append(
                {
                    "hypothesis_id": f"H{index + 1}",
                    "strategy": strategy(f"Momentum continuation {index + 1}"),
                    "rationale": "The approved fingerprint and discovery history support momentum.",
                    "breakdown": [
                        "Confirm the approved trending regime",
                        "Wait for positive momentum",
                        "Exit when momentum reverses",
                    ],
                    "evidence_refs": [
                        (
                            "invented-reference"
                            if self.invalid_reference and index == 0
                            else "market-1"
                        ),
                        "history-1",
                    ],
                }
            )
        return {"hypotheses": hypotheses}


async def test_ai_generated_uses_researcher_and_returns_three_grounded_hypotheses() -> None:
    agents = FixtureStrategyAgents()
    hypotheses = await StrategyGenerationWorkflow(agents).generate_hypotheses(
        StrategyOrigin.AI_GENERATED,
        evidence_pack(),
        "Focus on liquid intraday markets",
    )

    assert agents.invoked == ["strategy_researcher"]
    assert len(hypotheses) == 3
    assert {item.specification.instruments[0] for item in hypotheses} == {"EUR/USD"}
    assert all(item.specification.origin == StrategyOrigin.AI_GENERATED for item in hypotheses)
    assert agents.payload["evidence_pack"]["selection_id"] == "selection-1"
    assert "holdout" not in str(agents.payload).lower()


async def test_ai_assisted_requires_description_and_uses_assistant() -> None:
    agents = FixtureStrategyAgents()
    workflow = StrategyGenerationWorkflow(agents)
    with pytest.raises(ValueError, match="description"):
        await workflow.generate_hypotheses(StrategyOrigin.AI_ASSISTED, evidence_pack(), "")

    await workflow.generate_hypotheses(
        StrategyOrigin.AI_ASSISTED,
        evidence_pack(),
        "I want a conservative momentum strategy around the London session",
    )
    assert agents.invoked == ["strategy_assistant"]


async def test_generation_rejects_uncited_or_invented_evidence() -> None:
    agents = FixtureStrategyAgents(invalid_reference=True)
    with pytest.raises(ValueError, match="unknown evidence reference"):
        await StrategyGenerationWorkflow(agents).generate_hypotheses(
            StrategyOrigin.AI_GENERATED, evidence_pack()
        )


async def test_generation_rejects_instrument_drift() -> None:
    agents = FixtureStrategyAgents()
    original = agents.invoke

    async def drift(logical_id: str, payload: dict, output_schema: dict) -> dict:
        response = deepcopy(await original(logical_id, payload, output_schema))
        response["hypotheses"][0]["strategy"]["instruments"] = ["GBP/USD"]
        return response

    agents.invoke = drift  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="approved instrument"):
        await StrategyGenerationWorkflow(agents).generate_hypotheses(
            StrategyOrigin.AI_GENERATED, evidence_pack()
        )


def test_only_ai_generated_and_ai_assisted_origins_exist() -> None:
    assert list(StrategyOrigin) == [StrategyOrigin.AI_GENERATED, StrategyOrigin.AI_ASSISTED]
