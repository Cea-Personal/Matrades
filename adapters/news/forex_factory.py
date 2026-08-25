"""Small, provider-owned Forex Factory calendar feed adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from modules.analysis.models import EconomicEvent

DEFAULT_FOREX_FACTORY_FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _scheduled_at(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_forex_factory_payload(
    payload: Any, *, source: str = "FOREX_FACTORY"
) -> list[EconomicEvent]:
    rows = payload.get("events", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    events: list[EconomicEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("title") or row.get("event") or row.get("name")
        country = row.get("country") or row.get("currency")
        timestamp = row.get("date") or row.get("datetime") or row.get("scheduled_at")
        if not name or not country or not timestamp:
            continue
        try:
            events.append(
                EconomicEvent(
                    name=str(name),
                    currency=str(country).upper(),
                    impact=str(row.get("impact") or "UNKNOWN").upper(),
                    scheduled_at=_scheduled_at(timestamp),
                    source=source,
                )
            )
        except (TypeError, ValueError):
            continue
    return events


async def fetch_forex_factory_events(
    feed_url: str = DEFAULT_FOREX_FACTORY_FEED,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[EconomicEvent]:
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=10, headers={"User-Agent": "Matrades/1"})
    try:
        response = await http.get(feed_url)
        response.raise_for_status()
        return parse_forex_factory_payload(response.json())
    finally:
        if owns_client:
            await http.aclose()
