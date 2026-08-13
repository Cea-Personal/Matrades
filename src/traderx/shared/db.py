from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from importlib import import_module
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, MetaData, Numeric, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def load_model_metadata() -> None:
    """Register every model before schema creation or Alembic metadata inspection."""

    for module_name in (
        "traderx.identity.model",
        "traderx.accounts.model",
        "traderx.risk.model",
        "traderx.integrations.model",
        "traderx.integrations.broker_model",
        "traderx.jobs.model",
        "traderx.market_data.model",
        "traderx.market_research.model",
        "traderx.research.model",
        "traderx.strategies.model",
        "traderx.strategies.approval_model",
        "traderx.strategies.health_model",
        "traderx.validation.model",
        "traderx.paper.model",
        "traderx.opportunities.model",
        "traderx.opportunities.recommendation_model",
        "traderx.monitoring.position_model",
        "traderx.monitoring.thesis_model",
        "traderx.journal.model",
        "traderx.notifications.model",
        "traderx.audit.model",
    ):
        import_module(module_name)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VersionedMixin(CreatedAtMixin):
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__: dict[str, Any] = {"version_id_col": version}


class IdentifiedMixin(VersionedMixin):
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


FinancialDecimal = Numeric(38, 18, asdecimal=True)
PercentDecimal = Numeric(18, 10, asdecimal=True)


def numeric(value: Decimal | str | int) -> Decimal:
    from traderx.shared.types import as_decimal

    return as_decimal(value)
