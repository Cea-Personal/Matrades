from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.broker_model import (
    BrokerDiscoveredAccount,
    BrokerIntegrationProfile,
    BrokerProvider,
)
from traderx.integrations.crypto import EncryptedSecret, SecretBox
from traderx.integrations.model import CredentialVersion, Integration, IntegrationHealthObservation
from traderx.integrations.mt5_bridge import Mt5BridgeAdapter, Mt5BridgeError, Mt5BridgeIdentity
from traderx.integrations.oanda_v20 import OandaAdapterError, OandaEnvironment, OandaV20Adapter
from traderx.integrations.reconciliation import (
    NormalizedBrokerSnapshot,
    commit_authoritative_snapshot,
    record_broker_failure,
)
from traderx.shared.config import get_settings
from traderx.shared.types import InvalidTransition

BROKER_CAPABILITIES = ["ACCOUNT_READ", "POSITION_READ", "DEAL_READ", "INSTRUMENT_READ"]


@dataclass(frozen=True, slots=True)
class BrokerIntegrationCommand:
    provider: BrokerProvider
    configuration: dict[str, object]
    credentials: dict[str, object]
    display_name: str | None = None


def create_broker_integration(
    database: Session, actor: Actor, command: BrokerIntegrationCommand
) -> Integration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    configuration = _validated_configuration(command.provider, command.configuration)
    _validated_credentials(command.provider, command.credentials)
    integration = Integration(
        name=command.display_name or _default_name(command.provider, configuration),
        provider=command.provider,
        state="DISABLED",
        capabilities=BROKER_CAPABILITIES,
        official_source=True,
    )
    database.add(integration)
    database.flush()
    database.add(
        BrokerIntegrationProfile(
            integration_id=integration.id,
            provider=command.provider,
            environment=configuration.get("environment"),
            bridge_url=configuration.get("bridge_url"),
            bridge_id=configuration.get("bridge_id"),
            account_login=configuration.get("account_login"),
            server=configuration.get("server"),
            configuration=configuration,
        )
    )
    _store_credential(database, integration.id, command.credentials)
    database.flush()
    return integration


def rotate_broker_credential(
    database: Session, actor: Actor, integration: Integration, credentials: dict[str, object]
) -> None:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.rotate_credential", require_mfa=True)
    provider = _provider(integration)
    _validated_credentials(provider, credentials)
    for previous in database.scalars(
        select(CredentialVersion).where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
    ):
        previous.active = False
    _store_credential(database, integration.id, credentials)
    integration.state = "DISABLED"
    database.flush()


def active_broker_credentials(database: Session, integration: Integration) -> dict[str, object]:
    credential = database.scalar(
        select(CredentialVersion)
        .where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
        .order_by(CredentialVersion.created_at.desc())
    )
    if credential is None:
        raise InvalidTransition("the broker integration has no active credential")
    try:
        packed = json.loads(credential.encrypted_value)
        secret = EncryptedSecret(
            ciphertext_b64=packed["ciphertext_b64"],
            nonce_b64=packed["nonce_b64"],
            key_version=credential.key_version,
            aad=packed["aad"],
        )
        value = _secret_box().decrypt(secret)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise InvalidTransition("the broker credential cannot be decrypted") from error
    if not isinstance(value, dict):
        raise InvalidTransition("the broker credential is invalid")
    return value


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
            .order_by(BrokerDiscoveredAccount.display_name, BrokerDiscoveredAccount.provider_account_id)
        )
    ]


