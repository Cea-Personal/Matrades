"""Complete paper evaluation evidence fields.

Revision ID: 0017_paper_workflows
Revises: 0016_strategy_workflows
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_paper_workflows"
down_revision = "0016_strategy_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    run_columns = {column["name"] for column in inspector.get_columns("paper_runs")}
    if "validation_run_id" not in run_columns:
        op.add_column("paper_runs", sa.Column("validation_run_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_paper_runs_validation_run_id_validation_runs",
            "paper_runs",
            "validation_runs",
            ["validation_run_id"],
            ["id"],
        )
    if "criteria" not in run_columns:
        op.add_column(
            "paper_runs", sa.Column("criteria", sa.JSON(), nullable=False, server_default="{}")
        )
    trade_columns = {column["name"] for column in inspector.get_columns("paper_trade_references")}
    for name, type_ in (
        ("stop", sa.Numeric(38, 18)),
        ("target", sa.Numeric(38, 18)),
        ("direction", sa.String(8)),
        ("pnl", sa.Numeric(38, 18)),
    ):
        if name not in trade_columns:
            op.add_column("paper_trade_references", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    raise RuntimeError("paper evidence fields must be retained")
