from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.integrations.ports import SourceSemantics
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    SourceRole,
    build_source_evidence,
)
from traderx.market_research.coordinator import create_coordinated_run
from traderx.market_research.model import ActiveMarketAssignment, MarketResearchRun
from traderx.market_research.source_selection import SourceAttempt, select_market_source
from traderx.shared.db import Base, load_model_metadata


def test_unique_three_category_run_pins_model_without_activating_a_market() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        account = TradingAccount(
            name="Demo", mode="DEMO", currency="USD", starting_balance=Decimal("10000")
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
            llm_pin={
                "provider_key": "OPENAI_RESPONSES",
                "exact_model_id": "gpt-5.6-terra",
                "catalogue_revision": "catalogue-v1",
                "adapter_revision": "adapter-v1",
                "prompt_template_version": "prompt-v1",
                "output_schema_version": "schema-v1",
                "inference_policy_version": "inference-v1",
            },
        )
        children = list(
            database.scalars(
                select(MarketResearchRun).where(
                    MarketResearchRun.coordinated_run_id == parent.id
                )
            )
        )
        assert {item.category for item in children} == {"COMMODITY", "FOREX", "CRYPTO"}
        assert all(item.policy_pins["llm"]["exact_model_id"] == "gpt-5.6-terra" for item in children)
        assert database.scalar(select(ActiveMarketAssignment)) is None


def test_fallback_preserves_original_freshness_and_assignment_boundary() -> None:
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    stale = build_source_evidence(
        provider="CME_GROUP",
        capability="OPEN_INTEREST",
        semantics=SourceSemantics.ACTUAL,
        source_role=SourceRole.FALLBACK_CACHED_EXTERNAL,
        observed_at=now - timedelta(days=2),
        received_at=now - timedelta(days=2),
        evaluated_at=now,
        policy=FreshnessPolicy("CME_GROUP", "OPEN_INTEREST", "unchanged-v1", timedelta(days=1)),
        entitlement_status="VERIFIED",
        complete=True,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
    )
    selection = select_market_source(
        specialist_attempts=[SourceAttempt("CME_GROUP", 3, False, "TIMEOUT")],
        specialist_evidence=[],
        mt5_evidence=[],
        cached_external_evidence=[stale],
        required_capabilities={"OPEN_INTEREST"},
    )
    assert selection.blocked is True
    assert selection.active_assignment_changed is False
    assert selection.reason_codes == ("NO_COMPLETE_FRESH_FALLBACK",)
