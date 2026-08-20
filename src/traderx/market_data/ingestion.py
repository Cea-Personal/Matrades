from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.integrations.ports import ProviderObservation
from traderx.market_data.model import DataSetManifest, MarketObservation
from traderx.shared.types import as_decimal

if TYPE_CHECKING:
    from traderx.market_data.source_evidence import ConflictState


@dataclass(frozen=True, slots=True)
class CanonicalBar:
    observed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    spread: Decimal | None
    revision: int = 1


@dataclass(frozen=True, slots=True)
class ProviderBatch:
    """An immutable copy of the provider response retained before normalization."""

    provider: str
    provider_symbol: str
    retrieved_at: datetime
    payload: bytes
    cursor: str | None = None
    venue: str | None = None
    capability: str = "CANDLES"
    semantics: str = "UNAVAILABLE"
    source_role: str = "SPECIALIST_PRIMARY"
    catalogue_revision: str | None = None
    adapter_revision: str | None = None
    mapping_revision: str | None = None
    freshness_policy_version: str | None = None
    retry_policy_version: str | None = None
    entitlement_status: str = "UNVERIFIED"
    source_observed_at: datetime | None = None
    raw_reference: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ParquetArtifact:
    """Canonical normalized data plus the evidence needed for a dataset manifest."""

    content: bytes
    content_hash: str
    source_hash: str
    row_count: int
    coverage_start: datetime | None
    coverage_end: datetime | None
    cursor: str | None
    source_manifest: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedProviderBatch:
    """Database-backed immutable provider batch and its normalized observations."""

    manifest: DataSetManifest
    observations: tuple[MarketObservation, ...]


