from decimal import Decimal

from traderx.monitoring.monitor import evaluate_thesis
from traderx.monitoring.thesis import freeze_thesis


def test_thesis_is_frozen_and_invalidation_drives_guidance() -> None:
    source = {"entry": Decimal("100")}
    thesis = freeze_thesis(source)
    source["entry"] = Decimal("1")
    assert thesis.evidence["entry"] == Decimal("100")
    assert (
        evaluate_thesis(
            current_price=Decimal("90"),
            invalidation_price=Decimal("95"),
            favorable_distance=Decimal("10"),
            direction="LONG",
        ).health
        == "INVALIDATED"
    )
