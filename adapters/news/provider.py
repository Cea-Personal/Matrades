from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from adapters.news.forex_factory import fetch_forex_factory_events
from packages.shared.domain_types import AwareDateTime


class NewsItem(BaseModel):
    headline: str
    source: str
    published_at: AwareDateTime
    instruments: list[str] = []


def normalize_news(payload: dict, source: str) -> NewsItem:
    return NewsItem(
        headline=str(payload["headline"]),
        source=source,
        published_at=datetime.fromisoformat(str(payload["published_at"])),
        instruments=list(payload.get("instruments", [])),
    )


__all__ = ["NewsItem", "normalize_news", "fetch_forex_factory_events"]
