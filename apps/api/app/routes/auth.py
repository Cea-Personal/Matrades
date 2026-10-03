from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import UTC, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db
from modules.identity.email_delivery import AuthEmailUnavailable, deliver_auth_link, delivery_mode
from modules.identity.models import User
from modules.identity.persistence import (
    AuthTokenRecord,
    SessionRecord,
    SignupGateRecord,
    UserRecord,
)
from modules.identity.service import enroll, hash_password, totp, verify_password
from modules.mt5.desktop_runtime import MT5StartupError, ensure_mt5_started
from packages.shared.config import get_settings
from packages.shared.domain_types import utc_now
from packages.shared.store import ResourceStore

router = APIRouter(prefix="/auth", tags=["Authentication"])
SESSION_COOKIE = "matrades_session"
logger = logging.getLogger(__name__)


class SignupRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=12, max_length=256)


class TokenRequest(BaseModel):
    token: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChallengeRequest(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=6, max_length=64)


class EnrollmentConfirmRequest(BaseModel):
    enrollment_id: UUID
    code: str = Field(min_length=6, max_length=6)


class StepUpRequest(BaseModel):
    action_scope: str
    code: str = Field(min_length=6, max_length=64)


class RecoveryStartRequest(BaseModel):
    email: str = Field(max_length=320)


class ResendVerificationRequest(BaseModel):
    email: str = Field(max_length=320)


class RecoveryCompleteRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=256)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _normalized_email(value: str) -> str:
    email = value.lower().strip()
    if (
        len(email) > 320
        or email.count("@") != 1
        or any(character.isspace() or ord(character) < 32 for character in email)
        or "." not in email.split("@", 1)[1]
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "valid email required")
    return email


def _require_email_delivery() -> str:
    try:
        return delivery_mode()
    except AuthEmailUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "authentication email is unavailable"
        ) from exc


async def _signup_available(db: AsyncSession) -> bool:
    if await db.scalar(select(UserRecord.id).limit(1)) is not None:
        return False
    return await db.get(SignupGateRecord, 1) is None


def _cipher_key() -> bytes:
    secret = get_settings().secret_key.get_secret_value().encode()
    return hashlib.sha256(secret).digest()


def _encrypt(value: str, associated: UUID) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_cipher_key()).encrypt(nonce, value.encode(), str(associated).encode())
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def _decrypt(value: str, associated: UUID) -> str:
    raw = base64.urlsafe_b64decode(value.encode())
    return AESGCM(_cipher_key()).decrypt(raw[:12], raw[12:], str(associated).encode()).decode()


def _verify_mfa(user: UserRecord, code: str) -> bool:
    secret = _decrypt(user.mfa_secret, user.id) if user.mfa_secret else ""
    now = int(utc_now().timestamp())
    if secret and any(
        hmac.compare_digest(totp(secret, now + offset), code) for offset in (-30, 0, 30)
    ):
        return True
    code_hash = _digest(code)
    if code_hash in user.recovery_code_hashes:
        user.recovery_code_hashes = [x for x in user.recovery_code_hashes if x != code_hash]
        return True
    return False


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=8 * 60 * 60,
        httponly=True,
        secure=get_settings().env == "production",
        samesite="lax",
        path="/",
    )


async def _issue_session(db: AsyncSession, user: UserRecord, response: Response) -> SessionRecord:
    try:
        await ensure_mt5_started()
    except MT5StartupError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MT5 desktop runtime could not be started; session was not created",
        ) from exc
    raw = secrets.token_urlsafe(48)
    item = SessionRecord(
        user_id=user.id,
        owner_id=user.owner_id,
        token_hash=_digest(raw),
        role=user.role,
        expires_at=utc_now() + timedelta(hours=8),
    )
    db.add(item)
    await db.flush()
    _set_session_cookie(response, raw)
    await ResourceStore(db).audit(
        user.owner_id,
        user.id,
        "session.created",
        "session",
        item.id,
        {"expires_at": item.expires_at},
    )
    return item


