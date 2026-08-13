"""Add password-recovery and assisted-MFA-reset evidence.

Revision ID: 0012_identity_recovery
Revises: 0011_identity_bootstrap
"""

from alembic import op

revision = "0012_identity_recovery"
down_revision = "0011_identity_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.identity import model as identity_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables["assisted_mfa_reset_requests"]],
    )


def downgrade() -> None:
    raise RuntimeError("identity recovery evidence must be retained")
