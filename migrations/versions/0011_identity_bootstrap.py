"""Add the singleton guard for first-owner enrollment.

Revision ID: 0011_identity_bootstrap
Revises: 0010_operations
"""

from alembic import op

revision = "0011_identity_bootstrap"
down_revision = "0010_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.identity.model import BootstrapState  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(
        bind=op.get_bind(), tables=[Base.metadata.tables["identity_bootstrap_state"]]
    )


def downgrade() -> None:
    raise RuntimeError("identity bootstrap evidence must be retained")
