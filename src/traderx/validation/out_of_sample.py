from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChronologicalSplits[T]:
    development: list[T]
    validation: list[T]
    out_of_sample: list[T]


def chronological_split[T](
    values: list[T], development_fraction: float = 0.6, validation_fraction: float = 0.2
) -> ChronologicalSplits[T]:
    if (
        not 0 < development_fraction < 1
        or not 0 < validation_fraction < 1
        or development_fraction + validation_fraction >= 1
    ):
        raise ValueError("split fractions must leave an out-of-sample segment")
    development_end = int(len(values) * development_fraction)
    validation_end = development_end + int(len(values) * validation_fraction)
    return ChronologicalSplits(
        values[:development_end], values[development_end:validation_end], values[validation_end:]
    )
