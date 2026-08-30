from types import SimpleNamespace
from uuid import uuid4

from apps.api.app.routes.research_matrix import (
    _account_matrix_history,
    _next_account_matrix_version,
)


def _matrix(account_id, version):
    return SimpleNamespace(data={"account_id": str(account_id), "version": version})


def test_matrix_versions_are_independent_per_account() -> None:
    first = uuid4()
    second = uuid4()
    records = [
        _matrix(first, 1),
        _matrix(second, 1),
        _matrix(first, 2),
        _matrix(second, 2),
        _matrix(second, 3),
    ]

    assert [item.data["version"] for item in _account_matrix_history(records, first)] == [2, 1]
    assert [item.data["version"] for item in _account_matrix_history(records, second)] == [3, 2, 1]
    assert _next_account_matrix_version(records, first) == 3
    assert _next_account_matrix_version(records, second) == 4
    assert _next_account_matrix_version(records, uuid4()) == 1
