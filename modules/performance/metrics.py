from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from modules.performance.models import EvidenceClass, PerformanceRecord


def aggregate(
    records: list[PerformanceRecord], dimension: str
) -> dict[str, dict[str, Decimal | int | str]]:
    grouped = defaultdict(list)
    for item in records:
        grouped[str(getattr(item, dimension))].append(item)
    return {key: analytics(items) for key, items in grouped.items()}


def analytics(records: list[PerformanceRecord]) -> dict[str, Decimal | int | str]:
    """Calculate auditable metrics without mixing evidence classes."""
    if not records:
        return {"trades": 0, "pnl": Decimal("0"), "expectancy": Decimal("0")}
    net_values = [
        item.pnl
        - item.financing
        - item.funding
        - item.commissions
        - item.slippage
        - item.spread_cost
        for item in records
    ]
    total = sum(net_values, Decimal("0"))
    wins = [item for item in net_values if item > 0]
    losses = [item for item in net_values if item < 0]
    risk_values = [
        value / item.risk
        for item, value in zip(records, net_values, strict=True)
        if item.risk > 0
    ]
    equity = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for _item, net in zip(records, net_values, strict=True):
        equity += net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    profit_factor = (sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0")))) if losses else None
    evidence = sorted({item.evidence_class.value for item in records})
    return {
        "trades": len(records),
        "pnl": total,
        "expectancy": total / len(records),
        "r": sum(risk_values, Decimal("0")) / len(records) if risk_values else Decimal("0"),
        "win_rate": Decimal(len(wins)) / len(records),
        "gross_profit": sum(wins, Decimal("0")),
        "gross_loss": sum(losses, Decimal("0")),
        "profit_factor": profit_factor if profit_factor is not None else Decimal("Infinity"),
        "max_drawdown": max_drawdown,
        "after_cost": total,
        "sample_status": (
            "COMPLETE" if all(item.status == "COMPLETED" for item in records) else "PARTIAL"
        ),
        "evidence_classes": ",".join(evidence),
    }


def evidence_metrics(records: list[PerformanceRecord]) -> dict[str, dict[str, Decimal | int | str]]:
    return {
        evidence.value: analytics([item for item in records if item.evidence_class is evidence])
        for evidence in EvidenceClass
        if any(item.evidence_class is evidence for item in records)
    }


def wrapper_metrics(records: list[PerformanceRecord]) -> dict[str, dict[str, Decimal | int | str]]:
    """Compare spot, CFD, and futures results without mixing cost semantics."""
    return aggregate(records, "instrument_type") if records else {}
