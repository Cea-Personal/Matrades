"""Identity, encrypted credential references, connections and policies."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    for name in (
        "users",
        "sessions",
        "mfa_enrollments",
        "credential_versions",
        "provider_connections",
        "prop_firms",
        "prop_programs",
        "prop_rulesets",
        "guardrail_profiles",
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), nullable=False, index=True),
            sa.Column(
                "payload",
                sa.LargeBinary() if name == "credential_versions" else sa.JSON(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade():
    for name in reversed(
        (
            "users",
            "sessions",
            "mfa_enrollments",
            "credential_versions",
            "provider_connections",
            "prop_firms",
            "prop_programs",
            "prop_rulesets",
            "guardrail_profiles",
        )
    ):
        op.drop_table(name)
