from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from traderx.identity.authentication import SessionManager, SessionView, hash_password, verify_password
from traderx.identity.mfa import TotpManager
from traderx.identity.model import (
    AuthSession,
    BootstrapState,
    MfaFactor,
    RecoveryCode,
    Role,
    User,
    UserStatus,
)
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.shared.config import get_settings
from traderx.shared.types import (
    AuthenticationError,
    AuthorizationError,
    BootstrapUnavailable,
    utc_now,
)
from traderx_api.dependencies import get_database_session

router = APIRouter(prefix="/auth", tags=["Identity"])

SESSION_COOKIE = "__Host-tx_session"


class BootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class MfaCodeRequest(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class BootstrapStatus(BaseModel):
    bootstrap_available: bool


class LoginResult(BaseModel):
    status: Literal["AUTHENTICATED", "MFA_ENROLLMENT_REQUIRED", "MFA_REQUIRED"]
    recovery_codes: list[str] | None = None


class MfaEnrollment(BaseModel):
    provisioning_uri: str


@dataclass(frozen=True, slots=True)
class AuthenticationContext:
    user: User
    session: AuthSession


def _session_manager() -> SessionManager:
    settings = get_settings()
    return SessionManager(
        settings.session_pepper.get_secret_value(),
        idle=timedelta(minutes=settings.session_idle_minutes),
        absolute=timedelta(hours=settings.session_absolute_hours),
    )


def _secret_box() -> SecretBox:
    return SecretBox(get_settings().encryption_key_b64.get_secret_value())


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_absolute_hours * 60 * 60,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )


def _issue_session(database: Session, user_id: UUID, assurance: str) -> str:
    settings = get_settings()
    now = utc_now()
    token, digest = _session_manager().issue()
    database.add(
        AuthSession(
            user_id=user_id,
            token_digest=digest,
            assurance=assurance,
            issued_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
        )
    )
    return token


def _active_context(request: Request, database: Session) -> AuthenticationContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthenticationError("an active session is required")

    manager = _session_manager()
    session = database.scalar(
        select(AuthSession).where(AuthSession.token_digest == manager.digest(token))
    )
    if session is None:
        raise AuthenticationError("an active session is required")
    session_view = SessionView(
        token_digest=session.token_digest,
        assurance=session.assurance,
        issued_at=_as_utc(session.issued_at),
        last_seen_at=_as_utc(session.last_seen_at),
        expires_at=_as_utc(session.expires_at),
        revoked_at=_as_utc(session.revoked_at) if session.revoked_at else None,
    )
    if not manager.is_active(session_view, utc_now()):
        raise AuthenticationError("the session has expired")
    user = database.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("the session is no longer valid")
    session.last_seen_at = utc_now()
    return AuthenticationContext(user=user, session=session)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def authenticated_context(
    request: Request, database: Session = Depends(get_database_session)
) -> AuthenticationContext:
    context = _active_context(request, database)
    if context.session.assurance != "MFA":
        raise AuthenticationError("multi-factor verification is required")
    return context


def _decrypt_totp_secret(factor: MfaFactor) -> str:
    encrypted = EncryptedSecret(**json.loads(factor.secret_ref))
    value = _secret_box().decrypt(encrypted).get("totp")
    if not isinstance(value, str):
        raise AuthenticationError("the multi-factor enrollment is invalid")
    return value


def _store_totp_secret(factor: MfaFactor, secret: str) -> None:
    encrypted = _secret_box().encrypt({"totp": secret}, aad=f"mfa:{factor.user_id}")
    factor.secret_ref = json.dumps(asdict(encrypted), sort_keys=True)


def _rotate_to_mfa(database: Session, context: AuthenticationContext) -> str:
    context.session.revoked_at = utc_now()
    return _issue_session(database, context.user.id, assurance="MFA")


@router.get("/bootstrap-status", response_model=BootstrapStatus)
def bootstrap_status(database: Session = Depends(get_database_session)) -> BootstrapStatus:
    return BootstrapStatus(bootstrap_available=database.get(BootstrapState, 1) is None)


