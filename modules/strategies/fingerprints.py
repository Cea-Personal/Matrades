import hashlib
import json

from packages.strategy_sdk.schema import StrategySpecification


def fingerprint(spec: StrategySpecification) -> str:
    body = spec.model_dump(mode="json", exclude={"name", "origin"})
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
