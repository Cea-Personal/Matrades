from datetime import UTC, datetime, timedelta

import pytest

from traderx.identity.authentication import SessionManager
from traderx.identity.mfa import TotpManager
from traderx.shared.types import AuthorizationError


def test_session_token_is_not_stored_as_plaintext() -> None:
    manager = SessionManager("pepper")
    token, digest = manager.issue()
    assert token != digest
    assert manager.verify(token, digest)


def test_session_expiry_and_recent_assurance() -> None:
    manager = SessionManager("pepper")
    now = datetime(2026, 8, 12, tzinfo=UTC)
    session = manager.new_session(now, assurance="MFA")
    assert manager.is_active(session, now + timedelta(minutes=4))
    assert manager.has_recent_assurance(session, now + timedelta(minutes=4), timedelta(minutes=5))
    assert not manager.has_recent_assurance(
        session, now + timedelta(minutes=6), timedelta(minutes=5)
    )


def test_totp_step_cannot_be_reused() -> None:
    manager = TotpManager()
    secret = manager.new_secret()
    when = datetime(2026, 8, 12, tzinfo=UTC)
    code = manager.at(secret, when)
    accepted_step = manager.verify(secret, code, when, None)
    with pytest.raises(AuthorizationError):
        manager.verify(secret, code, when, accepted_step)