@router.post("/bootstrap", response_model=LoginResult, status_code=201)
def bootstrap_initial_owner(
    payload: BootstrapRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> LoginResult:
    if database.get(BootstrapState, 1) is not None:
        raise BootstrapUnavailable("the initial owner has already been created")

    now = utc_now()
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=Role.OWNER,
        status=UserStatus.ACTIVE,
        mfa_required=True,
    )
    database.add(user)
    try:
        database.flush()
        database.add(BootstrapState(id=1, owner_id=user.id, initialized_at=now))
        database.add(
            MfaFactor(
                user_id=user.id,
                factor_type="TOTP",
                secret_ref="",
            )
        )
        token = _issue_session(database, user.id, assurance="PASSWORD")
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise BootstrapUnavailable("the initial owner has already been created") from error

    _set_session_cookie(response, token)
    return LoginResult(status="MFA_ENROLLMENT_REQUIRED")


@router.post("/login", response_model=LoginResult)
def login(
    payload: LoginRequest,
    response: Response,
    database: Session = Depends(get_database_session),
) -> LoginResult:
    user = database.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("invalid email or password")

    token = _issue_session(database, user.id, assurance="PASSWORD")
    confirmed_factor = database.scalar(
        select(MfaFactor).where(
            MfaFactor.user_id == user.id,
            MfaFactor.confirmed_at.is_not(None),
            MfaFactor.revoked_at.is_(None),
        )
    )
    database.commit()
    _set_session_cookie(response, token)
    if confirmed_factor is None:
        return LoginResult(status="MFA_ENROLLMENT_REQUIRED")
    return LoginResult(status="MFA_REQUIRED")


@router.post("/mfa/enroll", response_model=MfaEnrollment)
def begin_mfa_enrollment(
    request: Request,
    database: Session = Depends(get_database_session),
) -> MfaEnrollment:
    context = _active_context(request, database)
    if context.session.assurance != "PASSWORD":
        raise AuthorizationError("a fresh password authentication is required")

    factor = database.scalar(
        select(MfaFactor)
        .where(MfaFactor.user_id == context.user.id, MfaFactor.confirmed_at.is_(None))
        .order_by(MfaFactor.created_at.desc())
    )
    if factor is None:
        factor = MfaFactor(user_id=context.user.id, factor_type="TOTP", secret_ref="")
        database.add(factor)
        database.flush()
    secret = TotpManager().new_secret()
    _store_totp_secret(factor, secret)
    database.commit()
    return MfaEnrollment(
        provisioning_uri=TotpManager().provisioning_uri(secret, str(context.user.email))
    )


@router.post("/mfa/enroll/verify", response_model=LoginResult)
def complete_mfa_enrollment(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    database: Session = Depends(get_database_session),
) -> LoginResult:
    context = _active_context(request, database)
    factor = database.scalar(
        select(MfaFactor)
        .where(MfaFactor.user_id == context.user.id, MfaFactor.confirmed_at.is_(None))
        .order_by(MfaFactor.created_at.desc())
    )
    if factor is None or not factor.secret_ref:
        raise AuthenticationError("multi-factor enrollment must be started first")

    now = utc_now()
    factor.last_used_step = TotpManager().verify(
        _decrypt_totp_secret(factor), payload.code, now, factor.last_used_step
    )
    factor.confirmed_at = now
    context.user.last_authenticated_at = now
    recovery_codes = [secrets.token_urlsafe(12) for _ in range(8)]
    for code in recovery_codes:
        database.add(RecoveryCode(user_id=context.user.id, code_hash=hash_password(code)))
    token = _rotate_to_mfa(database, context)
    database.commit()
    _set_session_cookie(response, token)
    return LoginResult(status="AUTHENTICATED", recovery_codes=recovery_codes)


@router.post("/mfa/verify", response_model=LoginResult)
def verify_mfa(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    database: Session = Depends(get_database_session),
) -> LoginResult:
    context = _active_context(request, database)
    factor = database.scalar(
        select(MfaFactor).where(
            MfaFactor.user_id == context.user.id,
            MfaFactor.confirmed_at.is_not(None),
            MfaFactor.revoked_at.is_(None),
        )
    )
    if factor is None:
        raise AuthenticationError("multi-factor enrollment is required")

    now = utc_now()
    factor.last_used_step = TotpManager().verify(
        _decrypt_totp_secret(factor), payload.code, now, factor.last_used_step
    )
    context.user.last_authenticated_at = now
    token = _rotate_to_mfa(database, context)
    database.commit()
    _set_session_cookie(response, token)
    return LoginResult(status="AUTHENTICATED")


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    database: Session = Depends(get_database_session),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session = database.scalar(
            select(AuthSession).where(AuthSession.token_digest == _session_manager().digest(token))
        )
        if session is not None:
            session.revoked_at = utc_now()
            database.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
