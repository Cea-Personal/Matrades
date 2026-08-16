from decimal import Decimal

import pytest

from traderx.market_research.liquidity import assess_asset_liquidity
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
