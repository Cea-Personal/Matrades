"""Economic-calendar adapters.

Official production sources use documented machine feeds only.  The optional
ForexFactory adapter at the bottom is deliberately marked development-only and
is kept separate so it cannot be mistaken for an official source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class CalendarSource:
    provider: str
    schedule_url: str | None
    values_url: str | None
    origin: str


BLS = CalendarSource("BLS", "https://www.bls.gov/schedule/news_release/bls.ics", None, "OFFICIAL_MACHINE")
BEA = CalendarSource("BEA", "https://www.bea.gov/news/schedule/icalendar", None, "OFFICIAL_MACHINE")
EIA = CalendarSource("EIA", None, "https://api.eia.gov/v2/", "OWNER_CITED")
FEDERAL_RESERVE = CalendarSource(
    "FEDERAL_RESERVE", None, None, "OWNER_CITED"
)


def parse_ics_schedule(*, provider: str, content: bytes, retrieved_at: datetime) -> list[dict[str, object]]:
    """Normalize an official ICS feed without fetching or interpreting HTML."""

    result: list[dict[str, object]] = []
    source_hash = sha256(content).hexdigest()
    for component in _vevents(content.decode("utf-8", errors="strict")):
        start = _ics_datetime(component.get("DTSTART"))
        if start is None:
            continue
        title = component.get("SUMMARY", "").strip()
        if not title:
            continue
        event_type = canonical_event_type(title)
        if event_type is None:
            continue
        uid = component.get("UID") or f"{provider}:{start.isoformat()}:{title}"
        result.append(
            {
                "external_id": uid,
                "title": title,
                "canonical_type": event_type,
                "scheduled_at": _utc(start),
                "source_provider": provider,
                "source_origin": "OFFICIAL_MACHINE",
                "source_retrieved_at": _utc(retrieved_at),
                "raw_hash": source_hash,
            }
        )
    return result


def canonical_event_type(title: str) -> str | None:
    normalized = title.upper()
    mapping = {
        "CONSUMER PRICE": "US_CPI",
        "EMPLOYMENT SITUATION": "US_NFP",
        "PAYROLL": "US_NFP",
        "PRODUCER PRICE": "US_PPI",
        "GROSS DOMESTIC PRODUCT": "US_GDP",
        "PERSONAL INCOME": "US_PCE",
        "PERSONAL CONSUMPTION": "US_PCE",
    }
    return next((event for phrase, event in mapping.items() if phrase in normalized), None)


def owner_cited_source(provider: str) -> CalendarSource:
    if provider == "FEDERAL_RESERVE":
        return CalendarSource(provider, "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", None, "OWNER_CITED")
    if provider == "EIA":
        return CalendarSource(provider, "https://www.eia.gov/petroleum/supply/weekly/schedule.php", EIA.values_url, "OWNER_CITED")
    raise ValueError("only documented owner-cited calendar sources are permitted")


FOREX_FACTORY_EXPERIMENTAL_URL = "https://www.forexfactory.com/calendar"


def parse_forex_factory_experimental(
    *, payload: object, retrieved_at: datetime
) -> list[dict[str, object]]:
    """Normalize a conservative subset of the optional scraper's JSON output.

    The third-party API is not an authority and its shape is not a contract
    TraderX owns.  Rows without an unambiguous date/time or title are dropped
    rather than inventing a schedule.  Every accepted row is explicitly tagged
    ``SCRAPED_EXPERIMENTAL``.
    """

    rows = _scraper_rows(payload)
    events: list[dict[str, object]] = []
    raw_hash = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    for row in rows:
        title = _first_string(row, "title", "event", "name", "event_name")
        scheduled_at = _scraper_datetime(row)
        if not title or scheduled_at is None:
            continue
        impact_text = (_first_string(row, "impact", "importance", "priority") or "").upper()
        impact = "HIGH" if "HIGH" in impact_text else "MEDIUM" if "MEDIUM" in impact_text else "LOW"
        currency = _first_string(row, "currency", "country", "region") or "UNKNOWN"
        external = _first_string(row, "id", "event_id")
        external_id = external or sha256(
            f"{scheduled_at.isoformat()}|{currency}|{title}".encode()
        ).hexdigest()
        events.append(
            {
                "external_id": external_id,
                "title": title,
                "canonical_type": canonical_event_type(title) or "OTHER",
                "scheduled_at": scheduled_at,
                "source_provider": "FOREX_FACTORY_SCRAPER",
                "source_origin": "SCRAPED_EXPERIMENTAL",
                "source_retrieved_at": _utc(retrieved_at),
                "raw_hash": raw_hash,
                "impact": impact,
                "currency_or_region": currency,
                "affected_categories": ["FOREX", "COMMODITY", "CRYPTO"],
            }
        )
    return events


def _scraper_rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = payload.get("results") or payload.get("data") or payload.get("events") or []
    else:
        return []
    return [row for row in candidates if isinstance(row, dict)]


def _first_string(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _scraper_datetime(row: dict[str, Any]) -> datetime | None:
    value = _first_string(row, "scheduled_at", "datetime", "date_time", "timestamp")
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _utc(parsed)
        except ValueError:
            pass
    date_text = _first_string(row, "date", "event_date")
    time_text = _first_string(row, "time", "event_time")
    if not date_text or not time_text or time_text.lower() in {"all day", "tentative", "day"}:
        return None
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        for time_format in ("%H:%M", "%H:%M:%S", "%I:%M%p", "%I:%M %p"):
            try:
                parsed = datetime.strptime(f"{date_text} {time_text.upper()}", f"{date_format} {time_format}")
                return parsed.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
            except ValueError:
                continue
    return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _vevents(content: str) -> list[dict[str, str]]:
    """Small strict parser for the DTSTART/SUMMARY/UID fields we accept from ICS."""
    unfolded: list[str] = []
    for line in content.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in unfolded:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            field, value = line.split(":", 1)
            current[field.split(";", 1)[0]] = value
    return events


def _ics_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
