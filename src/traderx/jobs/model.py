from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from traderx.shared.db import Base, IdentifiedMixin
from traderx.shared.types import InvalidTransition


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_ALLOWED: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {JobState.PAUSED, JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
    JobState.PAUSED: {JobState.QUEUED, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: {JobState.QUEUED},
    JobState.CANCELLED: set(),
}


class BackgroundJob(IdentifiedMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(nullable=True)
    context: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    input_manifest: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=JobState.QUEUED, nullable=False)
    progress: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pause_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def transition(self, target: JobState) -> None:
        # SQLAlchemy column defaults are applied when a row is inserted, not when
        # an object is constructed. Treat an unsaved job as queued as well.
        current = JobState(self.state or JobState.QUEUED)
        if target not in _ALLOWED[current]:
            raise InvalidTransition(f"cannot transition job from {current} to {target}")
        self.state = target


class JobAttempt(IdentifiedMixin, Base):
    __tablename__ = "job_attempts"

    job_id: Mapped[UUID] = mapped_column(ForeignKey("background_jobs.id"), nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    fencing_token: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checkpoint: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
