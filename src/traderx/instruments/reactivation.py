from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CoverageGap:
    start: datetime
    end: datetime


def missing_intervals(
    covered: list[tuple[datetime, datetime]], *, required_start: datetime, required_end: datetime
) -> list[CoverageGap]:
    cursor = required_start
    gaps: list[CoverageGap] = []
    for start, end in sorted(covered):
        if start > cursor:
            gaps.append(CoverageGap(cursor, start))
        cursor = max(cursor, end)
    if cursor < required_end:
        gaps.append(CoverageGap(cursor, required_end))
    return gaps