def test_broker_integration(database: Session, integration: Integration) -> list[dict[str, object]]:
    """Perform a bounded read-only credential test and retain only safe discovered-account data."""

    provider = _provider(integration)
    profile = _profile(database, integration.id)
    credentials = active_broker_credentials(database, integration)
    try:
        candidates: list[dict[str, object]]
        if provider is BrokerProvider.OANDA_V20:
            oanda_adapter = OandaV20Adapter(
                personal_access_token=_required_text(credentials, "personal_access_token"),
                environment=OandaEnvironment(profile.environment or "PRACTICE"),
            )
            try:
                candidates = [
                    {
                        "provider_account_id": candidate.provider_account_id,
                        "display_name": candidate.display_name,
                        "currency": candidate.currency,
                        "account_mode": candidate.account_mode,
                    }
                    for candidate in oanda_adapter.discover_accounts()
                ]
            finally:
                oanda_adapter.close()
        else:
            mt5_adapter = Mt5BridgeAdapter(
                identity=Mt5BridgeIdentity(
                    bridge_url=_required_text({"bridge_url": profile.bridge_url}, "bridge_url"),
                    account_login=_required_text({"account_login": profile.account_login}, "account_login"),
                    server=_required_text({"server": profile.server}, "server"),
                ),
                bridge_client_secret=_required_text(credentials, "bridge_client_secret"),
            )
            try:
                mt5_adapter.test_connection()
                snapshot = mt5_adapter.get_account_snapshot(
                    _required_text({"login": profile.account_login}, "login")
                )
                candidates = [
                    {
                        "provider_account_id": _required_text({"login": profile.account_login}, "login"),
                        "display_name": f"{profile.server} {profile.account_login}",
                        "currency": snapshot.currency,
                        "account_mode": "UNKNOWN",
                    }
                ]
            finally:
                mt5_adapter.close()
    except (OandaAdapterError, Mt5BridgeError, ValueError) as error:
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
    provider = _provider(integration)
    credentials = active_broker_credentials(database, integration)
    try:
        if provider is BrokerProvider.OANDA_V20:
            oanda_adapter = OandaV20Adapter(
                personal_access_token=_required_text(credentials, "personal_access_token"),
                environment=OandaEnvironment(profile.environment or "PRACTICE"),
            )
            try:
                oanda_source = oanda_adapter.bootstrap_account(selected)
            finally:
                oanda_adapter.close()
            truth = NormalizedBrokerSnapshot(
                provider_account_id=oanda_source.provider_account_id,
                provider_event_id=oanda_source.cursor,
                balance=_decimal(oanda_source.balance),
                equity=_decimal(oanda_source.equity),
                realized_pl=_decimal(oanda_source.realized_pl),
                floating_pl=_decimal(oanda_source.floating_pl),
                observed_at=oanda_source.observed_at,
                source_cursor=oanda_source.cursor,
                source_window={},
                raw_evidence={"provider": "OANDA_V20", "equity_source": oanda_source.equity_source},
                open_position_count=oanda_source.open_position_count,
            )
        else:
            mt5_adapter = Mt5BridgeAdapter(
                identity=Mt5BridgeIdentity(
                    bridge_url=_required_text({"bridge_url": profile.bridge_url}, "bridge_url"),
                    account_login=_required_text({"account_login": profile.account_login}, "account_login"),
                    server=_required_text({"server": profile.server}, "server"),
                ),
                bridge_client_secret=_required_text(credentials, "bridge_client_secret"),
            )
            try:
                mt5_source = mt5_adapter.get_account_snapshot(selected)
            finally:
                mt5_adapter.close()
            observed_at = datetime.now(UTC)
            truth = NormalizedBrokerSnapshot(
                provider_account_id=selected,
                provider_event_id=_mt5_event_id(mt5_source, observed_at),
                balance=_decimal(mt5_source.balance),
                equity=_decimal(mt5_source.equity),
                realized_pl=Decimal("0"),
                floating_pl=Decimal("0"),
                observed_at=observed_at,
                source_cursor=None,
                source_window={"lookback_days": 2, "terminal_version": mt5_source.terminal_version},
                raw_evidence={"provider": "MT5_TERMINAL_BRIDGE", "terminal_version": mt5_source.terminal_version},
                open_position_count=len(mt5_source.positions),
            )
        snapshot = commit_authoritative_snapshot(database, integration, account, truth)
    except (OandaAdapterError, Mt5BridgeError, ValueError, InvalidTransition) as error:
        record_broker_failure(
            database,
            integration,
            account,
            reason_code="BROKER_SNAPSHOT_UNVERIFIED",
            detail="the broker did not provide a complete verified account snapshot",
        )
        raise InvalidTransition("broker verification failed; TraderX remains in LOCKDOWN") from error
    return {
        "account_snapshot_id": str(snapshot.id),
        "quality": snapshot.quality,
        "observed_at": snapshot.observed_at.isoformat(),
    }


