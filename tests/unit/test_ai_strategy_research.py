import json
from decimal import Decimal

from traderx.strategies.ai_research import (
    strategy_blueprint_for,
    strategy_definition_for,
    validate_selection,
)
from traderx.strategies.lifecycle import definition_from_payload


def test_ai_selection_is_compiled_to_bounded_deterministic_rules() -> None:
    selection = validate_selection(
        {
            "strategy_family": "BREAKOUT",
            "direction": "LONG",
            "primary_timeframe": "H4",
            "confidence": 0.72,
            "rationale": "Fresh volatility and liquidity evidence support a continuation breakout test.",
            "cautions": [],
        }
    )

    definition = strategy_definition_for(selection, price=Decimal("100"))

    assert definition.regime == "BREAKOUT"
    assert definition.direction == "LONG"
    assert definition.timeframes == ("H4",)
    assert definition.risk_fraction == Decimal("0.005")
    assert definition.conditions[0] == {"field": "close", "operator": ">", "value": "100.30000000"}
    assert definition.stop == {"type": "PERCENT", "value": "0.007"}
    blueprint = strategy_blueprint_for(selection, definition)
    assert blueprint["entry_qualification"] == "A H4 candle closes above 100.30000000. No entry is qualified until this condition is true."
    assert blueprint["risk_per_trade"] == "0.5% of account equity."
    # AI strategy drafts cross a JSON job boundary before the immutable
    # lifecycle compiler receives them.
    restored = definition_from_payload(json.loads(json.dumps(definition.canonical())))
    assert restored.timeframes == ("H4",)


def test_ai_selection_rejects_unapproved_strategy_families() -> None:
    invalid = {
        "strategy_family": "ARBITRARY_CODE",
        "direction": "LONG",
        "primary_timeframe": "H1",
        "confidence": 0.5,
        "rationale": "This should fail because the family is not in TraderX's approved catalogue.",
        "cautions": [],
    }

    try:
        validate_selection(invalid)
    except ValueError:
        return
    raise AssertionError("unapproved AI strategy family was accepted")
