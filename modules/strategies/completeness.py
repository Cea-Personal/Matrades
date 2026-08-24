from packages.strategy_sdk.schema import StrategySpecification


def check(specification: StrategySpecification | None) -> list[str]:
    if specification is None:
        return ["canonical specification is missing"]
    issues = []
    if not specification.entry:
        issues.append("entry rules missing")
    if not specification.exit:
        issues.append("exit rules missing")
    if specification.stop_loss is None:
        issues.append("bounded stop loss missing")
    return issues
