from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from pwdlib import PasswordHash

from traderx.shared.types import AuthorizationError

_PASSWORD_HASH = PasswordHash.recommended()


@dataclass(slots=True)
class SessionView:
    token_digest: str
    assurance: str
    issued_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class SessionManager:
    def __init__(
        self,
        pepper: str,
        *,
        idle: timedelta = timedelta(minutes=30),
        absolute: timedelta = timedelta(hours=12),
    ) -> None:
        self._pepper = pepper
        self._idle = idle
        self._absolute = absolute

    def digest(self, token: str) -> str:
        return hashlib.sha256(f"{self._pepper}:{token}".encode()).hexdigest()

    def issue(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        return token, self.digest(token)

    def verify(self, token: str, digest: str) -> bool:
        return secrets.compare_digest(self.digest(token), digest)

    def new_session(self, now: datetime, *, assurance: str) -> SessionView:
        _, digest = self.issue()
        return SessionView(digest, assurance, now, now, now + self._absolute)

    def rotate(
        self, session: SessionView, now: datetime, *, assurance: str | None = None
    ) -> tuple[str, SessionView]:
        """Revoke a session and issue a replacement with a fresh opaque token."""
        if not self.is_active(session, now):
            raise AuthorizationError("session is no longer active")
        session.revoked_at = now
        token, digest = self.issue()
        replacement = SessionView(
            digest,
            assurance or session.assurance,
            now,
            now,
            now + self._absolute,
        )
        return token, replacement

    def revoke(self, session: SessionView, now: datetime) -> None:
        session.revoked_at = now

    def csrf_token(self, session: SessionView) -> str:
        return hmac.new(
            self._pepper.encode(), f"csrf:{session.token_digest}".encode(), hashlib.sha256
        ).hexdigest()

    def verify_csrf(self, session: SessionView, token: str) -> bool:
        return secrets.compare_digest(self.csrf_token(session), token)

    def is_active(self, session: SessionView, now: datetime) -> bool:
        return (
            session.revoked_at is None
            and now <= session.expires_at
            and now - session.last_seen_at <= self._idle
        )

    def has_recent_assurance(
        self, session: SessionView, now: datetime, maximum_age: timedelta
    ) -> bool:
        return (
            self.is_active(session, now)
            and session.assurance == "MFA"
            and now - session.issued_at <= maximum_age
        )


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise AuthorizationError("password must contain at least twelve characters")
    return _PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _PASSWORD_HASH.verify(password, password_hash)


@dataclass(slots=True)
class RecoveryChallengeView:
    token_digest: str
    expires_at: datetime
    consumed_at: datetime | None = None


class PasswordRecoveryManager:
    def __init__(self, pepper: str, *, lifetime: timedelta = timedelta(minutes=15)) -> None:
        self._sessions = SessionManager(pepper)
        self._lifetime = lifetime

    def issue(self, now: datetime) -> tuple[str, RecoveryChallengeView]:
        token, digest = self._sessions.issue()
        return token, RecoveryChallengeView(digest, now + self._lifetime)

    def consume(self, challenge: RecoveryChallengeView, token: str, now: datetime) -> None:
        if challenge.consumed_at is not None or now > challenge.expires_at:
            raise AuthorizationError("password recovery challenge is unavailable")
        if not self._sessions.verify(token, challenge.token_digest):
            raise AuthorizationError("invalid password recovery challenge")
        challenge.consumed_at = now
