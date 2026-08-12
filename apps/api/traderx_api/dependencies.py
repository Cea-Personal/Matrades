from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from traderx.shared.config import get_settings


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine = create_engine(settings.database_url.unicode_string(), pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_database_session() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
