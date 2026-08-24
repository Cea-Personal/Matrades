from __future__ import annotations

from modules.risk.reservations import ReservationBook
from modules.trading.proposals import ProposalService

reservation_book = ReservationBook()
proposal_service = ProposalService(reservation_book)
