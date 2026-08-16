from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

REFERENCE_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

MT5_INSTRUMENTS = {
    "COMMODITY": {
        "symbol": "XAUUSD",
        "category": "COMMODITY",
        "contract_size": "100",
        "tick_size": "0.01",
        "tick_value": "1",
        "volume_min": "0.01",
        "volume_step": "0.01",
        "bid": "2450.10",
        "ask": "2450.30",
        "tick_volume": "125000",
        "real_volume": None,
        "depth_status": "UNAVAILABLE",
    },
    "FOREX": {
        "symbol": "EURUSD",
        "category": "FOREX",
        "contract_size": "100000",
        "tick_size": "0.00001",
        "tick_value": "1",
        "volume_min": "0.01",
        "volume_step": "0.01",
        "bid": "1.10100",
        "ask": "1.10108",
        "tick_volume": "95000",
        "depth_status": "UNAVAILABLE",
    },
    "CRYPTO": {
        "symbol": "BTCUSD",
        "category": "CRYPTO",
        "contract_size": "1",
        "tick_size": "0.01",
        "tick_value": "0.01",
        "volume_min": "0.01",
        "volume_step": "0.01",
        "bid": "118000",
        "ask": "118010",
        "tick_volume": "50000",
        "depth_status": "AVAILABLE",
        "book": {"bids": [["118000", "4.5"]], "asks": [["118010", "4.2"]]},
    },
}

CME_FIXTURE = {
    "provider": "CME_GROUP",
    "venue": "COMEX",
    "provider_symbol": "GC",
    "observed_at": REFERENCE_NOW.isoformat(),
    "traded_volume": "203415",
    "open_interest": "511223",
    "top_of_book": {"bid": "2450.1", "ask": "2450.2"},
    "depth": {"bid_quantity": "420", "ask_quantity": "405"},
}

CBOE_FIXTURE = {
    "provider": "CBOE_FX_SPOT",
    "venue": "CBOE_FX_SPOT",
    "provider_symbol": "EUR/USD",
    "observed_at": REFERENCE_NOW.isoformat(),
    "traded_volume": "7750000000",
    "top_of_book": {"bid": "1.10101", "ask": "1.10107"},
    "depth": {"bid_quantity": "8000000", "ask_quantity": "7600000"},
}

COINBASE_FIXTURE = {
    "provider": "COINBASE_EXCHANGE",
    "venue": "COINBASE_EXCHANGE",
    "provider_symbol": "BTC-USD",
    "observed_at": REFERENCE_NOW.isoformat(),
    "traded_volume": "15423.25",
    "book_sequence": 9001,
    "bids": [["118000", "12.5"]],
    "asks": [["118010", "11.8"]],
}

LLM_ADVISORY_FIXTURE = {
    "summary": "Eligible candidates show usable volatility with category-specific liquidity.",
    "anomalies": [],
    "cautions": ["Confirm source freshness before activation."],
    "method_proposals": [],
}

PROVIDER_OUTAGES = {
    "rate_limit": {"status": 429, "retry_after_seconds": 5},
    "entitlement": {"status": 403, "reason": "ENTITLEMENT_REQUIRED"},
    "timeout": {"reason": "TIMEOUT"},
    "invalid_llm": {"summary": 7, "unexpected": "field"},
}

STALE_CACHE_OBSERVED_AT = REFERENCE_NOW - timedelta(days=3)
FRESH_CACHE_OBSERVED_AT = REFERENCE_NOW - timedelta(minutes=5)
CONFLICT_VALUES = (Decimal("100"), Decimal("135"))

# The New York anchor crosses both DST offsets and is intentionally deterministic.
DST_SCHEDULE = {
    "timezone": "America/New_York",
    "anchor_local": "2026-03-07T09:00:00-05:00",
    "interval_seconds": 86400,
}
