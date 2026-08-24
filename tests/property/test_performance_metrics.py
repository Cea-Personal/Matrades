from decimal import Decimal
from uuid import uuid4

from modules.performance.metrics import aggregate
from modules.performance.models import PerformanceRecord


def test_attribution_preserves_total_pnl():
    owner = uuid4()
    records = [
        PerformanceRecord(
            owner_id=owner,
            trade_id=uuid4(),
            strategy_version_id=uuid4(),
            account_id=uuid4(),
            instrument=x,
            category="fx",
            regime="trend",
            session="london",
            pnl=Decimal(p),
            risk=Decimal("1"),
        )
        for x, p in (("EURUSD", "2"), ("GBPUSD", "-1"))
    ]
    groups = aggregate(records, "category")
    assert groups["fx"]["pnl"] == Decimal("1")
