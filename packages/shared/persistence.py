from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def validate_executable_reference(data: dict[str, Any]) -> None:
    """Reject actionable typed records that do not pin market authority.

    Untyped historical records remain readable for compatibility. Once a
    write declares an instrument type, it must carry an exact venue listing
    and effective specification; futures additionally require a dated
    contract.
    """
    instrument_type = data.get("instrument_type")
    if instrument_type is None:
        return
    required = ("venue_instrument_id", "specification_version_id", "quantity_unit")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(f"typed executable reference missing: {', '.join(missing)}")
    if str(instrument_type) == "FUTURES" and not data.get("futures_contract_id"):
        raise ValueError("futures executable reference requires a dated futures contract")


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class EntityMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    record_type: Mapped[str] = mapped_column(String(80), nullable=False)
