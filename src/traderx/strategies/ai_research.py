from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from traderx.strategies.schema import StrategyDefinition

PROMPT_TEMPLATE_VERSION = "strategy-blueprint-v2"
OUTPUT_SCHEMA_VERSION = "strategy-blueprint-v2"
INFERENCE_POLICY_VERSION = "bounded-no-tools-v1"


class StrategySelection(BaseModel):
    """The model chooses a family, never arbitrary executable strategy rules."""

    model_config = ConfigDict(extra="forbid", strict=True)

    strategy_family: Literal["TREND_FOLLOWING", "MEAN_REVERSION", "BREAKOUT"]
    direction: Literal["LONG", "SHORT"]
    primary_timeframe: Literal["H1", "H4", "D1"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=16, max_length=1600)
    cautions: list[str] = Field(max_length=12)


def selection_json_schema() -> dict[str, Any]:
    return StrategySelection.model_json_schema()


def validate_selection(value: object) -> StrategySelection:
    return StrategySelection.model_validate(value)


def strategy_definition_for(selection: StrategySelection, *, price: Decimal) -> StrategyDefinition:
    """Compile an LLM-selected family to bounded deterministic rules.

    The model may select among reviewed families and explain why, but cannot
    supply arbitrary rules, risk, or execution instructions.
    """

    if price <= 0:
        raise ValueError("strategy research requires a positive current price")
    timeframe = selection.primary_timeframe
    direction = selection.direction
    if selection.strategy_family == "TREND_FOLLOWING":
        threshold = price * (Decimal("1.001") if direction == "LONG" else Decimal("0.999"))
        regime = "TREND"
        operator = ">" if direction == "LONG" else "<"
        stop, target, expiry = "0.006", "2.0", 12
    elif selection.strategy_family == "MEAN_REVERSION":
        threshold = price * (Decimal("0.996") if direction == "LONG" else Decimal("1.004"))
        regime = "RANGE"
        operator = "<" if direction == "LONG" else ">"
        stop, target, expiry = "0.004", "1.5", 8
    else:
        threshold = price * (Decimal("1.003") if direction == "LONG" else Decimal("0.997"))
        regime = "BREAKOUT"
        operator = ">" if direction == "LONG" else "<"
        stop, target, expiry = "0.007", "2.2", 10
    return StrategyDefinition(
        regime=regime,
        direction=direction,
        timeframes=(timeframe,),
        conditions=(
            {
                "field": "close",
                "operator": operator,
                "value": str(threshold.quantize(Decimal("0.00000001"))),
            },
        ),
        filters=(
            {"field": "spread_bps", "operator": "<", "value": "15"},
        ),
        stop={"type": "PERCENT", "value": stop},
        target={"type": "RR", "value": target},
        invalidation={"type": "REGIME_CHANGE"},
        expiration={"type": "BARS", "value": expiry},
        risk_fraction=Decimal("0.005"),
    )


def strategy_blueprint_for(
    selection: StrategySelection, definition: StrategyDefinition
) -> dict[str, object]:
    """Return the human-readable representation of the compiled draft.

    This is deliberately derived from the immutable definition, rather than
    generated prose, so the result panel cannot describe rules that differ
    from the strategy saved for backtesting and approval.
    """

    condition = definition.conditions[0]
    operator = {">": "closes above", "<": "closes below", "==": "closes at"}.get(
        str(condition["operator"]), str(condition["operator"])
    )
    threshold = str(condition["value"])
    stop_value = Decimal(str(definition.stop["value"])) * Decimal("100")
    return {
        "title": (
            f"{selection.primary_timeframe} {selection.strategy_family.replace('_', ' ').title()} "
            f"{selection.direction.title()}"
        ),
        "family": selection.strategy_family,
        "direction": selection.direction,
        "timeframe": selection.primary_timeframe,
        "market_regime": definition.regime,
        "entry_qualification": (
            f"A {selection.primary_timeframe} candle {operator} {threshold}. "
            "No entry is qualified until this condition is true."
        ),
        "liquidity_filter": "Reported spread must remain below 15 basis points.",
        "stop_loss": f"{stop_value.normalize():f}% adverse move from the qualified entry.",
        "take_profit": f"{definition.target['value']}:1 reward-to-risk target.",
        "invalidation": str(definition.invalidation["type"]).replace("_", " ").title(),
        "expiry": f"Expires after {definition.expiration['value']} {selection.primary_timeframe} bars.",
        "risk_per_trade": f"{(definition.risk_fraction * Decimal('100')).normalize():f}% of account equity.",
    }


def system_instruction() -> str:
    return (
        "You are TraderX's strategy research agent. Analyze only the supplied normalized "
        "evidence for one already-active market. Select exactly one best-fit strategy family "
        "from TREND_FOLLOWING, MEAN_REVERSION, or BREAKOUT and one direction. This is a "
        "strategy-design proposal, not a trade recommendation: explain why the selected family, "
        "direction, and timeframe fit the supplied evidence. TraderX will compile the exact entry, "
        "filter, stop, target, expiry, and 0.5% risk rules from its reviewed deterministic template. "
        "It cannot alter active-market selection, risk limits, or place orders. Do not invent prices, "
        "data, indicators, or custom rules. Return every schema key; use an empty cautions array "
        "when there are no cautions."
    )
