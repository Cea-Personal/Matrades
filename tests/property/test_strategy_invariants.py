from decimal import Decimal

from modules.strategies.fingerprints import fingerprint
from packages.strategy_sdk.schema import Condition, StrategySpecification
from packages.strategy_sdk.taxonomy import Horizon, StrategyFamily, StrategyOrigin


def spec(origin):
    return StrategySpecification(
        name="x",
        origin=origin,
        family=StrategyFamily.TREND,
        horizon=Horizon.SWING,
        instruments=["XAUUSD"],
        entry=[Condition(feature="close", operator=">", value=Decimal("1"))],
        exit=[Condition(feature="close", operator="<", value=Decimal("1"))],
        stop_loss=Condition(feature="atr", operator=">", value=Decimal("0")),
        risk_per_trade=Decimal("1"),
    )


def test_origin_does_not_change_canonical_identity():
    assert len({fingerprint(spec(origin)) for origin in StrategyOrigin}) == 1