def integration_payload(integration: Integration) -> dict[str, object]:
    status = integration.state if integration.state in {"HEALTHY", "DEGRADED", "FAILED", "DISABLED"} else "DEGRADED"
    return {
        "id": str(integration.id),
        "version": integration.version,
        "category": "BROKER",
        "provider": integration.provider,
        "status": status,
        "credential_hint": "configured" if integration.state != "DISABLED" else "configured; verification required",
    }


def _store_credential(database: Session, integration_id: UUID, value: dict[str, object]) -> None:
    secret = _secret_box().encrypt(value, aad=f"broker-integration:{integration_id}")
    database.add(
        CredentialVersion(
            integration_id=integration_id,
            key_version=secret.key_version,
            encrypted_value=json.dumps(
                {
                    "ciphertext_b64": secret.ciphertext_b64,
                    "nonce_b64": secret.nonce_b64,
                    "aad": secret.aad,
                },
                sort_keys=True,
            ),
            active=True,
            created_at=datetime.now(UTC),
        )
    )


def _validated_configuration(provider: BrokerProvider, value: dict[str, object]) -> dict[str, object]:
    if provider is BrokerProvider.OANDA_V20:
        environment = str(value.get("environment", "PRACTICE")).upper()
        if environment not in {"PRACTICE", "LIVE"}:
            raise InvalidTransition("OANDA environment must be PRACTICE or LIVE")
        if environment == "LIVE" and value.get("live_confirmed") is not True:
            raise InvalidTransition("explicit confirmation is required before connecting OANDA Live")
        return {"environment": environment}
    required = ("bridge_url", "bridge_id", "account_login", "server")
    if any(not _optional_text(value, key) for key in required):
        raise InvalidTransition("MT5 bridge URL, identity, account login, and server are required")
    bridge_url = _required_text(value, "bridge_url")
    if not bridge_url.startswith("https://"):
        raise InvalidTransition("MT5 bridge URL must use HTTPS")
    return {key: _required_text(value, key) for key in required}


def _validated_credentials(provider: BrokerProvider, value: dict[str, object]) -> None:
    key = "personal_access_token" if provider is BrokerProvider.OANDA_V20 else "bridge_client_secret"
    if not _optional_text(value, key):
        raise InvalidTransition(f"{key} is required")


def _provider(integration: Integration) -> BrokerProvider:
    try:
        return BrokerProvider(integration.provider)
    except ValueError as error:
        raise InvalidTransition("the integration is not a supported broker provider") from error


def _profile(database: Session, integration_id: UUID) -> BrokerIntegrationProfile:
    profile = database.scalar(
        select(BrokerIntegrationProfile).where(BrokerIntegrationProfile.integration_id == integration_id)
    )
    if profile is None:
        raise InvalidTransition("the broker integration profile does not exist")
    return profile


def _default_name(provider: BrokerProvider, configuration: dict[str, object]) -> str:
    suffix = configuration.get("environment") or configuration.get("bridge_id")
    return f"{provider} {suffix}"


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


def _secret_box() -> SecretBox:
    return SecretBox(get_settings().encryption_key_b64.get_secret_value())


def _decimal(value: str) -> Decimal:
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError("broker returned a non-finite amount")
    return parsed


def _mt5_event_id(snapshot: object, observed_at: datetime) -> str:
    return f"mt5-{getattr(snapshot, 'terminal_version', 'unknown')}-{observed_at.isoformat()}"
