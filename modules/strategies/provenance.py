from dataclasses import dataclass

from packages.strategy_sdk.taxonomy import StrategyOrigin


@dataclass(frozen=True)
class RuleProvenance:
    path: str
    origin: StrategyOrigin
    ai_contribution: bool
    user_decision: str | None
    revision: int
    author_id: str
