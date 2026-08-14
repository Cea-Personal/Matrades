from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChronologicalSplits[T]:
    development: list[T]
    validation: list[T]
    out_of_sample: list[T]


@dataclass(frozen=True, slots=True)
class WalkForwardWindow[T]:
    training: list[T]
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


def rolling_walk_forward[T](
    values: list[T], *, training_size: int, validation_size: int, out_of_sample_size: int, step: int
) -> list[WalkForwardWindow[T]]:
    if min(training_size, validation_size, out_of_sample_size, step) <= 0:
        raise ValueError("walk-forward window sizes and step must be positive")
    window_size = training_size + validation_size + out_of_sample_size
    windows: list[WalkForwardWindow[T]] = []
    for start in range(0, len(values) - window_size + 1, step):
        training_end = start + training_size
        validation_end = training_end + validation_size
        windows.append(
            WalkForwardWindow(
                training=values[start:training_end],
                validation=values[training_end:validation_end],
                out_of_sample=values[validation_end : validation_end + out_of_sample_size],
            )
        )
    return windows
