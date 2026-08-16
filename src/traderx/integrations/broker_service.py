from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.broker_model import (
    BrokerDiscoveredAccount,
    BrokerIntegrationProfile,
    BrokerProvider,
    Mt5BridgeAgent,
)
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.integrations.mt5_bridge import Mt5BridgeError, normalize_native_market_evidence
from traderx.integrations.reconciliation import (
    NormalizedBrokerSnapshot,
    commit_authoritative_snapshot,
    record_broker_failure,
)
from traderx.shared.types import InvalidTransition

BROKER_CAPABILITIES = ["ACCOUNT_READ", "POSITION_READ", "DEAL_READ", "INSTRUMENT_READ"]
MT5_ENROLLMENT_LIFETIME = timedelta(hours=24)
MT5_SNAPSHOT_MAX_AGE = timedelta(seconds=90)


@dataclass(frozen=True, slots=True)
class ManagedMt5Enrollment:
    integration: Integration
    agent_id: UUID
    enrollment_token: str
    expires_at: datetime
    account_login: str
    server: str


@dataclass(frozen=True, slots=True)
class ManagedMt5Snapshot:
    balance: str
    equity: str
    currency: str
    positions: list[dict[str, object]]
    deals: list[dict[str, object]]
    instruments: list[dict[str, object]]
    terminal_version: str
    observed_at: datetime


def begin_managed_mt5_enrollment(
    database: Session,
    actor: Actor,
    *,
    account_login: str,
    server: str,
    display_name: str | None = None,
) -> ManagedMt5Enrollment:
    """Create or reactivate a TraderX-owned bridge and return a one-time enrollment code.

    The code is deliberately the only bridge setup value shown to the user. The Windows agent
    exchanges it over HTTPS for its own credential; neither code is stored in plaintext.
    """

    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    configuration = _managed_mt5_configuration(account_login=account_login, server=server)
    existing = database.scalar(
        select(BrokerIntegrationProfile).where(
            BrokerIntegrationProfile.provider == BrokerProvider.MT5_TERMINAL_BRIDGE,
            BrokerIntegrationProfile.account_login == configuration["account_login"],
            BrokerIntegrationProfile.server == configuration["server"],
        )
    )
    if existing is not None:
        prior_integration = database.get(Integration, existing.integration_id)
        if prior_integration is None or prior_integration.state != "REMOVED":
            raise InvalidTransition("this MT5 account already has a TraderX bridge enrollment")
        agent = _managed_mt5_agent(database, prior_integration.id)
        enrollment = _issue_managed_mt5_enrollment(
            prior_integration, agent, configuration=configuration
        )
        database.flush()
        return enrollment
    integration = Integration(
        name=display_name or _managed_mt5_name(configuration),
        provider=BrokerProvider.MT5_TERMINAL_BRIDGE,
        state="DISABLED",
        capabilities=BROKER_CAPABILITIES,
        official_source=True,
    )
    database.add(integration)
    database.flush()

    agent = Mt5BridgeAgent(
        integration_id=integration.id,
        enrollment_token_digest="",
        enrollment_expires_at=datetime.now(UTC),
    )
    database.add(agent)
    database.flush()
    database.add(
        BrokerIntegrationProfile(
            integration_id=integration.id,
            provider=BrokerProvider.MT5_TERMINAL_BRIDGE,
            bridge_id=str(agent.id),
            account_login=configuration["account_login"],
            server=configuration["server"],
            configuration={"transport": "TRADERX_MANAGED_OUTBOUND"},
        )
    )
    database.flush()
    return _issue_managed_mt5_enrollment(integration, agent, configuration=configuration)


def renew_managed_mt5_enrollment(
    database: Session, actor: Actor, integration: Integration
) -> ManagedMt5Enrollment:
    """Invalidate the prior bridge credential and issue a fresh one-time enrollment code."""

    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    _require_mt5_provider(integration)
    profile = _profile(database, integration.id)
    configuration = _managed_mt5_configuration(
        account_login=profile.account_login or "", server=profile.server or ""
    )
    _require_active_managed_mt5_integration(integration)
    agent = _managed_mt5_agent(database, integration.id)
    enrollment = _issue_managed_mt5_enrollment(integration, agent, configuration=configuration)
    database.flush()
    return enrollment


