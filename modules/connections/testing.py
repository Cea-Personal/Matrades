"""Real, bounded provider health probes with redacted results."""

from __future__ import annotations

import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import httpx

from adapters.news.forex_factory import DEFAULT_FOREX_FACTORY_FEED, parse_forex_factory_payload
from modules.connections.models import ConnectionProbe, ConnectionProfile, ConnectionProvider

TWELVE_DATA_HEALTH_INTERVAL = timedelta(hours=1)


def twelve_data_check_due(last_checked: str | None, *, now: datetime | None = None) -> bool:
    """Return whether a Twelve Data probe may make another external API request."""
    if not last_checked:
        return True
    try:
        checked_at = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=UTC)
        observed_at = now or datetime.now(UTC)
        return observed_at - checked_at.astimezone(UTC) >= TWELVE_DATA_HEALTH_INTERVAL
    except (TypeError, ValueError):
        return True


def _mt5_headers(secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    signed = timestamp.encode() + b"." + nonce.encode() + b"."
    signature = hmac.new(secret.encode(), signed, sha256).hexdigest()
    return {"X-Timestamp": timestamp, "X-Nonce": nonce, "X-Signature": signature}


async def probe_connection(
    profile: ConnectionProfile,
    credential_secret: str | None,
    *,
    client: httpx.AsyncClient | None = None,
) -> ConnectionProbe:
    started = time.monotonic()
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=8, headers={"User-Agent": "Matrades/1"})
    capabilities: list[str] = []
    version: str | None = None
    fresh = False
    writes: bool | None = None
    try:
        if profile.provider == ConnectionProvider.TWELVE_DATA:
            # Validate only the credential/provider boundary here.  The market
            # research cycle is responsible for selecting an instrument and
            # requesting its quote/candles; a connection health check must not
            # invent or require a test pair.
            response = await http.get(
                "https://api.twelvedata.com/api_usage",
                headers={"Authorization": f"apikey {credential_secret}"},
            )
            body = response.json()
            if response.is_error or body.get("status") == "error":
                code = body.get("code") or response.status_code
                message = str(
                    body.get("message") or body.get("status") or "provider rejected request"
                )
                raise RuntimeError(f"Twelve Data {code}: {message}")
            if body.get("code") is not None and int(body["code"]) >= 400:
                raise RuntimeError(
                    f"Twelve Data {body['code']}: "
                    f"{body.get('message', 'provider rejected request')}"
                )
            capabilities = ["provider.authenticated", "forex.read", "metals.read", "candles.read"]
            # /api_usage is deliberately symbol-free.  A successful response
            # proves the key is accepted; instrument availability is checked
            # when research requests the selected market-research pair.
            fresh = bool(body) and body.get("status", "ok") != "error"
            if not fresh:
                raise RuntimeError("Twelve Data usage response did not confirm the credential")
        elif profile.provider == ConnectionProvider.COINBASE:
            response = await http.get("https://api.exchange.coinbase.com/time")
            response.raise_for_status()
            capabilities = ["crypto.read", "candles.read", "order_book.read"]
            fresh = bool(response.json().get("epoch"))
        elif profile.provider == ConnectionProvider.COINGECKO:
            response = await http.get("https://api.coingecko.com/api/v3/ping")
            response.raise_for_status()
            capabilities = ["crypto.discovery", "asset_metadata.read"]
            fresh = bool(response.json())
        elif profile.provider == ConnectionProvider.FRED:
            response = await http.get(
                "https://api.stlouisfed.org/fred/series",
                params={"series_id": "GDP", "api_key": credential_secret, "file_type": "json"},
            )
            response.raise_for_status()
            capabilities = ["macro.read"]
            fresh = bool(response.json().get("seriess"))
        elif profile.provider == ConnectionProvider.SERPAPI:
            response = await http.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": "site:youtube.com trading",
                    "api_key": credential_secret,
                    "num": 1,
                },
            )
            body = response.json()
            if response.is_error or body.get("error"):
                raise RuntimeError("SerpApi rejected the connection test")
            capabilities = ["search.read", "youtube.discovery", "transcript.read"]
            fresh = bool(body.get("search_metadata"))
        elif profile.provider == ConnectionProvider.FOREX_FACTORY:
            feed_url = str(profile.configuration.get("feed_url", DEFAULT_FOREX_FACTORY_FEED))
            response = await http.get(feed_url)
            response.raise_for_status()
            events = parse_forex_factory_payload(response.json())
            capabilities = ["news.read", "calendar.read", "forex_factory.scrape"]
            fresh = bool(events)
        elif profile.provider in {ConnectionProvider.CALENDAR, ConnectionProvider.NEWS}:
            base_url = str(profile.configuration["base_url"])
            response = await http.get(f"{base_url}/health")
            response.raise_for_status()
            capabilities = [
                "calendar.read" if profile.provider == ConnectionProvider.CALENDAR else "news.read"
            ]
            fresh = True
        else:
            bridge_url = str(profile.configuration["bridge_url"])
            response = await http.get(
                f"{bridge_url}/health", headers=_mt5_headers(credential_secret or "")
            )
            response.raise_for_status()
            body = response.json()
            capabilities = [str(value) for value in body.get("capabilities", [])]
            version = str(body.get("bridge_version")) if body.get("bridge_version") else None
            fresh = bool(body.get("fresh"))
            writes = bool(body.get("writes", True))
            if writes or not {"accounts.read", "positions.read"}.issubset(capabilities):
                raise RuntimeError("bridge does not satisfy the read-only capability contract")
        return ConnectionProbe(
            status="HEALTHY" if fresh else "STALE",
            latency_ms=int((time.monotonic() - started) * 1000),
            checked_at=datetime.now(UTC).isoformat(),
            capabilities=capabilities,
            version=version,
            fresh=fresh,
            writes=writes,
        )
    except Exception as exc:
        return ConnectionProbe(
            status="OFFLINE",
            latency_ms=int((time.monotonic() - started) * 1000),
            checked_at=datetime.now(UTC).isoformat(),
            capabilities=capabilities,
            version=version,
            fresh=False,
            writes=writes,
            safe_message=(
                f"{type(exc).__name__}: {str(exc)[:180]}"
                if isinstance(exc, RuntimeError)
                else f"{type(exc).__name__}: connection probe failed"
            ),
        )
    finally:
        if owns_client:
            await http.aclose()
