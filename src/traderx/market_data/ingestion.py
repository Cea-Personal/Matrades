from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

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


def normalize_bar(raw: dict[str, object]) -> CanonicalBar:
    return CanonicalBar(
        observed_at=raw["observed_at"],  # type: ignore[arg-type]
        open=as_decimal(raw["open"]),
        high=as_decimal(raw["high"]),
        low=as_decimal(raw["low"]),
        close=as_decimal(raw["close"]),
        volume=as_decimal(raw["volume"]) if raw.get("volume") is not None else None,
        spread=as_decimal(raw["spread"]) if raw.get("spread") is not None else None,
        revision=int(raw.get("revision", 1)),
    )


def retain_latest_revision(bars: Iterable[CanonicalBar]) -> list[CanonicalBar]:
    latest: dict[datetime, CanonicalBar] = {}
    for bar in bars:
        old = latest.get(bar.observed_at)
        if old is None or bar.revision > old.revision:
            latest[bar.observed_at] = bar
    return [latest[key] for key in sorted(latest)]


def manifest_hash(bars: Iterable[CanonicalBar]) -> str:
    document = [
        (
            bar.observed_at.isoformat(),
            str(bar.open),
            str(bar.high),
            str(bar.low),
            str(bar.close),
            bar.revision,
        )
        for bar in retain_latest_revision(bars)
    ]
    return hashlib.sha256(json.dumps(document, separators=(",", ":")).encode()).hexdigest()
