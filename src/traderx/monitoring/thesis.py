from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FrozenThesis:
    evidence: dict[str, object]


def freeze_thesis(recommendation_evidence: dict[str, object]) -> FrozenThesis:
    return FrozenThesis(copy.deepcopy(recommendation_evidence))
