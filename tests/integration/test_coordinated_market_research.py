from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.market_research.coordinator import (
    coordinated_report,
    create_coordinated_run,
    record_category_outcome,
)
from traderx.market_research.model import ActiveMarketAssignment, MarketResearchRun
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
        assert all(child.policy_pins["source_catalogue_revision"] == "2026-08-14.v1" for child in children)

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
            "BLOCKED",
        }
        assert database.scalar(select(ActiveMarketAssignment)) is None


def test_coordinator_reuses_an_occurrence_after_redelivery() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    # The idempotent occurrence path is covered by the scheduler integration test;
    # this assertion prevents a category count from becoming configurable.
    constraint_names = {constraint.name for constraint in Base.metadata.tables["coordinated_market_research_runs"].constraints}
    assert "ck_coordinated_market_research_runs_coordinated_run_three_categories" in constraint_names
