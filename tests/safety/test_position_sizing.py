from decimal import Decimal

from traderx.risk.sizing import size_position


def test_sizing_rounds_down_and_never_increases_risk() -> None:
    assert size_position(
        permitted_risk=Decimal("101"),
        entry=Decimal("110"),
        stop=Decimal("100"),
        point_value=Decimal("1"),
        minimum=Decimal(".1"),
        step=Decimal(".1"),
        conversion_quality_verified=True,
    ) == Decimal("10.1")
    assert (
        size_position(
            permitted_risk=Decimal("101"),
            entry=Decimal("110"),
            stop=Decimal("100"),
            point_value=Decimal("1"),
            minimum=Decimal(".1"),
            step=Decimal(".1"),
            conversion_quality_verified=False,
        )
        == 0
    )


def test_cross_currency_conversion_and_broker_bounds_never_increase_risk() -> None:
    volume = size_position(
        permitted_risk=Decimal("100"),
        entry=Decimal("1.10"),
        stop=Decimal("1.09"),
        point_value=Decimal("1000"),
        minimum=Decimal("0.01"),
        step=Decimal("0.01"),
        conversion_quality_verified=True,
        conversion_rate=Decimal("1.25"),
        maximum=Decimal("5"),
    )
    assert volume == Decimal("5")
    realized_risk = volume * abs(Decimal("1.10") - Decimal("1.09")) * Decimal("1000") * Decimal("1.25")
    assert realized_risk <= Decimal("100")
