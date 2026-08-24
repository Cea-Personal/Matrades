from packages.strategy_sdk.schema import StrategySpecification


def boundary_cases(spec: StrategySpecification) -> list[dict]:
    return [
        {"rule": rule.model_dump(mode="json"), "case": "boundary"}
        for rule in spec.entry + spec.exit
    ]
