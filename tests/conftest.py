from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest


@pytest.fixture
def frozen_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
def decimal_one() -> Decimal:
    return Decimal("1")
