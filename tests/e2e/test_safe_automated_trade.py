from modules.risk.engine import RiskEngine
from modules.risk.models import RiskDecision
from tests.fixtures.pretrade import candidate, context


def test_safe_trade_has_explicit_pass_and_hard_block_paths() -> None:
    engine = RiskEngine()
    assert engine.evaluate(context(), candidate()).decision is RiskDecision.PASS
    blocked = engine.evaluate(context(static_max_concurrent_trades=0), candidate())
    assert blocked.decision is RiskDecision.HARD_BLOCK
