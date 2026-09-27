"""Fixed CFD baselines: seven families, both directions, no optimizer or LLM call."""

from modules.strategies.ai_workflow import StrategyHypothesis
from packages.strategy_sdk.schema import Condition, StrategySpecification, TradeRules
from packages.strategy_sdk.taxonomy import StrategyFamily


def cfd_family_hypotheses(
    prototype: StrategySpecification, evidence_ref: str
) -> list[StrategyHypothesis]:
    if prototype.instrument_type != "CFD":
        return []
    hypotheses = []
    for direction in ("LONG", "SHORT"):
        up = direction == "LONG"
        greater, lesser = (">", "<") if up else ("<", ">")

        def rule(feature, operator, value):
            return Condition(feature=feature, operator=operator, value=value)

        momentum = rule("momentum", greater, "0")
        trend = rule("close", greater, "slow_average")
        families = [
            (StrategyFamily.TREND, [trend, momentum], ["TRENDING"]),
            (
                StrategyFamily.MOMENTUM,
                [momentum, rule("close", greater, "moving_average")],
                ["TRENDING"],
            ),
            (
                StrategyFamily.BREAKOUT,
                [rule("close", greater, "prior_high" if up else "prior_low")],
                ["TRENDING", "RANGING"],
            ),
            (
                StrategyFamily.PULLBACK,
                [
                    trend,
                    rule("low" if up else "high", "<=" if up else ">=", "moving_average"),
                    momentum,
                ],
                ["TRENDING"],
            ),
            (
                StrategyFamily.MEAN_REVERSION,
                [rule("close", lesser, "slow_average"), momentum],
                ["RANGING"],
            ),
            (
                StrategyFamily.RANGE,
                [
                    rule(
                        "low" if up else "high",
                        "<=" if up else ">=",
                        "prior_low" if up else "prior_high",
                    ),
                    momentum,
                ],
                ["RANGING"],
            ),
            (
                StrategyFamily.LIQUIDITY_SWEEP,
                [
                    rule("low" if up else "high", lesser, "prior_low" if up else "prior_high"),
                    rule("close", greater, "prior_low" if up else "prior_high"),
                ],
                ["RANGING"],
            ),
        ]
        for family, entries, regimes in families:
            data = prototype.model_dump(mode="json")
            data.update(
                {
                    "name": f"{prototype.instruments[0]} {family.value} {direction} baseline",
                    "family": family.value,
                    "regimes": regimes,
                    "entry": [r.model_dump(mode="json") for r in entries],
                    "exit": [rule("momentum", lesser, "0").model_dump(mode="json")],
                    "confirmations": [],
                    "filters": [],
                    "invalidation": [],
                    "sessions": prototype.sessions,
                    "event_rules": prototype.event_rules,
                    "parameters": {},
                    "position_management": {},
                    "stop_loss": rule("volatility", ">", "0").model_dump(mode="json"),
                    "take_profit": [],
                    "trade_rules": TradeRules(
                        direction=direction,
                        stop_volatility_multiple="1.5",
                        take_profit_r_multiples=["1", "2"],
                    ).model_dump(mode="json"),
                    "evaluator_version": "strategy-evaluator-v2",
                }
            )
            hypotheses.append(
                StrategyHypothesis(
                    hypothesis_id=f"BASELINE_{family.value}_{direction}",
                    specification=StrategySpecification.model_validate(data),
                    rationale=(
                        "Fixed research baseline; establish eligibility per instrument "
                        "and regime after execution costs."
                    ),
                    breakdown=[
                        "Detect regime from completed bars",
                        "Evaluate fixed family entry at next bar open",
                        "Simulate volatility protection and costs; validate before use",
                    ],
                    evidence_refs=[evidence_ref],
                    agent_id="deterministic_family_library",
                )
            )
    return hypotheses
