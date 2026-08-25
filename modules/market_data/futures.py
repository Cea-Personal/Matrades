"""Dated futures selection; continuous series are analytical inputs only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from modules.market_data.models import ContinuousFuture, FuturesContract, RollRule


def executable_contract(
    contracts: list[FuturesContract],
    *,
    as_of: datetime,
    rule: RollRule,
) -> FuturesContract:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    eligible = [
        contract
        for contract in contracts
        if contract.status == "ACTIVE"
        and contract.listed_at <= as_of
        and as_of < contract.last_trade
        and (
            contract.first_notice is None
            or as_of < contract.first_notice - timedelta(days=rule.first_notice_buffer_days)
        )
    ]
    if not eligible:
        raise ValueError("no dated futures contract is executable at this time")
    return sorted(eligible, key=lambda item: (item.last_trade, item.contract_code))[0]


def reject_continuous_for_execution(series: ContinuousFuture) -> None:
    if not series.executable:
        raise ValueError("continuous futures series is analytical only")


def roll_required(contract: FuturesContract, *, now: datetime, rule: RollRule) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if contract.first_notice and now >= contract.first_notice - timedelta(
        days=rule.first_notice_buffer_days
    ):
        return True
    return now >= contract.last_trade - timedelta(days=rule.last_trade_buffer_days)
