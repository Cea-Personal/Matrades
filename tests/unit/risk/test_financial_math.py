from decimal import Decimal

import pytest

from modules.risk.financial_math import conservative_entry, loss_per_unit, size_for_risk


def test_conservative_side_and_rounding() -> None:
    assert conservative_entry("BUY", Decimal("1.1"), Decimal("1.2")) == Decimal("1.2")
    assert conservative_entry("SELL", Decimal("1.1"), Decimal("1.2")) == Decimal("1.1")
    assert size_for_risk(Decimal("101"), Decimal("30"), Decimal("0.1")) == Decimal("3.3")


def test_contract_and_conversion_value() -> None:
    assert loss_per_unit(
        Decimal("1.10"), Decimal("1.09"), Decimal("100000"), Decimal("1")
    ) == Decimal("1000.00")
    with pytest.raises(ValueError):
        loss_per_unit(Decimal("1"), Decimal("0"))
