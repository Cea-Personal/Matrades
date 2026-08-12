from datetime import UTC, datetime
from decimal import Decimal

import pytest

from traderx.shared.types import as_decimal, floor_to_step


def test_rejects_binary_float_at_financial_boundary() -> None:
    with pytest.raises(TypeError):
        as_decimal(0.1)  # type: ignore[arg-type]


def test_floors_volume_to_step_without_increasing_risk() -> None:
    assert floor_to_step(Decimal("1.299"), Decimal("0.01")) == Decimal("1.29")


def test_utc_instants_remain_timezone_aware(frozen_now: datetime) -> None:
    assert frozen_now.tzinfo is UTC


def test_decimal_has_exact_string_representation() -> None:
    assert as_decimal("0.10") + as_decimal("0.20") == Decimal("0.30")
