from datetime import UTC, datetime
from uuid import uuid4

from apps.worker.app.tasks.research import _typed_instrument_data
from modules.research.models import TypedResearchRun, TypedResearchSnapshot
from modules.research.workflow import AutonomousResearchWorkflow
from packages.shared.domain_types import AssetClass, InstrumentType, LaneStatus, ResearchLaneKey
from packages.shared.persistence import validate_executable_reference
from tests.fixtures.instrument_matrix import listing, specification


async def test_no_trade_persists_complete_analyst_decision_trace() -> None:
    lane = ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.CFD)
    market = listing(AssetClass.FOREX, InstrumentType.CFD)
    snapshot = TypedResearchSnapshot(
        listing=market,
        specification=specification(market.id),
        closes=[1.08, 1.09, 1.10],
        bid=1.0999,
        ask=1.1001,
        volume=82,
        observed_at=datetime.now(UTC),
        source="fixture-provider",
        source_version="fixture-v1",
        source_cut_id="cut-eurusd-001",
    )

    class Provider:
        async def gather_lane(self, requested_lane: ResearchLaneKey) -> list[TypedResearchSnapshot]:
            assert requested_lane == lane
            return [snapshot]

    class Agents:
        async def invoke(self, logical_id: str, payload: dict, output_schema: dict) -> dict:
            assert logical_id == "technical_analyst"
            assert payload["source_cut_refs"] == ["cut-eurusd-001"]
            assert payload["review_contract"]["stage"] == "MARKET_CANDIDATE_RESEARCH"
            assert "non-executable underlying-market proxy is expected" in payload[
                "review_contract"
            ]["cfd_proxy_policy"]
            return {
                "decision": "NO_ACTION — higher-timeframe confirmation is missing",
                "score_adjustments": [{"instrument": market.symbol, "adjustment": -3.5}],
                "evidence": ["Trend confirmation is missing on the higher timeframe."],
            }

    run = TypedResearchRun(
        owner_id=uuid4(),
        account_id=uuid4(),
        matrix_version=1,
        requested_lanes=[lane],
        created_at=datetime.now(UTC),
    )

    completed = await AutonomousResearchWorkflow(Provider(), Agents()).run_matrix(run)
    result = completed.lane_results[0]

    assert result.status is LaneStatus.NO_TRADE
    assert result.reason_code == "ANALYST_REASSESS"
    assert result.observed_candidates == [market.symbol]
    assert result.source_cut_refs == ["cut-eurusd-001"]
    assert result.exclusions == ["technical_analyst"]
    assert result.agent_reviews[0].logical_id == "technical_analyst"
    assert result.agent_reviews[0].status == "REASSESS"
    assert (
        result.agent_reviews[0].raw_decision
        == "NO_ACTION — higher-timeframe confirmation is missing"
    )
    assert result.agent_reviews[0].evidence == [
        "Trend confirmation is missing on the higher timeframe."
    ]
    assert result.agent_reviews[0].score_adjustments == {market.symbol: -3.5}


async def test_non_executable_cfd_proxy_can_advance_market_research() -> None:
    lane = ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.CFD)
    market = listing(AssetClass.FOREX, InstrumentType.CFD).model_copy(
        update={"executable": False}
    )
    snapshot = TypedResearchSnapshot(
        listing=market,
        specification=specification(market.id),
        closes=[1.08, 1.09, 1.10],
        bid=1.0999,
        ask=1.1001,
        volume=82,
        observed_at=datetime.now(UTC),
        source="fixture-provider",
        source_version="fixture-v1",
        source_cut_id="cut-eurusd-002",
    )

    class Provider:
        async def gather_lane(self, requested_lane: ResearchLaneKey) -> list[TypedResearchSnapshot]:
            return [snapshot]

    class Agents:
        async def invoke(self, logical_id: str, payload: dict, output_schema: dict) -> dict:
            contract = payload["review_contract"]
            assert contract["stage"] == "MARKET_CANDIDATE_RESEARCH"
            assert "MT5 validation remains mandatory later" in contract["execution_boundary"]
            return {
                "decision": "PASS",
                "score_adjustments": [],
                "evidence": [f"{logical_id} accepted the fresh research proxy"],
            }

    run = TypedResearchRun(
        owner_id=uuid4(),
        account_id=uuid4(),
        matrix_version=1,
        requested_lanes=[lane],
        created_at=datetime.now(UTC),
    )

    completed = await AutonomousResearchWorkflow(Provider(), Agents()).run_matrix(run)
    result = completed.lane_results[0]

    assert result.status is LaneStatus.READY
    assert result.candidate is not None
    assert result.candidate.listing.executable is False
    assert [review.logical_id for review in result.agent_reviews] == [
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
        "regime_analyst",
        "forex_research",
        "critic",
    ]
    instrument_data = _typed_instrument_data(run.account_id, result.candidate, result)
    validate_executable_reference(instrument_data)
    assert instrument_data["venue_instrument_id"] == str(market.id)
    assert instrument_data["quantity_unit"] == snapshot.specification.quantity_unit.value
