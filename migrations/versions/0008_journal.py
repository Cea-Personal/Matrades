"""Create durable journal and research-proposal evidence.

Revision ID: 0008_journal
Revises: 0007_monitoring
"""

from alembic import op

revision = "0008_journal"
down_revision = "0007_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.journal import model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("journal evidence must be retained")
