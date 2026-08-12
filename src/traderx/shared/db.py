from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
