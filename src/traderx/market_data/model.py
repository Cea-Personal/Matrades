from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, FinancialDecimal, IdentifiedMixin
from traderx.shared.types import DataQuality


class InstrumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    QUARANTINED = "QUARANTINED"


class Instrument(IdentifiedMixin, Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=InstrumentStatus.INACTIVE, nullable=False
    )
    contract_spec: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    trading_hours: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class InstrumentAlias(IdentifiedMixin, Base):
    __tablename__ = "instrument_aliases"
    __table_args__ = (UniqueConstraint("provider", "native_symbol", name="uq_instrument_alias"),)

    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    native_symbol: Mapped[str] = mapped_column(String(256), nullable=False)
    integration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integrations.id"), nullable=True
    )
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mapping_revision: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    contract_variant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataSetManifest(IdentifiedMixin, Base):
    __tablename__ = "dataset_manifests"

    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    integration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integrations.id"), nullable=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(256), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False, default="CANDLES")
    semantics: Mapped[str] = mapped_column(String(24), nullable=False, default="UNAVAILABLE")
    source_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SPECIALIST_PRIMARY"
    )
    catalogue_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapter_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mapping_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freshness_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entitlement_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="UNVERIFIED"
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    parquet_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    source_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    complete: Mapped[bool] = mapped_column(nullable=False, default=False)
    quality: Mapped[str] = mapped_column(String(24), nullable=False, default=DataQuality.UNKNOWN)
    conflict_state: Mapped[str] = mapped_column(String(24), nullable=False, default="UNCHECKED")
    fallback_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    raw_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketObservation(IdentifiedMixin, Base):
    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "provider",
            "capability",
            "observed_at",
            "revision",
            name="uq_market_observation",
        ),
    )

    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    integration_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integrations.id"), nullable=True
    )
    dataset_manifest_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("dataset_manifests.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(120), nullable=False, default="UNKNOWN")
    provider_symbol: Mapped[str | None] = mapped_column(String(256), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False, default="CANDLES")
    semantics: Mapped[str] = mapped_column(String(24), nullable=False, default="UNAVAILABLE")
    source_role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SPECIALIST_PRIMARY"
    )
    mapping_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freshness_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    # Metric-only provider observations (volume, open interest, depth) have no OHLC
    # values. Null preserves that distinction instead of manufacturing zero prices.
    open: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    high: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    low: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    close: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    volume: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    spread: Mapped[object | None] = mapped_column(FinancialDecimal, nullable=True)
    measures: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    complete: Mapped[bool] = mapped_column(nullable=False, default=True)
    conflict_state: Mapped[str] = mapped_column(String(24), nullable=False, default="CLEAR")
    raw_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    quality: Mapped[str] = mapped_column(String(16), default=DataQuality.UNKNOWN, nullable=False)


class EconomicEvent(IdentifiedMixin, Base):
    __tablename__ = "economic_events"
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency_or_region: Mapped[str] = mapped_column(String(32), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class DataQualityObservation(IdentifiedMixin, Base):
    __tablename__ = "data_quality_observations"
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
