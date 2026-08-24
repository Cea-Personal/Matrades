from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from base64 import b32decode, b32encode
from datetime import timedelta

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from modules.identity.models import MfaEnrollment, Session, User
from packages.shared.domain_types import utc_now


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    key = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(password.encode())
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    _, salt, key = encoded.split("$")
    actual = Scrypt(salt=bytes.fromhex(salt), length=32, n=2**14, r=8, p=1).derive(
        password.encode()
    )
    return hmac.compare_digest(actual, bytes.fromhex(key))


def register(email: str, password: str) -> User:
    return User(email=email.lower().strip(), password_hash=hash_password(password))


def totp(secret: str, at: int | None = None) -> str:
    counter = (at or int(time.time())) // 30
    digest = hmac.new(b32decode(secret), counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF) % 1000000).zfill(6)


def enroll(user: User) -> tuple[MfaEnrollment, list[str]]:
    secret = b32encode(secrets.token_bytes(20)).decode()
    codes = [secrets.token_urlsafe(10) for _ in range(8)]
    return MfaEnrollment(
        user_id=user.id,
        encrypted_secret=secret,
        recovery_code_hashes=[hashlib.sha256(x.encode()).hexdigest() for x in codes],
    ), codes


def create_session(user: User, hours: int = 8) -> Session:
    if not user.email_verified or not user.mfa_enabled:
        raise PermissionError("verified email and MFA required")
    return Session(user_id=user.id, expires_at=utc_now() + timedelta(hours=hours))
