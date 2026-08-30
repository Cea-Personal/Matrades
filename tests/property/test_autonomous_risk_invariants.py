from decimal import Decimal

from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_tighter_equity_capacity_never_increases_approved_size():
    engine = RiskEngine()
    broad = engine.evaluate(context(), candidate("5"))
    account = context().account.model_copy(
        update={
            "current_equity": Decimal("185000"),
            "current_balance": Decimal("186000"),
            "floating_pnl": Decimal("-1000"),
        }
    )
    tight = engine.evaluate(context(account=account), candidate("5"))
    assert tight.approved_size <= broad.approved_size
