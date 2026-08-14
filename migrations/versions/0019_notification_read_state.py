"""Add durable notification read state.

Revision ID: 0019_notification_read_state
Revises: 0018_position_matching
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_notification_read_state"
down_revision = "0018_position_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("routed_notifications")
    }
    if "read_at" not in columns:
        op.add_column(
            "routed_notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    raise RuntimeError("notification read evidence must be retained")
