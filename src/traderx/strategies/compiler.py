from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from traderx.strategies.schema import StrategyDefinition


@dataclass(frozen=True, slots=True)
class CompiledStrategy:
    definition: StrategyDefinition
    definition_hash: str


def validate_definition(definition: StrategyDefinition) -> None:
    if not definition.regime or not definition.timeframes or not definition.conditions:
        raise ValueError("strategy requires a regime, timeframes, and at least one condition")
    if not Decimal("0") < definition.risk_fraction <= Decimal("0.02"):
        raise ValueError(
            "strategy risk fraction must be greater than zero and no more than two percent"
        )
    if definition.direction not in {"LONG", "SHORT", "BOTH"}:
        raise ValueError("strategy direction must be LONG, SHORT, or BOTH")
    if not definition.stop or not definition.target or not definition.invalidation:
        raise ValueError("strategy requires stop, target, and invalidation definitions")
    for condition in definition.conditions:
        if not {"field", "operator", "value"}.issubset(condition):
            raise ValueError("each condition requires field, operator, and value")


def compile_strategy(definition: StrategyDefinition) -> CompiledStrategy:
    validate_definition(definition)
    canonical = json.dumps(
        definition.canonical(), sort_keys=True, separators=(",", ":"), default=str
    )
    return CompiledStrategy(definition, hashlib.sha256(canonical.encode()).hexdigest())
