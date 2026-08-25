from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from modules.market_data.models import MarketObservation
from packages.shared.domain_types import utc_now


@dataclass(frozen=True)
class SourceCut:
    provider: str
    endpoint: str
    window_start: datetime
    window_end: datetime
    cut_id: str
    cost_weight: int = 1


def plan_source_cuts(
    provider: str,
    endpoint: str,
    windows: Iterable[tuple[datetime, datetime]],
    *,
    cost_weight: int = 1,
) -> list[SourceCut]:
    """Deduplicate identical account requests into one immutable source cut."""
    result: list[SourceCut] = []
    seen: set[str] = set()
    for start, end in windows:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("source-cut windows must be aware and increasing")
        start = start.astimezone(UTC)
        end = end.astimezone(UTC)
        cut_id = f"{provider}:{endpoint}:{start.isoformat()}:{end.isoformat()}"
        if cut_id in seen:
            continue
        seen.add(cut_id)
        result.append(SourceCut(provider, endpoint, start, end, cut_id, max(cost_weight, 1)))
    return result


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity = max(capacity, 1)
        self.tokens = float(self.capacity)
        self.refill_per_second = max(refill_per_second, 0.0)
        self.observed_at = datetime.now(UTC)

    def consume(self, weight: int = 1) -> bool:
        now = datetime.now(UTC)
        elapsed = (now - self.observed_at).total_seconds()
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.observed_at = now
        if self.tokens < weight:
            return False
        self.tokens -= weight
        return True


def retry_after_seconds(headers: dict[str, str]) -> int | None:
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None


def normalize(
    observation: MarketObservation, max_age: timedelta = timedelta(seconds=30)
) -> MarketObservation:
    if observation.observed_at > observation.received_at:
        raise ValueError("future observations are not permitted")
    if utc_now() - observation.observed_at > max_age:
        raise ValueError("observation is stale")
    if (
        observation.bid is not None
        and observation.ask is not None
        and observation.ask < observation.bid
    ):
        raise ValueError("crossed quote")
    if not observation.provenance:
        raise ValueError("provenance is required")
    return observation
