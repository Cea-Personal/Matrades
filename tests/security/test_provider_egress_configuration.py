from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    REPOSITORY_ROOT / "deploy" / "compose.yaml",
    REPOSITORY_ROOT / "deploy" / "compose.production.yaml",
)


@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda path: path.name)
def test_only_research_worker_has_reviewed_provider_egress(compose_file: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose is required to validate deployment networking")

    result = subprocess.run(  # noqa: S603
        [docker, "compose", "-f", str(compose_file), "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    configuration = json.loads(result.stdout)
    services = configuration["services"]
    networks = configuration["networks"]

    assert set(services["worker-research"]["networks"]) == {"private", "provider-egress"}
    assert networks["private"]["internal"] is True
    assert networks["provider-egress"].get("internal", False) is False

    for service in (
        "api",
        "migrate",
        "postgres",
        "redis",
        "scheduler",
        "web",
        "worker-monitoring",
        "worker-notifications",
    ):
        assert "provider-egress" not in services[service]["networks"]
