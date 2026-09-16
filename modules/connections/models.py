"""Typed, provider-neutral connection configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.shared.domain_types import ResearchLaneKey


class ConnectionProvider(StrEnum):
    TWELVE_DATA = "TWELVE_DATA"
    COINBASE = "COINBASE"
    COINGECKO = "COINGECKO"
    FRED = "FRED"
    CFTC = "CFTC"
    FUTURES_REFERENCE = "FUTURES_REFERENCE"
    CALENDAR = "CALENDAR"
    NEWS = "NEWS"
    FOREX_FACTORY = "FOREX_FACTORY"
    SERPAPI = "SERPAPI"
    OPENAI = "OPENAI"
    COHERE = "COHERE"
    MT5_BRIDGE = "MT5_BRIDGE"


PROVIDER_LABELS = {
    ConnectionProvider.TWELVE_DATA: "Twelve Data",
    ConnectionProvider.COINBASE: "Coinbase",
    ConnectionProvider.COINGECKO: "CoinGecko",
    ConnectionProvider.FRED: "FRED",
    ConnectionProvider.CFTC: "CFTC Commitments of Traders",
    ConnectionProvider.FUTURES_REFERENCE: "Futures reference / contract chain",
    ConnectionProvider.CALENDAR: "Calendar",
    ConnectionProvider.NEWS: "News",
    ConnectionProvider.FOREX_FACTORY: "Forex Factory calendar scraper",
    ConnectionProvider.SERPAPI: "SerpApi + YouTube transcript ingestion",
    ConnectionProvider.OPENAI: "OpenAI",
    ConnectionProvider.COHERE: "Cohere Rerank",
    ConnectionProvider.MT5_BRIDGE: "MT5 Bridge",
}


def validated_endpoint(value: str, *, allow_loopback_http: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an HTTP(S) URL")
    blocked = {"169.254.169.254", "metadata.google.internal"}
    if parsed.hostname.lower() in blocked:
        raise ValueError("metadata endpoints are prohibited")
    loopback = parsed.hostname.lower() in {
        "localhost",
        "127.0.0.1",
        "::1",
        "host.docker.internal",
        "gateway.docker.internal",
    }
    if parsed.scheme != "https" and not (allow_loopback_http and loopback):
        raise ValueError("remote endpoints must use HTTPS")
    return value.rstrip("/")


class ConnectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    provider: ConnectionProvider
    credential_id: UUID | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    active: bool = True

    @model_validator(mode="after")
    def provider_requirements(self) -> ConnectionProfile:
        if (
            self.provider
            in {
                ConnectionProvider.TWELVE_DATA,
                ConnectionProvider.FRED,
                ConnectionProvider.SERPAPI,
                ConnectionProvider.OPENAI,
                ConnectionProvider.COHERE,
                ConnectionProvider.MT5_BRIDGE,
            }
            and self.credential_id is None
        ):
            raise ValueError(f"{PROVIDER_LABELS[self.provider]} requires a credential")
        if self.provider == ConnectionProvider.MT5_BRIDGE:
            bridge_url = str(self.configuration.get("bridge_url", ""))
            if not bridge_url:
                raise ValueError("MT5 Bridge requires bridge_url")
            self.configuration["bridge_url"] = validated_endpoint(
                bridge_url, allow_loopback_http=True
            )
        if self.provider in {ConnectionProvider.CALENDAR, ConnectionProvider.NEWS}:
            base_url = str(self.configuration.get("base_url", ""))
            if not base_url:
                raise ValueError(f"{PROVIDER_LABELS[self.provider]} requires base_url")
            self.configuration["base_url"] = validated_endpoint(base_url)
        if self.provider == ConnectionProvider.FOREX_FACTORY:
            feed_url = str(self.configuration.get("feed_url", ""))
            if feed_url:
                self.configuration["feed_url"] = validated_endpoint(feed_url)
        return self


class ConnectionProbe(BaseModel):
    status: str
    latency_ms: int = Field(ge=0)
    checked_at: str
    capabilities: list[str] = Field(default_factory=list)
    version: str | None = None
    fresh: bool = False
    writes: bool | None = None
    safe_message: str | None = None


class MarketDataCapability(StrEnum):
    INSTRUMENT_DIRECTORY = "INSTRUMENT_DIRECTORY"
    DISCOVERY = "DISCOVERY"
    QUOTE = "QUOTE"
    TRADES = "TRADES"
    CANDLES = "CANDLES"
    ORDER_BOOK = "ORDER_BOOK"
    CONTRACT_DETAILS = "CONTRACT_DETAILS"
    FUTURES_CHAIN = "FUTURES_CHAIN"
    OPEN_INTEREST = "OPEN_INTEREST"
    FUNDING = "FUNDING"
    CORPORATE_ACTIONS = "CORPORATE_ACTIONS"
    BROKER_TRADABILITY = "BROKER_TRADABILITY"
    ACCOUNT_BALANCES = "ACCOUNT_BALANCES"


class ProviderAuthorityPurpose(StrEnum):
    DISCOVERY = "DISCOVERY"
    REFERENCE = "REFERENCE"
    EXECUTABLE_QUOTE = "EXECUTABLE_QUOTE"
    HISTORY = "HISTORY"
    CONTRACT_TERMS = "CONTRACT_TERMS"
    BROKER_RECONCILIATION = "BROKER_RECONCILIATION"


class ResearchMatrixVersion(BaseModel):
    account_id: UUID
    version: int = Field(default=1, ge=1)
    lanes: list[ResearchLaneKey] = Field(default_factory=list, min_length=1, max_length=12)
    enabled: dict[str, bool] = Field(default_factory=dict)
    schedule: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_lanes(self) -> ResearchMatrixVersion:
        keys = [lane.as_string() for lane in self.lanes]
        if len(keys) != len(set(keys)):
            raise ValueError("research matrix lanes must be unique")
        return self


class ProviderBindingInput(BaseModel):
    account_id: UUID
    lane: ResearchLaneKey
    capability: MarketDataCapability
    authority_purpose: ProviderAuthorityPurpose
    connection_id: UUID
    priority: int = Field(default=1, ge=1)
    provider_venue: str | None = None
    freshness_policy: dict[str, Any] = Field(default_factory=dict)


class ProviderBinding(ProviderBindingInput):
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    verification_status: str = "UNVERIFIED"
    effective_from: str | None = None
