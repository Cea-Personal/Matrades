from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal

SCHEMA_VERSION = "strategy-v1"


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    regime: str
    timeframes: tuple[str, ...]
    conditions: tuple[dict[str, object], ...]
    filters: tuple[dict[str, object], ...] = ()
    stop: dict[str, object] = field(default_factory=dict)
    target: dict[str, object] = field(default_factory=dict)
    invalidation: dict[str, object] = field(default_factory=dict)
    expiration: dict[str, object] = field(default_factory=dict)
    risk_fraction: Decimal = Decimal("0.01")
    schema_version: str = SCHEMA_VERSION

    def canonical(self) -> dict[str, object]:
        output = asdict(self)
        output["risk_fraction"] = str(self.risk_fraction)
        return output
