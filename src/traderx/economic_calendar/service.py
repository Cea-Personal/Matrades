from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.market_data.model import CalendarCoverage, EconomicEvent, EconomicEventRevision


def sync_events(database: Session, *, events: list[dict[str, object]], source_url: str, now: datetime) -> list[EconomicEvent]:
    """Upsert only source-identified machine events while preserving revisions."""
    stored: list[EconomicEvent] = []
    for item in events:
        provider = str(item["source_provider"])
        external_id = str(item["external_id"])
        event = database.scalar(select(EconomicEvent).where(EconomicEvent.source_provider == provider, EconomicEvent.external_id == external_id))
        scheduled = _aware(item["scheduled_at"])
        source_origin = str(item.get("source_origin", "OFFICIAL_MACHINE"))
        payload = {"title": item["title"], "raw_hash": item.get("raw_hash")}
        impact = str(item.get("impact", "HIGH"))
        currency_or_region = str(item.get("currency_or_region", "USD"))
        affected_categories = list(item.get("affected_categories", ["FOREX", "COMMODITY", "CRYPTO"]))
        if event is None:
            event = EconomicEvent(
                event_at=scheduled, scheduled_at=scheduled, currency_or_region=currency_or_region, impact=impact,
                payload=payload, source_provider=provider, external_id=external_id,
                source_origin=source_origin, source_url=source_url,
                canonical_type=str(item["canonical_type"]), affected_categories=affected_categories,
                source_retrieved_at=now, stale_after=now + timedelta(days=8), status="UPCOMING",
                revision_number=1,
            )
            database.add(event)
        elif (
            event.scheduled_at != scheduled
            or event.payload != payload
            or event.impact != impact
            or event.source_origin != source_origin
        ):
            event.revision_number += 1
            event.event_at = scheduled
            event.scheduled_at = scheduled
            event.payload = payload
            event.impact = impact
            event.source_origin = source_origin
            event.source_retrieved_at = now
            database.add(EconomicEventRevision(
                economic_event_id=event.id, revision_number=event.revision_number, action="SOURCE_REVISION",
                reason="Official machine feed changed the event", source_url=source_url,
                payload=payload, changed_at=now,
            ))
        else:
            # A successful re-read refreshes provenance/freshness without
            # pretending the source changed an event.
            event.source_retrieved_at = now
            event.stale_after = now + timedelta(days=8)
        stored.append(event)
    database.flush()
    return stored


def create_owner_cited_event(
    database: Session, *, actor_id: UUID, provider: str, official_url: str, title: str,
    event_type: str, impact: str, scheduled_at: datetime, affected_categories: list[str], reason: str,
    now: datetime, supersedes_event_id: UUID | None = None,
) -> EconomicEvent:
    if provider not in {"FEDERAL_RESERVE", "EIA", "ECB", "BOE", "BOJ"}:
        raise ValueError("owner-cited source is not approved")
    if not official_url.startswith("https://") or len(reason.strip()) < 8:
        raise ValueError("owner-cited event requires an HTTPS official citation and reason")
    event = EconomicEvent(
        event_at=_aware(scheduled_at), scheduled_at=_aware(scheduled_at), currency_or_region="USD",
        impact=impact, payload={"title": title, "supersedes_event_id": str(supersedes_event_id) if supersedes_event_id else None},
        source_provider=provider, external_id=f"owner:{provider}:{scheduled_at.isoformat()}:{event_type}",
        source_origin="OWNER_CITED", source_url=official_url, canonical_type=event_type,
        affected_categories=affected_categories, source_retrieved_at=now,
        stale_after=now + timedelta(days=366), reviewed_by=actor_id, status="UPCOMING", revision_number=1,
    )
    database.add(event)
    database.flush()
    database.add(EconomicEventRevision(
        economic_event_id=event.id, revision_number=1, action="OWNER_CITED_CREATE", reason=reason,
        source_url=official_url, payload=event.payload, changed_by=actor_id, changed_at=now,
    ))
    coverage = database.scalar(
        select(CalendarCoverage).where(
            CalendarCoverage.source_provider == provider,
            CalendarCoverage.scope_key == "GLOBAL",
        )
    )
    if coverage is None:
        coverage = CalendarCoverage(
            source_provider=provider, scope_key="GLOBAL", status="VERIFIED",
            source_url=official_url, evidence={"origin": "OWNER_CITED", "last_event_id": str(event.id)},
        )
        database.add(coverage)
    coverage.status = "VERIFIED"
    coverage.last_success_at = now
    coverage.covered_through = _aware(scheduled_at) + timedelta(days=366)
    coverage.source_url = official_url
    coverage.evidence = {"origin": "OWNER_CITED", "last_event_id": str(event.id)}
    return event


def coverage_payload(database: Session) -> dict[str, object]:
    entries = list(database.scalars(select(CalendarCoverage).order_by(CalendarCoverage.source_provider, CalendarCoverage.scope_key)))
    return {"items": [{"provider": entry.source_provider, "scope": entry.scope_key, "status": entry.status, "source_url": entry.source_url, "covered_through": _iso(entry.covered_through), "last_success_at": _iso(entry.last_success_at), "evidence": entry.evidence} for entry in entries]}


def event_payload(event: EconomicEvent) -> dict[str, object]:
    coverage_state = (
        "EXPERIMENTAL_NOT_FOR_GATING"
        if event.source_origin == "SCRAPED_EXPERIMENTAL"
        else "VERIFIED"
        if event.stale_after and event.stale_after >= datetime.now(UTC)
        else "STALE"
    )
    return {"id": str(event.id), "source_origin": event.source_origin, "official_url": event.source_url, "title": event.payload.get("title", event.canonical_type), "event_type": event.canonical_type, "importance": event.impact, "scheduled_at": _iso(event.scheduled_at or event.event_at), "observed_at": _iso(event.released_at), "affected_currencies": [event.currency_or_region], "affected_categories": event.affected_categories, "actual": event.payload.get("actual"), "previous": event.payload.get("previous"), "consensus": None, "coverage_state": coverage_state, "source_retrieved_at": _iso(event.source_retrieved_at), "supersedes_event_id": event.payload.get("supersedes_event_id")}


def _aware(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("calendar time must be a datetime")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None
