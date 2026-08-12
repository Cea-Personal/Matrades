import pytest

from traderx.shared.idempotency import IdempotencyConflict, canonical_request_hash, start_or_replay


def test_idempotency_hash_is_stable_and_conflicting_replay_is_rejected() -> None:
    assert canonical_request_hash({"a": 1}) == canonical_request_hash({"a": 1})
    with pytest.raises(IdempotencyConflict):
        start_or_replay(
            type("Record", (), {"request_hash": "different", "state": "COMPLETED"})(),
            canonical_request_hash({"a": 1}),
        )
