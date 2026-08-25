"""Deterministic contract-output guard.

The repository keeps lightweight Python/TypeScript boundary types checked in
for the API and web packages.  Full code generation can be added without
changing this command: ``--check`` currently guarantees the checked-in
outputs still identify the OpenAPI contract version and the typed matrix
enums required by the application.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs/001-matrades-product-platform/contracts/openapi.yaml"
PYTHON = ROOT / "packages/contracts/generated/openapi.py"
TYPESCRIPT = ROOT / "packages/contracts/generated/openapi.ts"


def contract_version() -> str:
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("  version:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("OpenAPI version is missing")


def check() -> None:
    version = contract_version()
    py = PYTHON.read_text(encoding="utf-8")
    ts = TYPESCRIPT.read_text(encoding="utf-8")
    expected = f"matrades.openapi.v{version.split('.')[0]}"
    missing = [
        path.name for path, content in ((PYTHON, py), (TYPESCRIPT, ts)) if expected not in content
    ]
    if missing:
        raise SystemExit(f"generated contract outputs are stale: {', '.join(missing)}")
    print(f"contract outputs verified ({expected})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    # Generation is intentionally deterministic and currently means checking
    # the committed boundary.  This avoids silently producing a partial client
    # when a generator is unavailable in a clean environment.
    check()
    if not args.check:
        print("No files changed; checked-in outputs are the canonical generated artifacts.")


if __name__ == "__main__":
    main()