async def _token_user(
    db: AsyncSession, token: str, kind: str, *, by_id: bool = False
) -> tuple[AuthTokenRecord, UserRecord]:
    match = (
        AuthTokenRecord.id == UUID(token) if by_id else AuthTokenRecord.token_hash == _digest(token)
    )
    item = await db.scalar(
        select(AuthTokenRecord)
        .where(
            match,
            AuthTokenRecord.kind == kind,
            AuthTokenRecord.used_at.is_(None),
            AuthTokenRecord.expires_at > utc_now(),
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = await db.get(UserRecord, item.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return item, user


@router.get("/registration-status")
async def registration_status(db: Annotated[AsyncSession, Depends(get_db)]):
    return {"signup_available": await _signup_available(db)}


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED)
async def signup(payload: SignupRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    email = _normalized_email(payload.email)
    _require_email_delivery()
    if not await _signup_available(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "signup is closed for this installation")
    user = UserRecord(id=uuid4(), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.add(SignupGateRecord(id=1, user_id=user.id))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "signup is closed for this installation"
        ) from exc
    raw = secrets.token_urlsafe(40)
    token = AuthTokenRecord(
        user_id=user.id,
        kind="EMAIL_VERIFICATION",
        token_hash=_digest(raw),
        expires_at=utc_now() + timedelta(hours=24),
    )
    db.add(token)
    await ResourceStore(db).audit(
        user.owner_id, user.id, "user.registered", "user", user.id, {"email": email}
    )
    try:
        development_token = await deliver_auth_link(email, "verify", raw)
    except AuthEmailUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "verification email could not be sent; retry signup",
        ) from exc
    result = user.security_state()
    if development_token:
        result["verification_token"] = development_token
    return result


@router.post("/email-verifications/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_email_verification(
    payload: ResendVerificationRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    _require_email_delivery()
    email = _normalized_email(payload.email)
    result: dict[str, str] = {"status": "accepted"}
    user = await db.scalar(select(UserRecord).where(UserRecord.email == email).with_for_update())
    if user is None or user.mfa_enabled:
        return result
    latest = await db.scalar(
        select(AuthTokenRecord)
        .where(AuthTokenRecord.user_id == user.id, AuthTokenRecord.kind == "EMAIL_VERIFICATION")
        .order_by(AuthTokenRecord.created_at.desc())
        .limit(1)
    )
    if latest is not None:
        issued_at = latest.created_at
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=UTC)
        if utc_now() - issued_at < timedelta(seconds=60):
            return result
    raw = secrets.token_urlsafe(40)
    try:
        async with db.begin_nested():
            db.add(
                AuthTokenRecord(
                    user_id=user.id,
                    kind="EMAIL_VERIFICATION",
                    token_hash=_digest(raw),
                    expires_at=utc_now() + timedelta(hours=24),
                )
            )
            await db.flush()
            development_token = await deliver_auth_link(email, "verify", raw)
    except AuthEmailUnavailable:
        logger.warning("authentication verification email delivery failed")
        return result
    if development_token:
        result["verification_token"] = development_token
    return result


@router.post("/email-verifications")
async def verify_email(payload: TokenRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    token, user = await _token_user(db, payload.token, "EMAIL_VERIFICATION")
    token.used_at = utc_now()
    user.email_verified = True
    enrollment_token = secrets.token_urlsafe(40)
    db.add(
        AuthTokenRecord(
            user_id=user.id,
            kind="MFA_BOOTSTRAP",
            token_hash=_digest(enrollment_token),
            expires_at=utc_now() + timedelta(minutes=30),
        )
    )
    await ResourceStore(db).audit(
        user.owner_id, user.id, "user.email_verified", "user", user.id, {}
    )
    result = user.security_state()
    result["enrollment_token"] = enrollment_token
    return result


@router.post("/mfa/enrollments", status_code=status.HTTP_201_CREATED)
async def create_mfa_enrollment(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_enrollment_token: Annotated[str | None, Header()] = None,
):
    if not x_enrollment_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "enrollment token required")
    bootstrap, user = await _token_user(db, x_enrollment_token, "MFA_BOOTSTRAP")
    model_user = User(
        id=user.id,
        owner_id=user.owner_id,
        email=user.email,
        password_hash=user.password_hash,
        email_verified=user.email_verified,
        mfa_enabled=user.mfa_enabled,
    )
    enrollment, recovery_codes = enroll(model_user)
    secret = enrollment.encrypted_secret
    user.mfa_secret = _encrypt(secret, user.id)
    user.recovery_code_hashes = enrollment.recovery_code_hashes
    bootstrap.used_at = utc_now()
    pending = AuthTokenRecord(
        user_id=user.id,
        kind="MFA_ENROLLMENT",
        expires_at=utc_now() + timedelta(minutes=15),
    )
    db.add(pending)
    await db.flush()
    return {
        "enrollment_id": str(pending.id),
        "method": "TOTP",
        "setup_uri": f"otpauth://totp/Matrades:{user.email}?secret={secret}&issuer=Matrades",
        "secret": secret,
        "recovery_codes": recovery_codes,
    }


@router.post("/mfa/enrollments/confirm")
async def confirm_mfa_enrollment(
    payload: EnrollmentConfirmRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pending, user = await _token_user(db, str(payload.enrollment_id), "MFA_ENROLLMENT", by_id=True)
    if not user.mfa_secret or not hmac.compare_digest(
        totp(_decrypt(user.mfa_secret, user.id)), payload.code
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid authenticator code")
    pending.used_at = utc_now()
    user.mfa_enabled = True
    await _issue_session(db, user, response)
    await ResourceStore(db).audit(user.owner_id, user.id, "user.mfa_enrolled", "user", user.id, {})
    return user.security_state()


@router.post("/sessions", status_code=status.HTTP_202_ACCEPTED)
async def begin_session(payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    user = await db.scalar(
        select(UserRecord).where(UserRecord.email == payload.email.lower().strip())
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not user.email_verified or not user.mfa_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "email verification and MFA are required")
    challenge = AuthTokenRecord(
        user_id=user.id,
        kind="LOGIN_MFA",
        expires_at=utc_now() + timedelta(minutes=5),
    )
    db.add(challenge)
    await db.flush()
    return {"challenge_id": str(challenge.id), "expires_at": challenge.expires_at}


@router.post("/mfa/challenges")
async def verify_mfa_challenge(
    payload: ChallengeRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    challenge, user = await _token_user(db, str(payload.challenge_id), "LOGIN_MFA", by_id=True)
    if not _verify_mfa(user, payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MFA or recovery code")
    challenge.used_at = utc_now()
    await _issue_session(db, user, response)
    return user.security_state()


@router.post("/step-up")
async def verify_step_up(
    payload: StepUpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    matrades_session: Annotated[str | None, Cookie()] = None,
):
    if not matrades_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session required")
    session = await db.scalar(
        select(SessionRecord).where(
            SessionRecord.token_hash == _digest(matrades_session),
            SessionRecord.revoked_at.is_(None),
            SessionRecord.expires_at > utc_now(),
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    user = await db.get(UserRecord, session.user_id)
    if user is None or not _verify_mfa(user, payload.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MFA or recovery code")
    session.step_up_at = utc_now()
    raw = secrets.token_urlsafe(32)
    grant = AuthTokenRecord(
        user_id=user.id,
        kind="STEP_UP",
        token_hash=_digest(raw),
        payload={"scope": payload.action_scope, "session_id": str(session.id)},
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db.add(grant)
    await db.flush()
    return {"grant_id": raw, "action_scope": payload.action_scope, "expires_at": grant.expires_at}


@router.get("/me")
async def me(
    db: Annotated[AsyncSession, Depends(get_db)],
    matrades_session: Annotated[str | None, Cookie()] = None,
):
    if not matrades_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session required")
    session = await db.scalar(
        select(SessionRecord).where(
            SessionRecord.token_hash == _digest(matrades_session),
            SessionRecord.revoked_at.is_(None),
            SessionRecord.expires_at > utc_now(),
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    user = await db.get(UserRecord, session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user unavailable")
    return user.security_state()


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    matrades_session: Annotated[str | None, Cookie()] = None,
):
    if matrades_session:
        session = await db.scalar(
            select(SessionRecord).where(SessionRecord.token_hash == _digest(matrades_session))
        )
        if session:
            session.revoked_at = utc_now()
            await ResourceStore(db).audit(
                session.owner_id, session.user_id, "session.revoked", "session", session.id, {}
            )
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/password-recovery", status_code=status.HTTP_202_ACCEPTED)
async def start_password_recovery(
    payload: RecoveryStartRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    _require_email_delivery()
    result: dict[str, str] = {"status": "accepted"}
    user = await db.scalar(
        select(UserRecord)
        .where(UserRecord.email == _normalized_email(payload.email))
        .with_for_update()
    )
    if user:
        latest = await db.scalar(
            select(AuthTokenRecord)
            .where(AuthTokenRecord.user_id == user.id, AuthTokenRecord.kind == "PASSWORD_RECOVERY")
            .order_by(AuthTokenRecord.created_at.desc())
            .limit(1)
        )
        if latest is not None:
            issued_at = latest.created_at
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=UTC)
            if utc_now() - issued_at < timedelta(seconds=60):
                return result
        raw = secrets.token_urlsafe(40)
        try:
            async with db.begin_nested():
                db.add(
                    AuthTokenRecord(
                        user_id=user.id,
                        kind="PASSWORD_RECOVERY",
                        token_hash=_digest(raw),
                        expires_at=utc_now() + timedelta(minutes=30),
                    )
                )
                await db.flush()
                development_token = await deliver_auth_link(user.email, "recover", raw)
        except AuthEmailUnavailable:
            logger.warning("authentication password-recovery email delivery failed")
            return result
        if development_token:
            result["recovery_token"] = development_token
    return result


@router.post("/password-recovery/complete")
async def complete_password_recovery(
    payload: RecoveryCompleteRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    token, user = await _token_user(db, payload.token, "PASSWORD_RECOVERY")
    user.password_hash = hash_password(payload.new_password)
    token.used_at = utc_now()
    sessions = (
        await db.scalars(
            select(SessionRecord).where(
                SessionRecord.user_id == user.id, SessionRecord.revoked_at.is_(None)
            )
        )
    ).all()
    for session in sessions:
        session.revoked_at = utc_now()
    return {"status": "password_updated"}
