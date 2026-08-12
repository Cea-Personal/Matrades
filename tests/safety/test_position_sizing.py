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
