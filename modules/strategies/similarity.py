from modules.strategies.fingerprints import fingerprint
from packages.strategy_sdk.schema import StrategySpecification


def compare(left: StrategySpecification, right: StrategySpecification) -> dict[str, float | bool]:
    exact = fingerprint(left) == fingerprint(right)
    left_rules = {str(x) for x in left.entry + left.exit}
    right_rules = {str(x) for x in right.entry + right.exit}
    union = left_rules | right_rules
    return {
        "exact": exact,
        "structural": len(left_rules & right_rules) / len(union) if union else 1.0,
        "parameter": 1.0 if left.parameters == right.parameters else 0.5,
    }
