from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from packages.strategy_sdk.schema import StrategySpecification

OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


@dataclass(frozen=True)
class CompiledStrategy:
    artifact_hash: str
    specification: StrategySpecification

    def evaluate(self, features: dict[str, Decimal]) -> bool:
        for rule in self.specification.entry:
            if rule.operator not in OPS or rule.feature not in features:
                return False
            right = features.get(str(rule.value), rule.value)
            right = Decimal(str(right))
            if not OPS[rule.operator](features[rule.feature], right):
                return False
        return True


def compile_strategy(spec: StrategySpecification) -> CompiledStrategy:
    payload = json.dumps(spec.model_dump(mode="json"), sort_keys=True).encode()
    return CompiledStrategy(hashlib.sha256(payload).hexdigest(), spec)
