from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from modules.risk.reservations import ReservationBook


def test_concurrent_trade_plans_cannot_oversubscribe_capacity() -> None:
    book, account = ReservationBook(), uuid4()

    def reserve() -> bool:
        try:
            book.reserve(account, uuid4(), Decimal("600"), Decimal("1000"))
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: reserve(), range(2))) == 1
