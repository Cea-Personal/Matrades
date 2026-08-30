"""Pre-trade account, policy, risk reservation, proposal, and approval records."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older development builds created the durable reservation ledger from ORM
    # metadata before Alembic was introduced.  Preserve that data and let this
    # migration establish the remaining pre-trade tables.
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    if "risk_reservations" not in existing_tables:
        op.create_table(
            "risk_reservations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("proposal_id", sa.Uuid(), nullable=False, unique=True),
            sa.Column("amount", sa.Numeric(24, 8), nullable=False),
            sa.Column("state", sa.String(24), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
    op.create_table(
        "trade_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("account_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("trade_proposals.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    for table in (
        "approval_decisions",
        "trade_proposals",
        "risk_reservations",
        "account_snapshots",
    ):
        op.drop_table(table)
