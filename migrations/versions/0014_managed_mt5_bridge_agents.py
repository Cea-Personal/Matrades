"""Add managed outbound MT5 bridge enrollment evidence.

Revision ID: 0014_managed_mt5_bridge_agents
Revises: 0013_broker_account_truth
"""

from alembic import op

revision = "0014_managed_mt5_bridge_agents"
down_revision = "0013_broker_account_truth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from traderx.integrations import broker_model  # noqa: F401
    from traderx.shared.db import Base

    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["mt5_bridge_agents"]])


def downgrade() -> None:
    raise RuntimeError("MT5 bridge enrollment evidence must be retained")
