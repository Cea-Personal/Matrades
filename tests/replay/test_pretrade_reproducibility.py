from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_identical_versions_reproduce_identical_results() -> None:
    engine, ctx, trade = RiskEngine(), context(), candidate("4")
    assert engine.evaluate(ctx, trade).model_dump() == engine.evaluate(ctx, trade).model_dump()