def remove_managed_mt5_integration(
    database: Session, actor: Actor, integration: Integration
) -> int:
    """Revoke an MT5 bridge and hide it without deleting account-truth evidence."""

    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.remove", require_mfa=True)
    _require_mt5_provider(integration)
    if integration.state == "REMOVED":
        return 0

    now = datetime.now(UTC)
    agent = _managed_mt5_agent(database, integration.id)
    agent.enrollment_token_digest = _token_digest(_new_agent_token())
    agent.enrollment_expires_at = now
    agent.agent_token_digest = None
    agent.enrolled_at = None
    agent.last_seen_at = None
    agent.last_snapshot_at = None
    agent.latest_snapshot = {}

    profile = _profile(database, integration.id)
    profile.selected_provider_account_id = None
    bound_accounts = database.scalars(
        select(TradingAccount).where(TradingAccount.broker_integration_id == integration.id)
    ).all()
    for account in bound_accounts:
        record_broker_failure(
            database,
            integration,
            account,
            reason_code="BROKER_INTEGRATION_REMOVED",
            detail="the MT5 account integration was removed by an authorized user",
        )
        account.broker_integration_id = None
        account.provider_account_id = None
        account.status = AccountStatus.BLOCKED

    integration.state = "REMOVED"
    database.add(
        IntegrationHealthObservation(
            integration_id=integration.id,
            status="REMOVED",
            evidence={
                "reason_code": "BROKER_INTEGRATION_REMOVED",
                "unbound_account_count": len(bound_accounts),
            },
            observed_at=now,
        )
    )
    database.flush()
    return len(bound_accounts)


def enroll_managed_mt5_agent(
    database: Session,
    agent_id: UUID,
    *,
    enrollment_token: str,
    login: str,
    server: str,
    connected: bool,
    trading_disabled: bool,
    terminal_version: str,
) -> str:
    """Exchange one valid enrollment code for the bridge's local credential."""

    agent = database.get(Mt5BridgeAgent, agent_id)
    if agent is None:
        raise InvalidTransition("the MT5 bridge enrollment is not available")
    now = datetime.now(UTC)
    if (
        agent.enrolled_at is not None
        or _as_utc(agent.enrollment_expires_at) <= now
        or not hmac.compare_digest(agent.enrollment_token_digest, _token_digest(enrollment_token))
    ):
        raise InvalidTransition("the MT5 bridge enrollment code is invalid or expired")
    integration = database.get(Integration, agent.integration_id)
    if integration is None:
        raise InvalidTransition("the MT5 bridge integration is not available")
    _require_active_managed_mt5_integration(integration)
    profile = _profile(database, integration.id)
    if login != profile.account_login or server != profile.server:
        raise InvalidTransition("the MT5 terminal account does not match the requested connection")
    if not connected or not trading_disabled:
        raise InvalidTransition(
            "the MT5 bridge requires a connected investor terminal with trading disabled"
        )
    if not terminal_version.strip():
        raise InvalidTransition("the MT5 terminal version is required")
    agent_token = _new_agent_token()
    agent.agent_token_digest = _token_digest(agent_token)
    agent.enrolled_at = now
    agent.last_seen_at = now
    database.flush()
    return agent_token


def managed_mt5_enrollment_configuration(
    database: Session, agent_id: UUID, *, enrollment_token: str
) -> dict[str, str]:
    """Return the non-secret terminal identity to a holder of a valid enrollment code."""

    agent = database.get(Mt5BridgeAgent, agent_id)
    if (
        agent is None
        or agent.enrolled_at is not None
        or _as_utc(agent.enrollment_expires_at) <= datetime.now(UTC)
        or not hmac.compare_digest(agent.enrollment_token_digest, _token_digest(enrollment_token))
    ):
        raise InvalidTransition("the MT5 bridge enrollment code is invalid or expired")
    integration = database.get(Integration, agent.integration_id)
    if integration is None:
        raise InvalidTransition("the MT5 bridge integration is not available")
    _require_active_managed_mt5_integration(integration)
    profile = _profile(database, agent.integration_id)
    return {
        "login": _required_text({"login": profile.account_login}, "login"),
        "server": _required_text({"server": profile.server}, "server"),
    }


