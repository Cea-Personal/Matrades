from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authentication import (
    PasswordRecoveryManager,
    RecoveryChallengeView,
    SessionManager,
    SessionView,
    hash_password,
    verify_password,
)
from traderx.identity.mfa import TotpManager
from traderx.identity.model import (
    AssistedMfaResetRequest,
    AuthenticationThrottle,
    AuthSession,
    BootstrapState,
    MfaFactor,
    RecoveryChallenge,
    RecoveryCode,
    Role,
    User,
    UserStatus,
)
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.shared.config import get_settings
from traderx.shared.types import (
    AuthenticationError,
    AuthenticationRateLimited,
    AuthorizationError,
    BootstrapUnavailable,
    utc_now,
)
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id

router = APIRouter(prefix="/auth", tags=["Identity"])
user_router = APIRouter(prefix="/users", tags=["Identity"])

SESSION_COOKIE = "__Host-tx_session"
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class BootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class MfaCodeRequest(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class MfaRecoveryCodeRequest(BaseModel):
    recovery_code: str = Field(min_length=12, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetCompleteRequest(BaseModel):
    reset_token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=12, max_length=256)
    proof: MfaCodeRequest | MfaRecoveryCodeRequest


class MfaResetCommand(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)
    confirmation: Literal["CONFIRMED"]


class BootstrapStatus(BaseModel):
    bootstrap_available: bool


class LoginResult(BaseModel):
    status: Literal["AUTHENTICATED", "MFA_ENROLLMENT_REQUIRED", "MFA_REQUIRED"]
    recovery_codes: list[str] | None = None


class MfaEnrollment(BaseModel):
    provisioning_uri: str


class SessionResult(BaseModel):
    id: UUID
    user_id: UUID
    assurance: str
    expires_at: datetime
    revoked_at: datetime | None


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


def _login_throttle_key(email: str, client_host: str) -> str:
    pepper = get_settings().session_pepper.get_secret_value()
    return hashlib.sha256(f"{pepper}:{email.lower()}:{client_host}".encode()).hexdigest()


def _as_utc_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _check_login_throttle(database: Session, key_digest: str, now: datetime) -> None:
    throttle = database.scalar(
        select(AuthenticationThrottle).where(AuthenticationThrottle.key_digest == key_digest)
    )
    if throttle and throttle.locked_until and _as_utc_datetime(throttle.locked_until) > now:
        raise AuthenticationRateLimited("too many authentication attempts; try again later")


def _record_failed_login(database: Session, key_digest: str, now: datetime) -> bool:
    throttle = database.scalar(
        select(AuthenticationThrottle).where(AuthenticationThrottle.key_digest == key_digest)
    )
    window = timedelta(minutes=15)
    if throttle is None:
        throttle = AuthenticationThrottle(
            key_digest=key_digest,
            window_started_at=now,
            failure_count=1,
            locked_until=None,
        )
        database.add(throttle)
    elif now - _as_utc_datetime(throttle.window_started_at) > window:
        throttle.window_started_at = now
        throttle.failure_count = 1
        throttle.locked_until = None
    else:
        throttle.failure_count += 1
    if throttle.failure_count >= 5:
        throttle.locked_until = now + window
    database.commit()
    return throttle.locked_until is not None


def _clear_login_throttle(database: Session, key_digest: str) -> None:
    throttle = database.scalar(
        select(AuthenticationThrottle).where(AuthenticationThrottle.key_digest == key_digest)
    )
    if throttle is not None:
        database.delete(throttle)


def _secret_box() -> SecretBox:
    return SecretBox(get_settings().encryption_key_b64.get_secret_value())


def _password_recovery_manager() -> PasswordRecoveryManager:
    return PasswordRecoveryManager(get_settings().session_pepper.get_secret_value())


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_absolute_hours * 60 * 60,
        # The __Host- prefix is accepted by browsers only for Secure cookies.
        # TraderX exposes authentication only through the HTTPS proxy, including
        # local development, so the transport guarantee must never be relaxed.
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
    now = utc_now()
    if not manager.is_active(session_view, now):
        session.revoked_at = now
        session.revoked_reason = "SESSION_EXPIRED"
        database.commit()
        raise AuthenticationError("the session has expired")
    user = database.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("the session is no longer valid")
    session.last_seen_at = now
    return AuthenticationContext(user=user, session=session)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def authenticated_context(request: Request, database: DatabaseSession) -> AuthenticationContext:
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
    context.session.revoked_reason = "ASSURANCE_ROTATED"
    return _issue_session(database, context.user.id, assurance="MFA")


def _revoke_user_sessions(database: Session, user_id: UUID, now: datetime, reason: str) -> None:
    for session in database.scalars(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ):
        session.revoked_at = now
        session.revoked_reason = reason


def _replace_mfa_enrollment(database: Session, user_id: UUID, now: datetime) -> None:
    for factor in database.scalars(
        select(MfaFactor).where(MfaFactor.user_id == user_id, MfaFactor.revoked_at.is_(None))
    ):
        factor.revoked_at = now
    for code in database.scalars(
        select(RecoveryCode).where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
    ):
        code.used_at = now
    database.add(MfaFactor(user_id=user_id, factor_type="TOTP", secret_ref=""))


def _record_identity_audit(
    database: Session,
    *,
    action: str,
    target_user_id: UUID,
    now: datetime,
    actor: AuthenticationContext | None = None,
    reason: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    database.add(
        AuditEvent.create(
            actor_type="USER" if actor else "ANONYMOUS",
            actor_id=actor.user.id if actor else None,
            actor_role=str(actor.user.role) if actor else None,
            action=action,
            outcome="SUCCESS",
            target_type="USER",
            target_id=target_user_id,
            target_version=None,
            reason=reason,
            assurance=actor.session.assurance if actor else None,
            correlation_id=correlation_id.get(),
            causation_id=None,
            idempotency_key=None,
            previous_value=None,
            new_value=details,
            occurred_at=now,
        )
    )


def _confirmed_factor(database: Session, user_id: UUID) -> MfaFactor | None:
    return database.scalar(
        select(MfaFactor).where(
            MfaFactor.user_id == user_id,
            MfaFactor.confirmed_at.is_not(None),
            MfaFactor.revoked_at.is_(None),
        )
    )


def _redeem_recovery_code(
    database: Session, user_id: UUID, supplied_code: str, now: datetime
) -> None:
    for recovery_code in database.scalars(
        select(RecoveryCode).where(
            RecoveryCode.user_id == user_id,
            RecoveryCode.used_at.is_(None),
        )
    ):
        if verify_password(supplied_code, recovery_code.code_hash):
            recovery_code.used_at = now
            return
    raise AuthenticationError("the recovery code is invalid or has already been used")


def _verify_second_proof(
    database: Session,
    user: User,
    proof: MfaCodeRequest | MfaRecoveryCodeRequest,
    now: datetime,
) -> Literal["TOTP", "RECOVERY_CODE"]:
    if isinstance(proof, MfaCodeRequest):
        factor = _confirmed_factor(database, user.id)
        if factor is None:
            raise AuthenticationError("an enrolled authenticator is required")
        factor.last_used_step = TotpManager().verify(
            _decrypt_totp_secret(factor), proof.code, now, factor.last_used_step
        )
        return "TOTP"
    _redeem_recovery_code(database, user.id, proof.recovery_code, now)
    return "RECOVERY_CODE"


@router.get("/bootstrap-status", response_model=BootstrapStatus)
def bootstrap_status(database: DatabaseSession) -> BootstrapStatus:
    return BootstrapStatus(bootstrap_available=database.get(BootstrapState, 1) is None)


@router.post("/bootstrap", response_model=LoginResult, status_code=201)
def bootstrap_initial_owner(
    payload: BootstrapRequest,
    response: Response,
    database: DatabaseSession,
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


@router.post("/password-reset", status_code=202)
def request_password_reset(
    payload: PasswordResetRequest,
    database: DatabaseSession,
) -> Response:
    """Create a single-use reset challenge without revealing account existence.

    Delivery is intentionally delegated to the notification subsystem. The token is never returned
    by this endpoint or recorded in an audit/event payload.
    """

    user = database.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is not None and user.status == UserStatus.ACTIVE:
        now = utc_now()
        token, challenge = _password_recovery_manager().issue(now)
        del token
        database.add(
            RecoveryChallenge(
                user_id=user.id,
                token_digest=challenge.token_digest,
                expires_at=challenge.expires_at,
            )
        )
        _record_identity_audit(
            database,
            action="PASSWORD_RESET_REQUESTED",
            target_user_id=user.id,
            now=now,
            details={"delivery": "REQUESTED"},
        )
        database.commit()
    return Response(status_code=202)


@router.post("/password-reset/complete", response_model=LoginResult)
def complete_password_reset(
    payload: PasswordResetCompleteRequest,
    response: Response,
    database: DatabaseSession,
) -> LoginResult:
    manager = _password_recovery_manager()
    challenge = database.scalar(
        select(RecoveryChallenge).where(
            RecoveryChallenge.token_digest == manager.digest(payload.reset_token)
        )
    )
    if challenge is None:
        raise AuthenticationError("password reset challenge is unavailable")

    now = utc_now()
    manager.consume(
        RecoveryChallengeView(
            token_digest=challenge.token_digest,
            expires_at=_as_utc(challenge.expires_at),
            consumed_at=_as_utc(challenge.consumed_at) if challenge.consumed_at else None,
        ),
        payload.reset_token,
        now,
    )
    user = database.get(User, challenge.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("password reset challenge is unavailable")

    proof_kind = _verify_second_proof(database, user, payload.proof, now)
    challenge.consumed_at = now
    user.password_hash = hash_password(payload.new_password)
    user.last_authenticated_at = now
    _revoke_user_sessions(database, user.id, now, "PASSWORD_RESET")

    if proof_kind == "RECOVERY_CODE":
        _replace_mfa_enrollment(database, user.id, now)
        token = _issue_session(database, user.id, assurance="PASSWORD")
        result = LoginResult(status="MFA_ENROLLMENT_REQUIRED")
    else:
        token = _issue_session(database, user.id, assurance="MFA")
        result = LoginResult(status="AUTHENTICATED")

    _record_identity_audit(
        database,
        action="PASSWORD_RESET_COMPLETED",
        target_user_id=user.id,
        now=now,
        details={"proof_kind": proof_kind},
    )
    database.commit()
    _set_session_cookie(response, token)
    return result


@router.post("/login", response_model=LoginResult)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    database: DatabaseSession,
) -> LoginResult:
    client_host = request.client.host if request.client else "unknown"
    throttle_key = _login_throttle_key(str(payload.email), client_host)
    now = utc_now()
    _check_login_throttle(database, throttle_key, now)
    user = database.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or user.status != UserStatus.ACTIVE:
        if _record_failed_login(database, throttle_key, now):
            raise AuthenticationRateLimited("too many authentication attempts; try again later")
        raise AuthenticationError("invalid email or password")
    if not verify_password(payload.password, user.password_hash):
        if _record_failed_login(database, throttle_key, now):
            raise AuthenticationRateLimited("too many authentication attempts; try again later")
        raise AuthenticationError("invalid email or password")

    _clear_login_throttle(database, throttle_key)
    token = _issue_session(database, user.id, assurance="PASSWORD")
    confirmed_factor = _confirmed_factor(database, user.id)
    database.commit()
    _set_session_cookie(response, token)
    if confirmed_factor is None:
        return LoginResult(status="MFA_ENROLLMENT_REQUIRED")
    return LoginResult(status="MFA_REQUIRED")


@router.post("/mfa/enroll", response_model=MfaEnrollment)
def begin_mfa_enrollment(
    request: Request,
    database: DatabaseSession,
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
    database: DatabaseSession,
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
    database: DatabaseSession,
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


@router.post("/mfa/recovery", response_model=LoginResult)
def recover_mfa_with_code(
    payload: MfaRecoveryCodeRequest,
    request: Request,
    response: Response,
    database: DatabaseSession,
) -> LoginResult:
    context = _active_context(request, database)
    if context.session.assurance != "PASSWORD":
        raise AuthorizationError("a fresh password authentication is required")

    now = utc_now()
    _redeem_recovery_code(database, context.user.id, payload.recovery_code, now)
    _revoke_user_sessions(database, context.user.id, now, "MFA_RECOVERY")
    _replace_mfa_enrollment(database, context.user.id, now)
    token = _issue_session(database, context.user.id, assurance="PASSWORD")
    _record_identity_audit(
        database,
        action="MFA_RECOVERY_CODE_USED",
        target_user_id=context.user.id,
        now=now,
        actor=context,
        details={"fresh_enrollment_required": True},
    )
    database.commit()
    _set_session_cookie(response, token)
    return LoginResult(status="MFA_ENROLLMENT_REQUIRED")


@user_router.post("/{user_id}/mfa-reset", status_code=202)
def initiate_assisted_mfa_reset(
    user_id: UUID,
    payload: MfaResetCommand,
    request: Request,
    database: DatabaseSession,
) -> Response:
    context = authenticated_context(request, database)
    if context.user.role not in {Role.OWNER, Role.ADMIN}:
        raise AuthorizationError("only an owner or administrator can reset multi-factor enrollment")
    if not _session_manager().has_recent_assurance(
        SessionView(
            token_digest=context.session.token_digest,
            assurance=context.session.assurance,
            issued_at=_as_utc(context.session.issued_at),
            last_seen_at=_as_utc(context.session.last_seen_at),
            expires_at=_as_utc(context.session.expires_at),
            revoked_at=_as_utc(context.session.revoked_at) if context.session.revoked_at else None,
        ),
        utc_now(),
        timedelta(minutes=5),
    ):
        raise AuthorizationError("recent multi-factor confirmation is required")

    target = database.get(User, user_id)
    if target is None or target.status != UserStatus.ACTIVE:
        raise AuthorizationError("the requested user cannot be reset")

    now = utc_now()
    reset = AssistedMfaResetRequest(
        target_user_id=target.id,
        initiated_by_user_id=context.user.id,
        reason=payload.reason,
        confirmation=payload.confirmation,
        completed_at=now,
        outcome="COMPLETED",
    )
    database.add(reset)
    database.flush()
    _revoke_user_sessions(database, target.id, now, "ASSISTED_MFA_RESET")
    _replace_mfa_enrollment(database, target.id, now)
    _record_identity_audit(
        database,
        action="ASSISTED_MFA_RESET",
        target_user_id=target.id,
        now=now,
        actor=context,
        reason=payload.reason,
        details={"reset_request_id": str(reset.id)},
    )
    database.commit()
    return Response(status_code=202)


@router.get("/sessions", response_model=list[SessionResult])
def list_sessions(
    request: Request,
    database: DatabaseSession,
) -> list[SessionResult]:
    context = authenticated_context(request, database)
    return [
        SessionResult(
            id=session.id,
            user_id=session.user_id,
            assurance=session.assurance,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
        )
        for session in database.scalars(
            select(AuthSession).where(AuthSession.user_id == context.user.id)
        )
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: UUID,
    request: Request,
    database: DatabaseSession,
) -> Response:
    context = authenticated_context(request, database)
    session = database.get(AuthSession, session_id)
    if session is None or session.user_id != context.user.id:
        raise AuthorizationError("the requested session is unavailable")
    session.revoked_at = utc_now()
    session.revoked_reason = "USER_REVOKED"
    database.commit()
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    database: DatabaseSession,
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
