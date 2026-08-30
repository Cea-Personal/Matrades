from pathlib import Path

import yaml

from packages.contracts.generated import openapi


def test_openapi_contains_autonomous_routes_and_generated_version() -> None:
    document = yaml.safe_load(
        Path("specs/001-matrades-product-platform/contracts/openapi.yaml").read_text()
    )
    paths = document["paths"]
    assert "/automation/operations" in paths
    assert "/trade-plans" in paths
    assert openapi.CONTRACT_VERSION == "matrades.openapi.v2"
