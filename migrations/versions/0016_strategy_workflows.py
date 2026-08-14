"""Separate immutable strategy sequence from optimistic row versions.

Revision ID: 0016_strategy_workflows
Revises: 0015_mt5_only_integrations
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_strategy_workflows"
down_revision = "0015_mt5_only_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    strategy_columns = {column["name"] for column in inspector.get_columns("strategies")}
    if "owner_id" not in strategy_columns:
        op.add_column("strategies", sa.Column("owner_id", sa.Uuid(), nullable=True))
    version_columns = {column["name"] for column in inspector.get_columns("strategy_versions")}
    sequence_added = "sequence" not in version_columns
    if sequence_added:
        op.add_column("strategy_versions", sa.Column("sequence", sa.Integer(), nullable=True))
        bind.execute(sa.text("UPDATE strategy_versions SET sequence = version"))
    if "change_summary" not in version_columns:
        op.add_column(
            "strategy_versions",
            sa.Column(
                "change_summary",
                sa.String(length=2000),
                nullable=False,
                server_default="Initial draft",
            ),
        )
    if "author_id" not in version_columns:
        op.add_column("strategy_versions", sa.Column("author_id", sa.Uuid(), nullable=True))
    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("strategy_versions")
    }
    existing = unique_constraints.get("uq_strategy_version")
    with op.batch_alter_table("strategy_versions") as batch:
        if sequence_added:
            batch.alter_column("sequence", existing_type=sa.Integer(), nullable=False)
        if existing and existing != ("strategy_id", "sequence"):
            batch.drop_constraint("uq_strategy_version", type_="unique")
        if existing != ("strategy_id", "sequence"):
            batch.create_unique_constraint("uq_strategy_version", ["strategy_id", "sequence"])


def downgrade() -> None:
    raise RuntimeError("immutable strategy version history cannot be removed safely")
