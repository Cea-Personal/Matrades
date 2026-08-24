from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySetup:
    strategy_version: str
    eligible: bool
    direction: str
    evidence: tuple[str, ...]


def detect_setup(strategy_version: str, facts: dict[str, bool], direction: str) -> StrategySetup:
    ordered = tuple(sorted(key for key, value in facts.items() if value))
    return StrategySetup(strategy_version, bool(facts) and all(facts.values()), direction, ordered)
