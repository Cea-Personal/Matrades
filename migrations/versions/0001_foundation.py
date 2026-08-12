"""Create shared foundation tables.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-12
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.audit.model import AuditEvent  # noqa: F401
    from traderx.jobs.model import BackgroundJob, JobAttempt  # noqa: F401
    from traderx.shared.db import Base
    from traderx.shared.events import ConsumerReceipt, OutboxEvent  # noqa: F401
    from traderx.shared.idempotency import IdempotencyRecord  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[
            Base.metadata.tables[name]
            for name in [
                "audit_events",
                "background_jobs",
                "job_attempts",
                "consumer_receipts",
                "outbox_events",
                "idempotency_records",
            ]
        ],
    )


def downgrade() -> None:
    from traderx.shared.db import Base

    bind = op.get_bind()
    for name in [
        "idempotency_records",
        "outbox_events",
        "consumer_receipts",
        "job_attempts",
        "background_jobs",
        "audit_events",
    ]:
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
