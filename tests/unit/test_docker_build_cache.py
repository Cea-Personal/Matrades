from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from infra.docker.install_dependencies import install_dependencies

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILES = (
    "apps/api/Dockerfile",
    "apps/worker/Dockerfile",
    "apps/agent_worker/Dockerfile",
)


def test_dependency_install_uses_project_metadata_without_installing_source() -> None:
    project_file = ROOT / "pyproject.toml"
    with project_file.open("rb") as handle:
        project = tomllib.load(handle)
    with patch("infra.docker.install_dependencies.subprocess.run") as run:
        install_dependencies(project_file)
    run.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            *project["build-system"]["requires"],
            *project["project"]["dependencies"],
        ],
        check=True,
    )


def test_failed_dependency_install_fails_the_build() -> None:
    failure = subprocess.CalledProcessError(1, ["pip", "install"])
    with (
        patch("infra.docker.install_dependencies.subprocess.run", side_effect=failure),
        pytest.raises(subprocess.CalledProcessError),
    ):
        install_dependencies(ROOT / "pyproject.toml")


@pytest.mark.parametrize("relative_path", BACKEND_DOCKERFILES)
def test_source_edits_do_not_invalidate_dependency_layer(relative_path: str) -> None:
    dockerfile = (ROOT / relative_path).read_text()
    source_copy = dockerfile.index("COPY . .")
    dependency_install = dockerfile.index("python /tmp/install_dependencies.py")
    assert dockerfile.index("COPY pyproject.toml ./") < dependency_install < source_copy
    assert "target=/root/.cache/pip,sharing=locked" in dockerfile[:source_copy]
    assert "pip install --no-deps --no-build-isolation ." in dockerfile[source_copy:]
    assert "--no-cache-dir" not in dockerfile


def test_all_backend_images_share_the_same_dependency_build_prefix() -> None:
    prefixes = {
        (ROOT / relative_path).read_text().split("python /tmp/install_dependencies.py")[0]
        for relative_path in BACKEND_DOCKERFILES
    }
    assert len(prefixes) == 1


def test_compose_shares_backend_image_without_changing_service_roles() -> None:
    services = yaml.safe_load((ROOT / "infra/compose/compose.yaml").read_text())["services"]
    backend = services["api"]
    for name in ("worker", "scheduler", "mt5-bridge"):
        assert services[name]["image"] == backend["image"] == "matrades-backend:local"
        assert services[name]["build"] == backend["build"]
    assert services["worker"]["command"] == [
        "celery",
        "-A",
        "apps.worker.app.celery_app:celery_app",
        "worker",
        "--loglevel=INFO",
    ]
    assert "beat" in services["scheduler"]["command"]
    assert "bridges.mt5.app:app" in services["mt5-bridge"]["command"]
    assert "command" not in backend
    assert services["agent-worker"]["build"]["dockerfile"] == "apps/agent_worker/Dockerfile"


def test_agent_auth_stays_runtime_only_and_native_agent_configs_ship() -> None:
    dockerfile = (ROOT / "apps/agent_worker/Dockerfile").read_text()
    excluded = (ROOT / ".dockerignore").read_text().splitlines()
    assert "$AUTH_JSON" not in dockerfile
    assert ".codex/auth.json" in excluded
    assert ".codex/" not in excluded
    assert ".codex/agents/" not in excluded
    services = yaml.safe_load((ROOT / "infra/compose/compose.yaml").read_text())["services"]
    assert "${HOME}/.codex/auth.json:/root/.codex/auth.json" in services["agent-worker"]["volumes"]
