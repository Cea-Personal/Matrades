"""Install backend dependencies without copying or building application source."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def install_dependencies(project_file: Path) -> None:
    with project_file.open("rb") as handle:
        project = tomllib.load(handle)
    requirements = [
        *project["build-system"]["requires"],
        *project["project"]["dependencies"],
    ]
    subprocess.run(  # noqa: S603 - invoke pip with project-owned dependency declarations.
        [sys.executable, "-m", "pip", "install", *requirements],
        check=True,
    )


if __name__ == "__main__":
    install_dependencies(Path("pyproject.toml"))