def ingest_managed_mt5_snapshot(
    database: Session,
    agent_id: UUID,
    *,
    agent_token: str,
    login: str,
    server: str,
    connected: bool,
    trading_disabled: bool,
    terminal_version: str,
    balance: str,
    equity: str,
    currency: str,
    positions: list[dict[str, object]],
    deals: list[dict[str, object]],
    instruments: list[dict[str, object]],
) -> None:
    """Accept a complete, current, read-only terminal snapshot from an enrolled bridge."""

    agent = database.get(Mt5BridgeAgent, agent_id)
    if agent is None or agent.agent_token_digest is None:
        raise InvalidTransition("the MT5 bridge is not enrolled")
    if not hmac.compare_digest(agent.agent_token_digest, _token_digest(agent_token)):
        raise InvalidTransition("the MT5 bridge credential is invalid")
    integration = database.get(Integration, agent.integration_id)
    if integration is None:
        raise InvalidTransition("the MT5 bridge integration is not available")
    _require_active_managed_mt5_integration(integration)
    profile = _profile(database, integration.id)
    if login != profile.account_login or server != profile.server:
        raise InvalidTransition("the MT5 terminal account does not match the registered connection")
    if not connected or not trading_disabled:
        raise InvalidTransition(
            "the MT5 bridge requires a connected investor terminal with trading disabled"
        )
    _decimal(balance)
    _decimal(equity)
    if len(currency) != 3 or not currency.isalpha():
        raise InvalidTransition("the MT5 bridge returned an invalid account currency")
    if not terminal_version.strip():
        raise InvalidTransition("the MT5 bridge returned no terminal version")
    now = datetime.now(UTC)
    try:
        normalized_instruments = normalize_native_market_evidence(instruments, received_at=now)
    except Mt5BridgeError as error:
        raise InvalidTransition(str(error)) from error
    agent.last_seen_at = now
    agent.last_snapshot_at = now
    agent.latest_snapshot = {
        "balance": balance,
        "equity": equity,
        "currency": currency.upper(),
        "positions": positions,
        "deals": deals,
        "instruments": normalized_instruments,
        "terminal_version": terminal_version,
    }
    integration.state = "HEALTHY"
    database.add(
        IntegrationHealthObservation(
            integration_id=integration.id,
            status="HEALTHY",
            evidence={"reason_code": "MANAGED_MT5_SNAPSHOT_RECEIVED"},
            observed_at=now,
        )
    )
    database.flush()


def record_discovered_accounts(
    database: Session,
    integration: Integration,
    candidates: list[dict[str, object]],
) -> None:
    now = datetime.now(UTC)
    existing = {
        discovered.provider_account_id: discovered
        for discovered in database.scalars(
            select(BrokerDiscoveredAccount).where(
                BrokerDiscoveredAccount.integration_id == integration.id
            )
        )
    }
    for candidate in candidates:
        account_id = _required_text(candidate, "provider_account_id")
        target = existing.get(account_id)
        fields = {
            "display_name": _optional_text(candidate, "display_name"),
            "currency": _optional_text(candidate, "currency"),
            "account_mode": _optional_text(candidate, "account_mode") or "UNKNOWN",
            "verification_status": "VERIFIED",
            "verified_at": now,
        }
        if target is None:
            database.add(
                BrokerDiscoveredAccount(
                    integration_id=integration.id, provider_account_id=account_id, **fields
                )
            )
        else:
            for name, value in fields.items():
                setattr(target, name, value)
    integration.state = "HEALTHY"
    database.flush()


def bind_selected_account(
    database: Session, actor: Actor, integration: Integration, provider_account_id: str
) -> None:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.bind_account", require_mfa=True)
    _require_mt5_provider(integration)
    candidate = database.scalar(
        select(BrokerDiscoveredAccount).where(
            BrokerDiscoveredAccount.integration_id == integration.id,
            BrokerDiscoveredAccount.provider_account_id == provider_account_id,
            BrokerDiscoveredAccount.verification_status == "VERIFIED",
        )
    )
    if candidate is None:
        raise InvalidTransition("select an account returned by a successful broker test")
    profile = _profile(database, integration.id)
    profile.selected_provider_account_id = provider_account_id
    database.flush()


def discovered_account_payload(database: Session, integration_id: UUID) -> list[dict[str, object]]:
    integration = database.get(Integration, integration_id)
    if integration is None:
        raise InvalidTransition("the requested integration does not exist")
    _require_mt5_provider(integration)
    return [
        {
            "provider_account_id": account.provider_account_id,
            "provider": integration.provider,
            "display_name": account.display_name,
            "currency": account.currency,
            "account_mode": account.account_mode,
            "verification_status": account.verification_status,
            "verified_at": account.verified_at.isoformat() if account.verified_at else None,
        }
        for account in database.scalars(
            select(BrokerDiscoveredAccount)
            .where(BrokerDiscoveredAccount.integration_id == integration_id)
            .order_by(
                BrokerDiscoveredAccount.display_name, BrokerDiscoveredAccount.provider_account_id
            )
        )
    ]


