from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.getenv("TRADERX_TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


@pytest.fixture(scope="session")
def redis_url() -> str:
    return os.getenv("TRADERX_TEST_REDIS_URL", "redis://localhost:6379/15")
