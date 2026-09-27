from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from modules.research.features import IneligibleResearchEvidence, typed_fingerprint
from modules.research.models import TypedResearchRun, TypedResearchSnapshot
from modules.research.workflow import AutonomousResearchWorkflow
from packages.shared.domain_types import AssetClass, InstrumentType, LaneStatus, ResearchLaneKey
from tests.fixtures.instrument_matrix import listing, specification


def snapshot(**changes) -> TypedResearchSnapshot:
    market = listing(AssetClass.FOREX, InstrumentType.CFD)
    now = datetime.now(UTC)
    values = dict(
        listing=market,
        specification=specification(market.id),
        closes=[1 + i * 0.001 for i in range(100)],
        bid=1.0989,
        ask=1.0991,
        observed_at=now,
        quote_observed_at=now,
        candle_observed_at=now,
        spread_verified=True,
        source="fixture",
        source_version="v1",
        source_cut_id="cut",
    )
    values.update(changes)
    return TypedResearchSnapshot(**values)


def test_volume_does_not_determine_ranking_and_regime_is_measured():
    first, score, evidence = typed_fingerprint(snapshot(volume=0))
    _, other, _ = typed_fingerprint(snapshot(volume=10_000_000))
    assert score == other
    assert first.regime == "TRENDING"
    assert first.trend_score > 0
    assert first.criteria["timeframe_alignment"] == 1
    assert evidence


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"closes": [1, 2, 3]}, "INSUFFICIENT_HISTORY"),
        ({"closes": [1.0] * 30}, "NO_PRICE_MOVEMENT"),
        ({"closes": [float("nan")] * 30}, "INVALID_PRICE_HISTORY"),
        ({"ask": 1.0}, "CROSSED_QUOTE"),
        ({"ask": 1.2}, "EXCESSIVE_SPREAD"),
        ({"quote_observed_at": datetime.now(UTC) - timedelta(days=7)}, "STALE_QUOTE"),
        ({"candle_observed_at": datetime.now(UTC) - timedelta(days=7)}, "STALE_CANDLES"),
    ],
)
def test_bad_evidence_is_excluded(changes, reason):
    with pytest.raises(IneligibleResearchEvidence, match=reason):
        typed_fingerprint(snapshot(**changes))


def test_missing_spread_is_neutral_not_free():
    result, _, _ = typed_fingerprint(snapshot(spread_verified=False, bid=1.099, ask=1.099))
    assert result.criteria["trading_cost"] == 0.5
    assert result.criteria["spread_to_movement"] is None
    assert any("spread unavailable" in value for value in result.limitations)


@pytest.mark.parametrize("all_agents,expected", [(False, 10), (True, 15)])
async def test_critic_adjustments_are_applied_and_total_ai_adjustment_is_bounded(
    all_agents, expected
):
    value = snapshot()
    _, base, _ = typed_fingerprint(value)
    lane = ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.CFD)

    class Provider:
        async def gather_lane(self, lane):
            return [value]

    class Agents:
        async def invoke(self, role, payload, schema):
            assert payload["measured_criteria"]
            return {
                "decision": "PASS",
                "evidence": [],
                "score_adjustments": [
                    {
                        "instrument": value.listing.symbol,
                        "adjustment": -10 if all_agents or role == "critic" else 0,
                    }
                ],
            }

    run = TypedResearchRun(
        owner_id=uuid4(),
        account_id=uuid4(),
        matrix_version=1,
        requested_lanes=[lane],
        created_at=datetime.now(UTC),
    )
    result = await AutonomousResearchWorkflow(Provider(), Agents()).run_matrix(run)
    assert result.lane_results[0].candidate.score == round(base - expected, 4)


async def test_lane_winners_prefer_distinct_underlyings():
    underlying_a, underlying_b = uuid4(), uuid4()
    lanes = [
        ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=kind)
        for kind in (InstrumentType.CFD, InstrumentType.SPOT)
    ]

    class Provider:
        async def gather_lane(self, lane):
            results = []
            for symbol, underlying in [("EUR/USD", underlying_a), ("GBP/USD", underlying_b)]:
                value = snapshot()
                market = value.listing.model_copy(
                    update={
                        "id": uuid4(),
                        "symbol": symbol,
                        "underlying_id": underlying,
                        "instrument_type": lane.instrument_type,
                    }
                )
                results.append(
                    value.model_copy(
                        update={
                            "listing": market,
                            "specification": specification(market.id),
                        }
                    )
                )
            return results

    class Agents:
        async def invoke(self, *args):
            return {"decision": "PASS", "score_adjustments": [], "evidence": []}

    run = TypedResearchRun(
        owner_id=uuid4(),
        account_id=uuid4(),
        matrix_version=1,
        requested_lanes=lanes,
        created_at=datetime.now(UTC),
    )
    result = await AutonomousResearchWorkflow(Provider(), Agents()).run_matrix(run)
    assert {item.candidate.listing.symbol for item in result.lane_results} == {"EUR/USD", "GBP/USD"}
    assert all(item.candidate.rank == 1 for item in result.lane_results)
    assert any(
        item.candidate.fingerprint.criteria["diversification_penalty"] > 0
        for item in result.lane_results
    )


async def test_ineligible_candidates_never_reach_agents():
    class Provider:
        async def gather_lane(self, lane):
            return [snapshot(closes=[1, 2, 3])]

    class Agents:
        async def invoke(self, *args):
            pytest.fail("Ineligible evidence must not reach an agent")

    lane = ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.CFD)
    run = TypedResearchRun(
        owner_id=uuid4(),
        account_id=uuid4(),
        matrix_version=1,
        requested_lanes=[lane],
        created_at=datetime.now(UTC),
    )
    result = await AutonomousResearchWorkflow(Provider(), Agents()).run_matrix(run)
    assert result.lane_results[0].status == LaneStatus.NO_TRADE
    assert "INSUFFICIENT_HISTORY" in result.lane_results[0].exclusions[0]