def test_broker_integration(database: Session, integration: Integration) -> list[dict[str, object]]:
    """Perform a bounded read-only credential test and retain only safe discovered-account data."""

    _require_mt5_provider(integration)
    profile = _profile(database, integration.id)
    try:
        snapshot = _latest_managed_mt5_snapshot(database, integration)
        candidates: list[dict[str, object]] = [
            {
                "provider_account_id": _required_text({"login": profile.account_login}, "login"),
                "display_name": f"{profile.server} {profile.account_login}",
                "currency": snapshot.currency,
                "account_mode": "READ_ONLY",
            }
        ]
    except (ValueError, InvalidTransition) as error:
        integration.state = "DEGRADED"
        database.add(
            IntegrationHealthObservation(
                integration_id=integration.id,
                status="DEGRADED",
                evidence={"reason_code": "CONNECTION_TEST_FAILED"},
                observed_at=datetime.now(UTC),
            )
        )
        database.flush()
        raise InvalidTransition(
            "broker connection test failed; credentials and diagnostics remain protected"
        ) from error
    record_discovered_accounts(database, integration, candidates)
    return candidates


def sync_selected_broker_account(
    database: Session, integration: Integration, account: TradingAccount
) -> dict[str, object]:
    """Read one complete provider snapshot and atomically make it account truth.

    This entry point is deliberately read-only. It must be scheduled repeatedly by the worker in
    production, but is safe to invoke for the UI's explicit first verification.
    """

    profile = _profile(database, integration.id)
    selected = profile.selected_provider_account_id
    if not selected or account.provider_account_id != selected:
        raise InvalidTransition("select and bind a discovered broker account before verification")
    _require_mt5_provider(integration)
    try:
        mt5_source = _latest_managed_mt5_snapshot(database, integration)
        truth = NormalizedBrokerSnapshot(
            provider_account_id=selected,
            provider_event_id=_mt5_event_id(mt5_source, mt5_source.observed_at),
            balance=_decimal(mt5_source.balance),
            equity=_decimal(mt5_source.equity),
            realized_pl=Decimal("0"),
            floating_pl=Decimal("0"),
            observed_at=mt5_source.observed_at,
            source_cursor=None,
            source_window={"lookback_days": 2, "terminal_version": mt5_source.terminal_version},
            raw_evidence={
                "provider": "MT5_TERMINAL_BRIDGE",
                "terminal_version": mt5_source.terminal_version,
            },
            open_position_count=len(mt5_source.positions),
        )
        snapshot = commit_authoritative_snapshot(database, integration, account, truth)
        # The bridge remains read-only; this only projects its complete snapshot
        # into TraderX monitoring and never calls an MT5 trading method.
        from traderx.monitoring.reconciliation import project_mt5_positions

        project_mt5_positions(database, account, mt5_source.positions, mt5_source.deals)
    except (ValueError, InvalidTransition) as error:
        record_broker_failure(
            database,
            integration,
            account,
            reason_code="BROKER_SNAPSHOT_UNVERIFIED",
            detail="the broker did not provide a complete verified account snapshot",
        )
        raise InvalidTransition(
            "broker verification failed; TraderX remains in LOCKDOWN"
        ) from error
    return {
        "account_snapshot_id": str(snapshot.id),
        "quality": snapshot.quality,
        "observed_at": snapshot.observed_at.isoformat(),
    }


def integration_payload(
    integration: Integration, *, account_login: str, server: str
) -> dict[str, object]:
    status = (
        integration.state
        if integration.state in {"HEALTHY", "DEGRADED", "FAILED", "DISABLED"}
        else "DEGRADED"
    )
    return {
        "id": str(integration.id),
        "version": integration.version,
        "category": "BROKER",
        "provider": integration.provider,
        "name": integration.name,
        "status": status,
        "credential_hint": "configured"
        if integration.state != "DISABLED"
        else "configured; verification required",
        "mt5_account_login": account_login,
        "mt5_server": server,
    }


