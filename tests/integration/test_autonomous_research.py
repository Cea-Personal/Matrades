from __future__ import annotations

from datetime import UTC, datetime

from modules.research.models import MarketCategory, ResearchSnapshot
from modules.research.workflow import AutonomousResearchWorkflow


class FixtureProvider:
    async def gather(self, category: MarketCategory) -> list[ResearchSnapshot]:
        symbols = {
            MarketCategory.FOREX: ("EURUSD", "GBPUSD"),
            MarketCategory.METAL: ("XAUUSD", "XAGUSD"),
            MarketCategory.CRYPTO: ("BTC-USD", "ETH-USD"),
        }[category]
        return [
            ResearchSnapshot(
                instrument=symbol,
                category=category,
                closes=[100.0, 101.0 + index, 102.0 + index, 104.0 + index],
                bid=103.9 + index,
                ask=104.1 + index,
                volume=10_000.0 + index,
                observed_at=datetime.now(UTC),
                source="fixture",
                source_version="fixture-v1",
            )
            for index, symbol in enumerate(symbols)
        ]


class FixtureAgents:
    def __init__(self) -> None:
        self.invoked: list[str] = []

    async def invoke(self, logical_id: str, payload: dict, output_schema: dict) -> dict:
        self.invoked.append(logical_id)
        if logical_id == "critic":
            return {
                "decision": "PASS",
                "score_adjustments": [],
                "evidence": ["evidence is internally consistent"],
            }
        return {
            "decision": "PASS",
            "score_adjustments": {
                item["instrument"]: round(0.01 * (index + 1), 4)
                for index, item in enumerate(payload["candidates"])
            },
            "evidence": [f"{logical_id} reviewed normalized snapshots"],
            "uncertainties": [],
        }


async def test_cycle_discovers_candidates_and_invokes_required_research_roles() -> None:
    agents = FixtureAgents()
    result = await AutonomousResearchWorkflow(FixtureProvider(), agents).run(list(MarketCategory))

    assert result.state == "COMPLETED"
    assert {candidate.category for candidate in result.candidates} == set(MarketCategory)
    assert len(result.candidates) == 3
    assert all(candidate.fingerprint and candidate.evidence for candidate in result.candidates)
    assert {
        "forex_research",
        "metals_research",
        "crypto_research",
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
        "regime_analyst",
        "critic",
    }.issubset(agents.invoked)


async def test_missing_category_data_degrades_without_fabricating_a_pair() -> None:
    class MissingCrypto(FixtureProvider):
        async def gather(self, category: MarketCategory) -> list[ResearchSnapshot]:
            return [] if category == MarketCategory.CRYPTO else await super().gather(category)

    result = await AutonomousResearchWorkflow(MissingCrypto(), FixtureAgents()).run(
        list(MarketCategory)
    )

    assert result.state == "DEGRADED"
    assert MarketCategory.CRYPTO in result.missing_categories
    assert all(candidate.category != MarketCategory.CRYPTO for candidate in result.candidates)
