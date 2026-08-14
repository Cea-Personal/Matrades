"""Add durable pseudonymous authentication throttles.

Revision ID: 0022_authentication_throttles
Revises: 0021_integration_configuration
"""

from alembic import op

revision = "0022_authentication_throttles"
down_revision = "0021_integration_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.identity import model as identity_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.tables["authentication_throttles"].create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("authentication-abuse evidence must be retained")
