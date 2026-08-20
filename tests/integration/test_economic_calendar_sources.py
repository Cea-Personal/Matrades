from datetime import UTC, datetime

from traderx.economic_calendar.providers import canonical_event_type, parse_ics_schedule


def test_official_ics_is_parsed_without_html_scraping() -> None:
    events = parse_ics_schedule(provider="BLS", content=b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:cpi-1\r\nDTSTART:20260911T123000Z\r\nSUMMARY:Consumer Price Index\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n", retrieved_at=datetime(2026, 8, 20, tzinfo=UTC))
    assert events[0]["canonical_type"] == "US_CPI"
    assert events[0]["source_origin"] == "OFFICIAL_MACHINE"
    assert canonical_event_type("unrelated release") is None
