"""Create read-only broker reconciliation and thesis-monitoring tables.

Revision ID: 0007_monitoring
Revises: 0006_opportunities
"""

from alembic import op

revision = "0007_monitoring"
down_revision = "0006_opportunities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.monitoring import position_model, thesis_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("trade monitoring evidence must be retained")
