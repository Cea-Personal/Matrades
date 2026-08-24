from __future__ import annotations

from collections.abc import Callable


def chronological_replay(rows: list[dict], evaluator: Callable[[dict], bool]) -> list[bool]:
    ordered = sorted(rows, key=lambda row: row["observed_at"])
    if ordered != rows:
        raise ValueError("replay input must be chronological")
    return [
        evaluator({key: value for key, value in row.items() if key != "future"}) for row in rows
    ]
