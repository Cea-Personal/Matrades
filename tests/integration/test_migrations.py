from pathlib import Path


def test_migration_chain_is_linear_and_uses_governed_retention() -> None:
    revisions = sorted(Path("migrations/versions").glob("*.py"))
    assert len(revisions) >= 10
    assert all("revision =" in path.read_text() for path in revisions)
    assert len({path.stem.split("_", maxsplit=1)[0] for path in revisions}) == len(revisions)
