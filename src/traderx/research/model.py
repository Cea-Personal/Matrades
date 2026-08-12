from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class ResearchJobDetail(IdentifiedMixin, Base):
    __tablename__ = "research_job_details"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("background_jobs.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    input_manifest: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    result_summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchExperiment(IdentifiedMixin, Base):
    __tablename__ = "research_experiments"
    research_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_job_details.id"), nullable=False
    )
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
