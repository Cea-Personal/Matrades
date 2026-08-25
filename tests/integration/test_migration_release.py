import ast
from pathlib import Path


def test_migration_chain_and_reversibility():
    paths = sorted(Path("infra/migrations/versions").glob("*.py"))
    assert [x.name[:4] for x in paths] == [f"{x:04d}" for x in range(1, 12)]
    for path in paths:
        tree = ast.parse(path.read_text())
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {"upgrade", "downgrade"} <= functions
    first = paths[0].read_text()
    assert "timescaledb" in first and "vector" in first
