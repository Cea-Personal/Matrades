from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin


class ApprovalDecision(StrEnum):
    APPROVE_LIVE = "APPROVE_LIVE"
    REJECT = "REJECT"
    RETURN_TO_RESEARCH = "RETURN_TO_RESEARCH"


class StrategyApproval(IdentifiedMixin, Base):
    __tablename__ = "strategy_approvals"
    strategy_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategy_versions.id"), nullable=False
    )
    paper_run_id: Mapped[UUID] = mapped_column(ForeignKey("paper_runs.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    assurance_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
