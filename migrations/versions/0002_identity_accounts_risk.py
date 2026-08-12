"""Create identity, account, and risk tables.

Revision ID: 0002_identity_accounts_risk
Revises: 0001_foundation
Create Date: 2026-08-12
"""

from alembic import op

revision = "0002_identity_accounts_risk"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.accounts import model as accounts_model  # noqa: F401
    from traderx.identity import model as identity_model  # noqa: F401
    from traderx.risk import model as risk_model  # noqa: F401
    from traderx.shared.db import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Governed evidence is intentionally not dropped by routine downgrade.
    raise RuntimeError("governed TraderX evidence requires an explicit retention migration")