def _issue_managed_mt5_enrollment(
    integration: Integration,
    agent: Mt5BridgeAgent,
    *,
    configuration: dict[str, str],
) -> ManagedMt5Enrollment:
    enrollment_token = _new_agent_token()
    expires_at = datetime.now(UTC) + MT5_ENROLLMENT_LIFETIME
    agent.enrollment_token_digest = _token_digest(enrollment_token)
    agent.enrollment_expires_at = expires_at
    agent.agent_token_digest = None
    agent.enrolled_at = None
    agent.last_seen_at = None
    agent.last_snapshot_at = None
    agent.latest_snapshot = {}
    integration.state = "DISABLED"
    return ManagedMt5Enrollment(
        integration=integration,
        agent_id=agent.id,
        enrollment_token=enrollment_token,
        expires_at=expires_at,
        account_login=configuration["account_login"],
        server=configuration["server"],
    )


def _require_active_managed_mt5_integration(integration: Integration) -> None:
    _require_mt5_provider(integration)
    if integration.state == "REMOVED":
        raise InvalidTransition("the MT5 account integration has been removed")


def _require_mt5_provider(integration: Integration) -> None:
    if integration.provider != BrokerProvider.MT5_TERMINAL_BRIDGE:
        raise InvalidTransition("TraderX supports MetaTrader 5 account integrations only")


def _profile(database: Session, integration_id: UUID) -> BrokerIntegrationProfile:
    profile = database.scalar(
        select(BrokerIntegrationProfile).where(
            BrokerIntegrationProfile.integration_id == integration_id
        )
    )
    if profile is None:
        raise InvalidTransition("the broker integration profile does not exist")
    return profile


def _managed_mt5_configuration(*, account_login: str, server: str) -> dict[str, str]:
    login = account_login.strip()
    normalized_server = server.strip()
    if not login or not normalized_server:
        raise InvalidTransition("MT5 account login and broker server are required")
    return {"account_login": login, "server": normalized_server}


def _managed_mt5_name(configuration: dict[str, str]) -> str:
    return f"MT5 {configuration['server']} {configuration['account_login']}"


def _new_agent_token() -> str:
    return secrets.token_urlsafe(32)


def _token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _managed_mt5_agent(database: Session, integration_id: UUID) -> Mt5BridgeAgent:
    agent = database.scalar(
        select(Mt5BridgeAgent).where(Mt5BridgeAgent.integration_id == integration_id)
    )
    if agent is None:
        raise InvalidTransition("the managed MT5 bridge enrollment is unavailable")
    return agent


def _latest_managed_mt5_snapshot(database: Session, integration: Integration) -> ManagedMt5Snapshot:
    agent = _managed_mt5_agent(database, integration.id)
    now = datetime.now(UTC)
    if (
        agent.last_snapshot_at is None
        or now - _as_utc(agent.last_snapshot_at) > MT5_SNAPSHOT_MAX_AGE
    ):
        raise InvalidTransition("the MT5 bridge has not supplied a fresh verified account snapshot")
    payload = agent.latest_snapshot
    if not isinstance(payload, dict):
        raise InvalidTransition("the MT5 bridge snapshot is invalid")
    try:
        return ManagedMt5Snapshot(
            balance=_required_text(payload, "balance"),
            equity=_required_text(payload, "equity"),
            currency=_required_text(payload, "currency"),
            positions=_required_records(payload, "positions"),
            deals=_required_records(payload, "deals"),
            instruments=_required_records(payload, "instruments"),
            terminal_version=_required_text(payload, "terminal_version"),
            observed_at=_as_utc(agent.last_snapshot_at),
        )
    except (TypeError, ValueError) as error:
        raise InvalidTransition("the MT5 bridge snapshot is invalid") from error


def _required_records(value: dict[str, object], key: str) -> list[dict[str, object]]:
    records = value.get(key)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ValueError(f"{key} must be an array of records")
    return records


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _required_text(value: dict[str, object], key: str) -> str:
    text = _optional_text(value, key)
    if not text:
        raise InvalidTransition(f"{key} is required")
    return text


def _optional_text(value: dict[str, object], key: str) -> str | None:
    candidate = value.get(key)
    if not isinstance(candidate, str):
        return None
    return candidate.strip() or None


def _decimal(value: str) -> Decimal:
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("broker returned a non-finite amount")
    return parsed


def _mt5_event_id(snapshot: object, observed_at: datetime) -> str:
    return f"mt5-{getattr(snapshot, 'terminal_version', 'unknown')}-{observed_at.isoformat()}"
