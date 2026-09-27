"""Conservative weekend closure policy; not a broker holiday calendar."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from packages.shared.domain_types import AssetClass


def weekend_close(asset_class: AssetClass | str | None, now: datetime) -> datetime | None:
    """FX/metals close Fri 17:00 to Sun 17:00 New York; stocks weekends only.

    Stock weekend reference is Friday 16:00 New York. Venue holidays and daily
    broker session breaks need authoritative calendars; they are not inferred.
    Crypto never receives a closed-session freshness exception.
    """
    if asset_class not in {AssetClass.FOREX, AssetClass.METALS, AssetClass.STOCKS}:
        return None
    local = now.astimezone(ZoneInfo("America/New_York"))
    stocks = asset_class == AssetClass.STOCKS
    closed = (
        local.weekday() == 5
        or (local.weekday() == 6 and (stocks or local.hour < 17))
        or (not stocks and local.weekday() == 4 and local.hour >= 17)
    )
    if not closed:
        return None
    friday = local.date() - timedelta(days=(local.weekday() - 4) % 7)
    return datetime(
        friday.year,
        friday.month,
        friday.day,
        16 if stocks else 17,
        tzinfo=local.tzinfo,
    ).astimezone(UTC)
