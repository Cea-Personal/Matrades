from __future__ import annotations

from logging.config import fileConfig
from os import getenv
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from traderx.shared.db import Base, load_model_metadata

load_model_metadata()

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

def database_url_from_environment() -> str:
    """Inject the Docker-managed password without logging or exporting the secret."""
    raw_url = getenv("TRADERX_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    password_file = getenv("TRADERX_DATABASE_PASSWORD_FILE")
    if not password_file:
        return raw_url
    password = Path(password_file).read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("TRADERX_DATABASE_PASSWORD_FILE is empty")
    return make_url(raw_url).set(password=password).render_as_string(hide_password=False)


# Alembic stores this in ConfigParser, where percent signs denote interpolation.
# The database URL may contain percent-encoded secret characters, so escape them
# for the INI boundary; ConfigParser restores the original URL when it is read.
config.set_main_option("sqlalchemy.url", database_url_from_environment().replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
