from datetime import timedelta

from modules.risk.reservations import RiskReservation
from packages.shared.domain_types import utc_now


def awaiting_entry_valid(
    reservation: RiskReservation, max_wait: timedelta = timedelta(minutes=10)
) -> bool:
    return reservation.expires_at > utc_now() and reservation.expires_at - utc_now() <= max_wait
