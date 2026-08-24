from decimal import Decimal

from modules.policy.models import ConstraintKind
from modules.risk.engine import RiskEngine
from modules.risk.models import RiskDecision
from tests.fixtures.pretrade import candidate, context


def test_risk_decision_contracts() -> None:
    engine = RiskEngine()
    assert engine.evaluate(context(), candidate("1")).decision == RiskDecision.PASS
    assert engine.evaluate(context(), candidate("10")).decision == RiskDecision.REDUCE_SIZE
    blocked = context(
        constraints=[
            item.model_copy(update={"value": Decimal("0")})
            if item.kind == ConstraintKind.MAX_PORTFOLIO_RISK
            else item
            for item in context().constraints
        ]
    )
    assert engine.evaluate(blocked, candidate()).decision == RiskDecision.HARD_BLOCK
