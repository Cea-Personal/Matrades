from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from traderx.shared.config import get_settings
from traderx.shared.db import load_model_metadata


@lru_cache(maxsize=1)
def session_factory() -> sessionmaker[Session]:
    """One bounded pool per worker process, not one engine per task invocation."""

    load_model_metadata()
    engine = create_engine(
        get_settings().database_url.unicode_string(),
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=0,
        pool_timeout=30,
    )
    return sessionmaker(bind=engine, expire_on_commit=False)
