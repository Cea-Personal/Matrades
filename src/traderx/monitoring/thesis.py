from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class FrozenThesis:
    evidence: Mapping[str, object]
    evidence_hash: str


def freeze_thesis(recommendation_evidence: dict[str, object]) -> FrozenThesis:
    copied = copy.deepcopy(recommendation_evidence)
    canonical = json.dumps(copied, sort_keys=True, separators=(",", ":"), default=str)
    return FrozenThesis(
        _freeze_mapping(copied),
        hashlib.sha256(canonical.encode()).hexdigest(),
    )


def _freeze_mapping(value: dict[str, object]) -> Mapping[str, object]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, dict):
        return _freeze_mapping({str(key): item for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value
