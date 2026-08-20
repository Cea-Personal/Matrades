from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from traderx.integrations.ports import SourceSemantics
from traderx.market_data.model import Instrument
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    SourceRole,
    build_source_evidence,
)
from traderx.market_research.liquidity import assess_asset_liquidity
from traderx.market_research.service import _research_inputs
from traderx.shared.types import MarketCategory


def test_forex_uses_broker_spread_and_activity_without_claiming_global_depth() -> None:
    result = assess_asset_liquidity(
        category=MarketCategory.FOREX,
        turnover=Decimal("100000"),
        spread_bps=Decimal("0.8"),
        tick_volume=Decimal("95000"),
    )
    assert "TICK_VOLUME_BROKER_PROXY" in result.evidence
    assert "GLOBAL_ORDER_BOOK" not in result.evidence


def test_commodity_requires_actual_venue_volume_and_open_interest() -> None:
    with pytest.raises(ValueError, match="open interest"):
        assess_asset_liquidity(
            category=MarketCategory.COMMODITY,
            turnover=Decimal("100000"),
            spread_bps=Decimal("1"),
            tick_volume=Decimal("999999"),
        )
    result = assess_asset_liquidity(
        category=MarketCategory.COMMODITY,
        turnover=Decimal("203415"),
        spread_bps=Decimal("1"),
        open_interest=Decimal("511223"),
        quoted_depth=Decimal("825"),
    )
    assert {"TRADED_VOLUME_ACTUAL", "OPEN_INTEREST_ACTUAL", "ORDER_BOOK_ACTUAL"} <= set(
        result.evidence
    )


def test_crypto_requires_actual_selected_venue_volume_and_order_book_depth() -> None:
    with pytest.raises(ValueError, match="quoted depth"):
        assess_asset_liquidity(
            category=MarketCategory.CRYPTO,
            turnover=Decimal("15423"),
            spread_bps=Decimal("0.9"),
        )
    result = assess_asset_liquidity(
        category=MarketCategory.CRYPTO,
        turnover=Decimal("15423"),
        spread_bps=Decimal("0.9"),
        quoted_depth=Decimal("24.3"),
    )
    assert {"TRADED_VOLUME_ACTUAL", "ORDER_BOOK_ACTUAL"} <= set(result.evidence)


def test_forex_runtime_keeps_mt5_activity_authoritative_when_venue_data_exists() -> None:
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    instrument = Instrument(
        symbol="EURUSD",
        display_name="Euro / US Dollar",
        category="FOREX",
        contract_spec={
            "closes": [
                str(Decimal("1.10") + Decimal(index) / Decimal("10000")) for index in range(61)
            ],
            "tick_volumes": ["1000"] * 61,
            "bid": "1.1060",
            "ask": "1.1061",
            "tick_size": "0.00001",
            "tick_value": "1",
            "contract_size": "100000",
            "volume_min": "0.01",
            "volume_step": "0.01",
            "trade_mode": 4,
        },
        trading_hours={},
    )
    instrument.id = uuid4()
    evidence = build_source_evidence(
        provider="CBOE_FX_SPOT",
        capability="LIQUIDITY",
        semantics=SourceSemantics.ACTUAL,
        source_role=SourceRole.SPECIALIST_PRIMARY,
        observed_at=now,
        received_at=now,
        evaluated_at=now,
        policy=FreshnessPolicy("CBOE_FX_SPOT", "LIQUIDITY", "fx-v1", timedelta(minutes=1)),
        canonical_instrument_id=str(instrument.id),
        entitlement_status="VERIFIED",
        complete=True,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
        measures={"TRADED_VOLUME": "9000000000", "ORDER_BOOK": "70000000"},
    )
    inputs, metrics, _quality = _research_inputs(instrument, source_evidence=(evidence,))
    assert inputs.turnover == Decimal("61000")
    assert "TICK_VOLUME_BROKER_PROXY" in metrics["liquidity_evidence"]
    assert "ORDER_BOOK_ACTUAL" not in metrics["liquidity_evidence"]
