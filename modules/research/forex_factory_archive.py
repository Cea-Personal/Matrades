"""Period-keyed immutable archive for normalized Forex Factory events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from modules.analysis.models import EconomicEvent


@dataclass(frozen=True)
class ForexFactoryArchiveReference:
    period_key: str
    period_start: date
    period_end: date
    relative_path: str
    event_count: int
    skipped: bool
    message: str
    events: list[dict[str, Any]]


def _week_bounds(observed_at: datetime) -> tuple[date, date]:
    current = observed_at.astimezone(UTC).date()
    start = current - timedelta(days=current.weekday())
    return start, start + timedelta(days=6)


def period_bounds(
    events: list[EconomicEvent], *, observed_at: datetime, feed_url: str
) -> tuple[date, date]:
    """Determine the covered period, preserving the default feed's full week."""
    if "ff_calendar_thisweek" in feed_url:
        return _week_bounds(observed_at)
    dates = sorted(event.scheduled_at.astimezone(UTC).date() for event in events)
    if dates:
        return dates[0], dates[-1]
    current = observed_at.astimezone(UTC).date()
    return current, current


def period_key(period_start: date, period_end: date) -> str:
    if period_start.year == period_end.year and period_start.month == period_end.month:
        if period_start == period_end:
            return period_start.strftime("%d-%m-%Y")
        # Example: 24–29 August 2026 -> 2429-08-2026.
        return (
            f"{period_start.day:02d}{period_end.day:02d}-"
            f"{period_start.month:02d}-{period_start.year:04d}"
        )
    return f"{period_start:%Y%m%d}_to_{period_end:%Y%m%d}"


class ForexFactoryArchive:
    """Store one immutable JSON file for each covered calendar period."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _owner_root(self, owner_id: UUID) -> Path:
        directory = (self.root / str(owner_id) / "forex_factory").resolve()
        if self.root not in directory.parents:
            raise ValueError("unsafe Forex Factory archive path")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _events_payload(events: list[EconomicEvent]) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in events]

    def _reference(
        self,
        *,
        path: Path,
        payload: dict[str, Any],
        skipped: bool,
        message: str,
    ) -> ForexFactoryArchiveReference:
        period_start = date.fromisoformat(str(payload["period_start"]))
        period_end = date.fromisoformat(str(payload["period_end"]))
        return ForexFactoryArchiveReference(
            period_key=str(payload["period_key"]),
            period_start=period_start,
            period_end=period_end,
            relative_path=path.relative_to(self.root).as_posix(),
            event_count=int(payload.get("event_count", len(payload.get("events", [])))),
            skipped=skipped,
            message=message,
            events=list(payload.get("events", [])),
        )

    def find_covering_date(
        self, owner_id: UUID, observed_date: date
    ) -> ForexFactoryArchiveReference | None:
        directory = self._owner_root(owner_id)
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                start = date.fromisoformat(str(payload["period_start"]))
                end = date.fromisoformat(str(payload["period_end"]))
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
            if start <= observed_date <= end:
                return self._reference(
                    path=path,
                    payload=payload,
                    skipped=True,
                    message=(
                        f"Data already exists for period {payload['period_key']}; "
                        "scraper skipped."
                    ),
                )
        return None

    def save_period(
        self,
        *,
        owner_id: UUID,
        events: list[EconomicEvent],
        feed_url: str,
        scraped_at: datetime,
    ) -> ForexFactoryArchiveReference:
        if scraped_at.tzinfo is None or scraped_at.utcoffset() is None:
            raise ValueError("scraped_at must be timezone-aware")
        period_start, period_end = period_bounds(
            events, observed_at=scraped_at, feed_url=feed_url
        )
        key = period_key(period_start, period_end)
        directory = self._owner_root(owner_id)
        path = (directory / f"{key}.json").resolve()
        if directory not in path.parents:
            raise ValueError("unsafe Forex Factory archive path")
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return self._reference(
                path=path,
                payload=payload,
                skipped=True,
                message=f"Data already exists for period {key}; scraper skipped.",
            )
        payload = {
            "period_key": key,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "scraped_at": scraped_at.astimezone(UTC).isoformat(),
            "feed_url": feed_url,
            "event_count": len(events),
            "events": self._events_payload(events),
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return self._reference(
            path=path,
            payload=payload,
            skipped=False,
            message=f"Saved normalized data for period {key}.",
        )

    def list_periods(self, owner_id: UUID) -> list[ForexFactoryArchiveReference]:
        directory = self._owner_root(owner_id)
        results: list[ForexFactoryArchiveReference] = []
        for path in sorted(directory.glob("*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                results.append(
                    self._reference(
                        path=path,
                        payload=payload,
                        skipped=False,
                        message="Archived normalized Forex Factory data.",
                    )
                )
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return results
