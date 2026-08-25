from builtins import compile as compile_source
from decimal import Decimal

from modules.strategies.compiler import compile_strategy
from packages.strategy_sdk.taxonomy import StrategyOrigin
from tests.property.test_strategy_invariants import spec


def test_compiler_is_deterministic_and_handles_boundaries():
    artifact = compile_strategy(spec(StrategyOrigin.AI_ASSISTED))
    assert artifact == compile_strategy(spec(StrategyOrigin.AI_ASSISTED))
    assert artifact.evaluate({"close": Decimal("2")})
    assert not artifact.evaluate({"close": Decimal("1")})
    compile_source(artifact.generated_code, "generated_strategy.py", "exec")
    assert "never submits broker orders" in artifact.generated_code
