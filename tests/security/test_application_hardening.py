from datetime import UTC, datetime

from traderx.identity.authentication import SessionManager


def test_session_csrf_tokens_are_session_bound() -> None:
    manager = SessionManager("pepper")
    first = manager.new_session(datetime(2026, 8, 12, tzinfo=UTC), assurance="MFA")
    second = manager.new_session(datetime(2026, 8, 12, tzinfo=UTC), assurance="MFA")
    assert manager.verify_csrf(first, manager.csrf_token(first))
    assert not manager.verify_csrf(first, manager.csrf_token(second))
