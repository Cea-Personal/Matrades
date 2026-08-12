"""Create integration, notification, and strategy-health operations tables.

Revision ID: 0010_operations
Revises: 0009_instrument_retention
"""

from alembic import op

revision = "0010_operations"
down_revision = "0009_instrument_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.integrations import model as integrations_model  # noqa: F401
    from traderx.notifications import model as notifications_model  # noqa: F401
    from traderx.shared.db import Base
    from traderx.strategies import health_model  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError("operations evidence must be retained")
