"""Add governed instrument-knowledge retention indexes.

Revision ID: 0009_instrument_retention
Revises: 0008_journal
"""

from alembic import op

revision = "0009_instrument_retention"
down_revision = "0008_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All prior instrument references intentionally use restrictive foreign keys;
    # this index supports effective-history lookup without deletion.
    op.create_index(
        "ix_active_assignments_effective_history",
        "active_market_assignments",
        ["category", "effective_from"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_active_assignments_effective_history",
        table_name="active_market_assignments",
        if_exists=True,
    )
