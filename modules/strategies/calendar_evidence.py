"""Fail closed when historical event restrictions lack covered calendar dates."""

from datetime import timedelta


def historical_calendar(archive, owner_id, start, end):
    periods = archive.list_periods(owner_id)
    day, last = start.date() - timedelta(days=1), end.date() + timedelta(days=1)
    missing = []
    while day <= last:
        if not any(p.period_start <= day <= p.period_end for p in periods):
            missing.append(day.isoformat())
        day += timedelta(days=1)
    selected = [
        p
        for p in periods
        if p.period_end >= start.date() - timedelta(days=1) and p.period_start <= last
    ]
    events = {str(event): event for p in selected for event in p.events}
    coverage = {
        "complete": not missing,
        "missing_dates": missing,
        "periods": [p.period_key for p in selected],
    }
    return (list(events.values()) if not missing else None), coverage
