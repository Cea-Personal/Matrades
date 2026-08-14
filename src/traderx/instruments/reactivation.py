from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CoverageGap:
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class CoverageWindow:
    start: datetime
    end: datetime
    provider: str
    native_symbol: str


@dataclass(frozen=True, slots=True)
class AliasWindow:
    instrument_id: UUID
    provider: str
    native_symbol: str
    valid_from: datetime
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class IncrementalRefreshPlan:
    instrument_id: UUID
    required_start: datetime
    required_end: datetime
    aliases: tuple[AliasWindow, ...]
    missing: tuple[CoverageGap, ...]

    @property
    def refresh_required(self) -> bool:
        return bool(self.missing)


def missing_intervals(
    covered: list[tuple[datetime, datetime]], *, required_start: datetime, required_end: datetime
) -> list[CoverageGap]:
    if required_end <= required_start:
        raise ValueError("required_end must be after required_start")
    cursor = required_start
    gaps: list[CoverageGap] = []
    for start, end in sorted(covered):
        if end <= required_start or start >= required_end:
            continue
        start = max(start, required_start)
        end = min(end, required_end)
        if end <= start:
            continue
        if start > cursor:
            gaps.append(CoverageGap(cursor, start))
        cursor = max(cursor, end)
        if cursor >= required_end:
            break
    if cursor < required_end:
        gaps.append(CoverageGap(cursor, required_end))
    return gaps


def reconcile_aliases(
    aliases: list[AliasWindow],
    *,
    instrument_id: UUID,
    provider: str,
    required_start: datetime,
    required_end: datetime,
) -> tuple[AliasWindow, ...]:
    """Return the canonical alias chain covering an interval or fail on ambiguity/gaps."""
    relevant = sorted(
        (
            alias
            for alias in aliases
            if alias.instrument_id == instrument_id
            and alias.provider == provider
            and alias.valid_from < required_end
            and (alias.valid_to is None or alias.valid_to > required_start)
        ),
        key=lambda alias: (alias.valid_from, alias.native_symbol),
    )
    for index, alias in enumerate(relevant):
        alias_end = alias.valid_to or required_end
        for overlapping in relevant[index + 1 :]:
            if overlapping.valid_from >= alias_end:
                break
            if overlapping.native_symbol != alias.native_symbol:
                raise ValueError("instrument alias history is ambiguous")
    cursor = required_start
    resolved: list[AliasWindow] = []
    for alias in relevant:
        end = alias.valid_to or required_end
        if alias.valid_from > cursor:
            raise ValueError("instrument alias history has an uncovered interval")
        if resolved and alias.valid_from < cursor and resolved[-1].native_symbol != alias.native_symbol:
            raise ValueError("instrument alias history is ambiguous")
        cursor = max(cursor, min(end, required_end))
        resolved.append(alias)
        if cursor >= required_end:
            break
    if cursor < required_end:
        raise ValueError("instrument alias history does not cover the required interval")
    return tuple(resolved)


def plan_incremental_refresh(
    *,
    instrument_id: UUID,
    provider: str,
    aliases: list[AliasWindow],
    coverage: list[CoverageWindow],
    required_start: datetime,
    required_end: datetime,
) -> IncrementalRefreshPlan:
    alias_chain = reconcile_aliases(
        aliases,
        instrument_id=instrument_id,
        provider=provider,
        required_start=required_start,
        required_end=required_end,
    )
    valid_symbols = {alias.native_symbol for alias in alias_chain}
    covered = [
        (window.start, window.end)
        for window in coverage
        if window.provider == provider and window.native_symbol in valid_symbols
    ]
    return IncrementalRefreshPlan(
        instrument_id=instrument_id,
        required_start=required_start,
        required_end=required_end,
        aliases=alias_chain,
        missing=tuple(
            missing_intervals(
                covered,
                required_start=required_start,
                required_end=required_end,
            )
        ),
    )
