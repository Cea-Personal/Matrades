"""Runtime-bound agent profiles, prompts, tools, and execution audit."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_agent_runtime_type",
        "agent_model_profiles",
        "runtime_type IN ('CODEX_APP_SERVER','LITELLM_GATEWAY')",
    ) if False else None
    for name in (
        "agent_model_profiles",
        "agent_definitions",
        "agent_prompts",
        "agent_permission_sets",
        "agent_executions",
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("runtime_type", sa.String(32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.CheckConstraint(
                "runtime_type IN ('CODEX_APP_SERVER','LITELLM_GATEWAY')", name=f"ck_{name}_runtime"
            ),
        )


def downgrade():
    for name in reversed(
        (
            "agent_model_profiles",
            "agent_definitions",
            "agent_prompts",
            "agent_permission_sets",
            "agent_executions",
        )
    ):
        op.drop_table(name)
