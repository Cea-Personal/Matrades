from __future__ import annotations

import secrets
from datetime import datetime

import pyotp

from traderx.shared.types import AuthorizationError


class TotpManager:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def at(self, secret: str, now: datetime) -> str:
        return pyotp.TOTP(secret, interval=30, digits=6).at(now)

    def provisioning_uri(self, secret: str, email: str) -> str:
        return pyotp.TOTP(secret, interval=30, digits=6).provisioning_uri(
            name=email, issuer_name="TraderX"
        )

    def verify(self, secret: str, code: str, now: datetime, last_used_step: int | None) -> int:
        totp = pyotp.TOTP(secret, interval=30, digits=6)
        if not totp.verify(code, for_time=now, valid_window=1):
            raise AuthorizationError("invalid multi-factor code")
        step = int(now.timestamp() // 30)
        if last_used_step is not None and step <= last_used_step:
            raise AuthorizationError("multi-factor code has already been used")
        return step

    def generate_recovery_codes(self, count: int = 8) -> list[str]:
        if count < 1:
            raise ValueError("at least one recovery code is required")
        return [secrets.token_urlsafe(8) for _ in range(count)]

    def redeem_recovery_code(self, supplied: str, remaining: set[str]) -> None:
        """Consumes an in-memory code set; persistence should store hashed codes."""
        if supplied not in remaining:
            raise AuthorizationError("invalid or used recovery code")
        remaining.remove(supplied)
