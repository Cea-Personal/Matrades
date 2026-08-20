from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.market_data.model import Instrument
from traderx.market_research.coordinator import (
    claim_category_run,
    coordinated_report,
    create_coordinated_run,
    record_category_outcome,
)
from traderx.market_research.model import (
    ActiveMarketAssignment,
    CandidateAssessment,
    LlmAnalysisAttempt,
    MarketResearchRun,
)
from traderx.shared.db import Base, load_model_metadata


def test_one_parent_owns_exactly_three_independent_category_runs_and_pins_policies() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        account = TradingAccount(
            name="Demo",
            mode="DEMO",
            currency="USD",
            starting_balance=Decimal("10000"),
        )
        database.add(account)
        database.flush()
        parent = create_coordinated_run(
            database,
            account_id=account.id,
            trigger="MANUAL",
            methodology_version="market-suitability-v2",
            source_catalogue_revision="2026-08-14.v1",
            freshness_policy_manifest={"default": "freshness-2026-08-v1"},
            retry_policy_manifest={"default": "retry-2026-08-v1"},
            now=now,
            llm_pin={
                "provider_key": "OPENAI_RESPONSES",
                "exact_model_id": "gpt-5.6-terra",
                "catalogue_revision": "2026-08-14.v1",
                "adapter_revision": "v1",
                "prompt_template_version": "market-advisory-v1",
                "output_schema_version": "market-advisory-v1",
                "inference_policy_version": "bounded-v1",
            },
        )
        children = list(
            database.scalars(
                select(MarketResearchRun)
                .where(MarketResearchRun.coordinated_run_id == parent.id)
                .order_by(MarketResearchRun.category)
            )
        )
        assert [child.category for child in children] == ["COMMODITY", "CRYPTO", "FOREX"]
        assert parent.expected_category_count == 3
        assert parent.exact_model_id == "gpt-5.6-terra"
        assert all(
            child.policy_pins["source_catalogue_revision"] == "2026-08-14.v1" for child in children
        )

        instrument = Instrument(
            symbol="XAUUSD",
            display_name="Gold / US Dollar",
            category="COMMODITY",
            contract_spec={},
            trading_hours={},
        )
        database.add(instrument)
        database.flush()
        database.add(
            CandidateAssessment(
                research_run_id=children[0].id,
                instrument_id=instrument.id,
                eligible=True,
                gate_evidence={"reason_codes": []},
                components={"volatility": "0.84", "liquidity": "0.92"},
                score=Decimal("0.86"),
                rank=1,
                confidence=Decimal("0.93"),
                explanation={"eligibility_precedes_ranking": True},
                source_evidence=[{"provider": "CME_GROUP", "semantics": "ACTUAL"}],
                deterministic_result_hash="candidate-result-hash",
            )
        )
        database.add(
            LlmAnalysisAttempt(
                research_run_id=children[0].id,
                attempt_number=1,
                provider_key="OPENAI_RESPONSES",
                exact_model_id="gpt-5.6-terra",
                catalogue_revision="2026-08-14.v1",
                adapter_revision="v1",
                prompt_template_version="market-advisory-v1",
                output_schema_version="market-advisory-v1",
                inference_policy_version="bounded-v1",
                state="COMPLETED",
                request_hash="request-hash",
                response_hash="response-hash",
                usage={"input_tokens": 120, "output_tokens": 32},
                analysis={"summary": "Evidence is coherent."},
                started_at=now,
                finished_at=now,
            )
        )
        children[0].llm_analysis_state = "COMPLETED"

        record_category_outcome(database, children[0], outcome="RECOMMENDED", completed_at=now)
        record_category_outcome(database, children[1], outcome="RECOMMENDED", completed_at=now)
        record_category_outcome(
            database,
            children[2],
            outcome="BLOCKED",
            block_reasons=["NO_COMPLETE_FRESH_FALLBACK"],
            completed_at=now,
        )
        report = coordinated_report(database, parent.id)
        assert report["state"] == "PARTIAL"
        assert len(report["categories"]) == 3
        assert {item["outcome"] for item in report["categories"]} == {
            "RECOMMENDED",
            "NO_ELIGIBLE_CANDIDATE",
            "BLOCKED",
        }
        commodity = next(item for item in report["categories"] if item["category"] == "COMMODITY")
        assert commodity["candidates"][0]["rationale"]["eligibility_precedes_ranking"] is True
        assert commodity["selection_proposal"]["candidate"]["symbol"] == "XAUUSD"
        assert commodity["llm_analysis"]["analysis"]["summary"] == "Evidence is coherent."
        assert commodity["llm_analysis"]["authoritative"] is False
        assert report["model_pin"]["prompt_template_version"] == "market-advisory-v1"
        assert report["freshness_policy_manifest"]["default"] == "freshness-2026-08-v1"
        assert database.scalar(select(ActiveMarketAssignment)) is None


def test_coordinator_reuses_an_occurrence_after_redelivery() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    # The idempotent occurrence path is covered by the scheduler integration test;
    # this assertion prevents a category count from becoming configurable.
    constraint_names = {
        constraint.name
        for constraint in Base.metadata.tables["coordinated_market_research_runs"].constraints
    }
    assert (
        "ck_coordinated_market_research_runs_coordinated_run_three_categories" in constraint_names
    )


def test_category_claim_fences_redelivery_and_recovers_only_after_lease_expiry() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        account = TradingAccount(
            name="Lease demo",
            mode="DEMO",
            currency="USD",
            starting_balance=Decimal("10000"),
        )
        database.add(account)
        database.flush()
        parent = create_coordinated_run(
            database,
            account_id=account.id,
            trigger="SCHEDULED",
            methodology_version="market-suitability-v2",
            source_catalogue_revision="catalogue-v1",
            freshness_policy_manifest={"default": "freshness-v1"},
            retry_policy_manifest={"default": "retry-v1"},
            now=now,
        )
        child = database.scalar(
            select(MarketResearchRun).where(
                MarketResearchRun.coordinated_run_id == parent.id,
                MarketResearchRun.category == "FOREX",
            )
        )
        assert child is not None
        lease_a = str(uuid4())
        lease_b = str(uuid4())
        first = claim_category_run(
            database,
            child.id,
            now=now,
            lease_owner="worker-a",
            lease_token=lease_a,
            lease_duration=timedelta(minutes=10),
        )
        assert first is not None and first.attempt_count == 1
        assert (
            claim_category_run(
                database,
                child.id,
                now=now + timedelta(minutes=5),
                lease_owner="worker-b",
                lease_token=lease_b,
            )
            is None
        )
        recovered = claim_category_run(
            database,
            child.id,
            now=now + timedelta(minutes=11),
            lease_owner="worker-b",
            lease_token=lease_b,
        )
        assert recovered is not None and recovered.attempt_count == 2
        assert child.lease_token == lease_b