def persist_provider_observations(
    database: Session,
    *,
    instrument_id: UUID,
    integration_id: UUID,
    batch: ProviderBatch,
    observations: Sequence[ProviderObservation],
    normalized_value: Decimal | None,
    quality: str,
    conflict_state: ConflictState,
    complete: bool,
    fallback_reason: str | None = None,
) -> PersistedProviderBatch:
    """Persist native payloads before a research run consumes their normalized value.

    The content hash makes at-least-once collection idempotent. Provider payloads are
    retained in ``MarketObservation.measures``; metric-only observations deliberately
    keep OHLC fields null rather than manufacturing financial values.
    """

    if batch.provider == "TWELVE_DATA" and batch.capability not in {
        "QUOTES", "CANDLES", "TRADED_VOLUME"
    }:
        raise ValueError("Twelve Data cannot supply this market-data capability")
    if batch.provider == "TWELVE_DATA" and batch.semantics != "AGGREGATED_PROXY":
        raise ValueError("Twelve Data observations must retain AGGREGATED_PROXY semantics")
    native_rows = [_provider_observation_document(item) for item in observations]
    payload = json.dumps(
        {
            "integration_id": str(integration_id),
            "instrument_id": str(instrument_id),
            "provider": batch.provider,
            "provider_symbol": batch.provider_symbol,
            "capability": batch.capability,
            "retrieved_at": _utc_instant(batch.retrieved_at).isoformat(),
            "observations": native_rows,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    content_hash = hashlib.sha256(payload).hexdigest()
    existing = database.scalar(
        select(DataSetManifest).where(DataSetManifest.content_hash == content_hash)
    )
    if existing is not None:
        rows = tuple(
            database.scalars(
                select(MarketObservation)
                .where(MarketObservation.dataset_manifest_id == existing.id)
                .order_by(MarketObservation.observed_at, MarketObservation.id)
            )
        )
        return PersistedProviderBatch(existing, rows)

    observed_times = [
        _utc_instant(item.observed_at) for item in observations if item.observed_at is not None
    ]
    received_times = [_utc_instant(item.received_at) for item in observations]
    manifest = DataSetManifest(
        provider=batch.provider,
        integration_id=integration_id,
        provider_symbol=batch.provider_symbol,
        venue=batch.venue,
        capability=batch.capability,
        semantics=batch.semantics,
        source_role=batch.source_role,
        catalogue_revision=batch.catalogue_revision,
        adapter_revision=batch.adapter_revision,
        mapping_revision=batch.mapping_revision,
        freshness_policy_version=batch.freshness_policy_version,
        retry_policy_version=batch.retry_policy_version,
        entitlement_status=batch.entitlement_status,
        purpose="MARKET_SELECTION",
        parquet_uri=f"postgresql://market-observations/{content_hash}",
        content_hash=content_hash,
        coverage={
            "row_count": len(observations),
            "start": min(observed_times).isoformat() if observed_times else None,
            "end": max(observed_times).isoformat() if observed_times else None,
        },
        source_observed_at=max(observed_times) if observed_times else None,
        received_at=max(received_times) if received_times else _utc_instant(batch.retrieved_at),
        complete=complete,
        quality=quality,
        conflict_state=conflict_state.value,
        fallback_reason=fallback_reason,
        raw_reference=batch.raw_reference or f"sha256:{content_hash}",
        created_at=_utc_instant(batch.retrieved_at),
    )
    database.add(manifest)
    database.flush()

    persisted: list[MarketObservation] = []
    seen_observation_keys: set[tuple[datetime, int]] = set()
    for item in observations:
        if item.observed_at is None:
            continue
        revision = _positive_revision(item.revision)
        observation_key = (_utc_instant(item.observed_at), revision)
        if observation_key in seen_observation_keys:
            # Contradictory duplicate identities are retained in the native batch
            # below and quarantined by the manifest; never manufacture two rows
            # that violate the canonical observation identity.
            continue
        seen_observation_keys.add(observation_key)
        row = MarketObservation(
            instrument_id=instrument_id,
            integration_id=integration_id,
            dataset_manifest_id=manifest.id,
            provider=item.provider,
            provider_symbol=item.provider_symbol,
            venue=item.venue,
            capability=str(item.capability),
            semantics=item.semantics.value,
            source_role=batch.source_role,
            mapping_revision=batch.mapping_revision,
            freshness_policy_version=batch.freshness_policy_version,
            observed_at=_utc_instant(item.observed_at),
            received_at=_utc_instant(item.received_at),
            revision=revision,
            open=None,
            high=None,
            low=None,
            close=None,
            volume=normalized_value if batch.capability == "TRADED_VOLUME" else None,
            spread=None,
            measures={
                "payload": dict(item.payload),
                "native_batch": native_rows,
                "normalized_value": str(normalized_value) if normalized_value is not None else None,
                "provider_event_id": item.provider_event_id,
                "sequence": item.sequence,
                "provider_revision": item.revision,
                "quality_flags": list(item.quality_flags),
            },
            complete=complete and item.complete,
            conflict_state=conflict_state.value,
            raw_reference=manifest.raw_reference,
            quality=quality,
        )
        database.add(row)
        persisted.append(row)
    database.flush()
    return PersistedProviderBatch(manifest, tuple(persisted))


def _provider_observation_document(item: ProviderObservation) -> dict[str, object]:
    return {
        "provider": item.provider,
        "provider_symbol": item.provider_symbol,
        "venue": item.venue,
        "capability": str(item.capability),
        "semantics": item.semantics.value,
        "observed_at": item.observed_at.isoformat() if item.observed_at else None,
        "received_at": item.received_at.isoformat(),
        "provider_event_id": item.provider_event_id,
        "sequence": item.sequence,
        "revision": item.revision,
        "complete": item.complete,
        "quality_flags": list(item.quality_flags),
        "payload": item.payload,
    }


def _positive_revision(value: str | None) -> int:
    if value is None:
        return 1
    try:
        parsed = int(value)
    except ValueError:
        return 1
    return max(1, parsed)


def normalize_bar(raw: dict[str, object]) -> CanonicalBar:
    observed_at = _utc_instant(raw["observed_at"])
    revision = int(raw.get("revision", 1))
    if revision < 1:
        raise ValueError("market-data revision must be positive")
    return CanonicalBar(
        observed_at=observed_at,
        open=as_decimal(raw["open"]),
        high=as_decimal(raw["high"]),
        low=as_decimal(raw["low"]),
        close=as_decimal(raw["close"]),
        volume=as_decimal(raw["volume"]) if raw.get("volume") is not None else None,
        spread=as_decimal(raw["spread"]) if raw.get("spread") is not None else None,
        revision=revision,
    )


def retain_latest_revision(bars: Iterable[CanonicalBar]) -> list[CanonicalBar]:
    latest: dict[datetime, CanonicalBar] = {}
    for bar in bars:
        old = latest.get(bar.observed_at)
        if old is not None and bar.revision == old.revision and bar != old:
            raise ValueError("contradictory market-data values share the same revision")
        if old is None or bar.revision > old.revision:
            latest[bar.observed_at] = bar
    return [latest[key] for key in sorted(latest)]


def merge_incremental(
    existing: Iterable[CanonicalBar], incoming: Iterable[CanonicalBar]
) -> list[CanonicalBar]:
    """Merge an overlapping incremental window without silently choosing contradictions."""

    return retain_latest_revision([*existing, *incoming])


def manifest_hash(bars: Iterable[CanonicalBar]) -> str:
    document = [
        (
            bar.observed_at.isoformat(),
            str(bar.open),
            str(bar.high),
            str(bar.low),
            str(bar.close),
            str(bar.volume) if bar.volume is not None else None,
            str(bar.spread) if bar.spread is not None else None,
            bar.revision,
        )
        for bar in retain_latest_revision(bars)
    ]
    return hashlib.sha256(json.dumps(document, separators=(",", ":")).encode()).hexdigest()


def build_parquet_artifact(
    batch: ProviderBatch,
    raw_bars: Iterable[dict[str, object]],
    *,
    existing: Iterable[CanonicalBar] = (),
) -> tuple[list[CanonicalBar], ParquetArtifact]:
    """Normalize and revision-merge a provider batch into deterministic Parquet evidence."""

    retrieved_at = _utc_instant(batch.retrieved_at)
    normalized = merge_incremental(existing, (normalize_bar(item) for item in raw_bars))
    frame = pl.DataFrame(
        {
            "observed_at": [bar.observed_at for bar in normalized],
            "open": [str(bar.open) for bar in normalized],
            "high": [str(bar.high) for bar in normalized],
            "low": [str(bar.low) for bar in normalized],
            "close": [str(bar.close) for bar in normalized],
            "volume": [str(bar.volume) if bar.volume is not None else None for bar in normalized],
            "spread": [str(bar.spread) if bar.spread is not None else None for bar in normalized],
            "revision": [bar.revision for bar in normalized],
            "provider": [batch.provider for _ in normalized],
            "provider_symbol": [batch.provider_symbol for _ in normalized],
            "retrieved_at": [retrieved_at for _ in normalized],
            "venue": [batch.venue for _ in normalized],
            "capability": [batch.capability for _ in normalized],
            "semantics": [batch.semantics for _ in normalized],
            "source_role": [batch.source_role for _ in normalized],
            "catalogue_revision": [batch.catalogue_revision for _ in normalized],
            "adapter_revision": [batch.adapter_revision for _ in normalized],
            "mapping_revision": [batch.mapping_revision for _ in normalized],
        }
    )
    target = io.BytesIO()
    frame.write_parquet(target, compression="zstd", statistics=True)
    content = target.getvalue()
    return normalized, ParquetArtifact(
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        source_hash=batch.content_hash,
        row_count=len(normalized),
        coverage_start=normalized[0].observed_at if normalized else None,
        coverage_end=normalized[-1].observed_at if normalized else None,
        cursor=batch.cursor,
        source_manifest={
            "provider": batch.provider,
            "provider_symbol": batch.provider_symbol,
            "venue": batch.venue,
            "capability": batch.capability,
            "semantics": batch.semantics,
            "source_role": batch.source_role,
            "catalogue_revision": batch.catalogue_revision,
            "adapter_revision": batch.adapter_revision,
            "mapping_revision": batch.mapping_revision,
            "freshness_policy_version": batch.freshness_policy_version,
            "retry_policy_version": batch.retry_policy_version,
            "entitlement_status": batch.entitlement_status,
            "source_observed_at": (
                _utc_instant(batch.source_observed_at).isoformat()
                if batch.source_observed_at is not None
                else None
            ),
            "retrieved_at": retrieved_at.isoformat(),
            "source_hash": batch.content_hash,
            "raw_reference": batch.raw_reference,
            "complete": bool(normalized),
        },
    )


def _utc_instant(value: object) -> datetime:
    instant: datetime
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("observed_at must be an ISO-8601 string or datetime")
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("market-data timestamps must include an offset")
    return instant.astimezone(UTC)
