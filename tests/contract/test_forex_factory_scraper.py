from __future__ import annotations

from adapters.news.forex_factory import parse_forex_factory_payload


def test_forex_factory_feed_is_normalized_to_economic_events() -> None:
    events = parse_forex_factory_payload(
        [
            {
                "title": "Non-Farm Employment Change",
                "country": "USD",
                "date": "2026-08-25T12:30:00-04:00",
                "impact": "High",
                "forecast": "180K",
                "previous": "147K",
            }
        ],
        source="FOREX_FACTORY",
    )

    assert len(events) == 1
    assert events[0].name == "Non-Farm Employment Change"
    assert events[0].currency == "USD"
    assert events[0].impact == "HIGH"
    assert events[0].source == "FOREX_FACTORY"


def test_forex_factory_feed_skips_malformed_rows_without_fabricating_events() -> None:
    assert parse_forex_factory_payload([{"country": "USD"}], source="FOREX_FACTORY") == []
