from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import polars as pl

from traderx.shared.types import as_decimal


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
