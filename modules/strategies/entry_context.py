"""Shared historical and forward session/event constraints."""

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.research.sessions import weekend_close
from packages.strategy_sdk.schema import StrategySpecification


def entry_context_reason(
    spec: StrategySpecification, now: datetime, calendar: list[dict] | None
) -> str | None:
    if weekend_close(spec.asset_class, now):
        return "Market session is closed"
    if spec.asset_class == "STOCKS":
        local = now.astimezone(ZoneInfo("America/New_York"))
        if local.weekday() >= 5 or not 570 <= local.hour * 60 + local.minute < 960:
            return "Stock market session is closed"
    sessions = {
        "LONDON": ("Europe/London", 8, 17),
        "NEW_YORK": ("America/New_York", 8, 17),
        "TOKYO": ("Asia/Tokyo", 9, 18),
        "ASIA": ("Asia/Tokyo", 9, 18),
        "SYDNEY": ("Australia/Sydney", 8, 17),
    }
    wanted = [name.upper() for name in spec.sessions]
    if any(name not in {*sessions, "ALL", "24/7"} for name in wanted):
        return "Strategy session rules are unsupported; revise and validate the strategy"
    if wanted and not {"ALL", "24/7"}.intersection(wanted):
        if not any(
            start <= now.astimezone(ZoneInfo(zone)).hour < end
            and now.astimezone(ZoneInfo(zone)).weekday() < 5
            for zone, start, end in (sessions[name] for name in wanted)
        ):
            return "Outside the strategy's trading sessions"
    if any(rule != "block_high_impact_events" for rule in spec.event_rules):
        return "Strategy event rules are unsupported; revise and validate the strategy"
    if spec.event_rules:
        if calendar is None:
            return "Economic calendar coverage is unavailable for the current session"
        symbol = spec.instruments[0].upper().replace("/", "").replace("-", "")
        currencies = {symbol[:3], symbol[3:6]}
        for event in calendar:
            if event.get("impact", "").upper() == "HIGH" and event.get("currency") in currencies:
                if (
                    abs((datetime.fromisoformat(event["scheduled_at"]) - now).total_seconds())
                    <= 1800
                ):
                    return "High-impact event within the strategy's 30-minute event window"
    return None
