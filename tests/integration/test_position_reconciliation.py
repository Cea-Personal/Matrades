from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from modules.risk.engine import RiskEngine
from modules.trading.broker_models import ReconciliationState
from modules.trading.models import TradeProposal
from modules.trading.reconciliation import reconcile
from packages.broker_sdk.schemas import BrokerPosition
from tests.fixtures.pretrade import candidate, context


def test_exact_ambiguous_and_no_match():
    proposal = TradeProposal(
        owner_id=uuid4(),
        account_id=uuid4(),
        instrument="EURUSD",
        direction="BUY",
        entry=Decimal("1.1"),
        stop_loss=Decimal("1"),
        targets=[Decimal("1.2")],
        invalidation="x",
        approved_size=Decimal("1"),
        risk=RiskEngine().evaluate(context(), candidate()),
        critic_result="ok",
    )

    def pos(key):
        return BrokerPosition(
            position_id=key,
            account_id=proposal.account_id,
            symbol="EURUSD",
            direction="BUY",
            volume=Decimal("1"),
            entry_price=Decimal("1.1"),
            pnl=Decimal("0"),
            opened_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
        )

    assert reconcile(proposal, [pos("1")]).state == ReconciliationState.MATCHED
    assert reconcile(proposal, [pos("1"), pos("2")]).state == ReconciliationState.AMBIGUOUS
    assert reconcile(proposal, []).state == ReconciliationState.NOT_FOUND
