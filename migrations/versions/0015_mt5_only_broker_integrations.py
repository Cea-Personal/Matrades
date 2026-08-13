"""Decommission non-MT5 broker integrations without removing audit evidence.

Revision ID: 0015_mt5_only_broker_integrations
Revises: 0014_managed_mt5_bridge_agents
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_mt5_only_broker_integrations"
down_revision = "0014_managed_mt5_bridge_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE credential_versions SET active = false "
            "WHERE integration_id IN (SELECT id FROM integrations WHERE provider = 'OANDA_V20')"
        )
    )
    bind.execute(sa.text("UPDATE integrations SET state = 'DISABLED' WHERE provider = 'OANDA_V20'"))
    bind.execute(
        sa.text(
            "UPDATE trading_accounts SET status = 'BLOCKED' "
            "WHERE broker_integration_id IN (SELECT id FROM integrations WHERE provider = 'OANDA_V20')"
        )
    )


def downgrade() -> None:
    raise RuntimeError("decommissioned broker credentials and account evidence must remain fail-closed")
