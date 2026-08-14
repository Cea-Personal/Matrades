from decimal import Decimal

import pytest

from traderx.monitoring.monitor import evaluate_thesis
from traderx.monitoring.thesis import freeze_thesis


def test_thesis_is_frozen_and_invalidation_drives_guidance() -> None:
    source = {"entry": Decimal("100")}
    thesis = freeze_thesis(source)
    source["entry"] = Decimal("1")
    assert thesis.evidence["entry"] == Decimal("100")
    assert len(thesis.evidence_hash) == 64
    with pytest.raises(TypeError):
        thesis.evidence["entry"] = Decimal("2")  # type: ignore[index]
    assert (
        evaluate_thesis(
            current_price=Decimal("90"),
            invalidation_price=Decimal("95"),
            favorable_distance=Decimal("10"),
            direction="LONG",
        ).health
        == "INVALIDATED"
    )


def test_thesis_health_covers_strong_healthy_watch_weakening_and_invalidated() -> None:
    states = [
        evaluate_thesis(
            current_price=price,
            invalidation_price=Decimal("90"),
            favorable_distance=Decimal("10"),
            direction="LONG",
        ).health
        for price in (Decimal("106"), Decimal("100"), Decimal("96"), Decimal("92"), Decimal("89"))
    ]
    assert states == ["STRONG", "HEALTHY", "WATCH", "WEAKENING", "INVALIDATED"]
