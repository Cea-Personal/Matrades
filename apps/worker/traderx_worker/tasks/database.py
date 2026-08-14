from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from traderx.shared.config import get_settings
from traderx.shared.db import load_model_metadata


def session_factory() -> sessionmaker[Session]:
    load_model_metadata()
    engine = create_engine(get_settings().database_url.unicode_string(), pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)
