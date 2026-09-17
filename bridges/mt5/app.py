from __future__ import annotations

import hashlib
import hmac
import os
import time
from base64 import b64encode
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from bridges.mt5.commands import BridgeCommand, BridgeCommandQueue, BridgeReceipt
from modules.mt5.desktop_runtime import MT5StartupError, ensure_local_mt5_started
from packages.broker_sdk.schemas import (
    BrokerInstrument,
    BrokerMarketDataSnapshot,
    BrokerSnapshot,
)


def verify(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: bytes,
    window: int = 30,
    nonce: str = "",
) -> None:
    try:
        fresh = abs(time.time() - int(timestamp)) <= window
    except (TypeError, ValueError):
        fresh = False
    if not fresh:
        raise HTTPException(401, "stale signed request")
    signed = timestamp.encode() + (b"." + nonce.encode() if nonce else b"") + b"." + body
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid signature")


def create_app(
    reader: object | None = None,
    secret: bytes | None = None,
    *,
    authority_url: str | None = None,
    authority_token: str | None = None,
    authority_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Matrades bounded MT5 execution bridge")
    bridge_secret = (
        secret or os.environ.get("MATRADES_MT5_BRIDGE_SECRET", "development-mt5-secret").encode()
    )
    credential_authority_url = (
        authority_url
        if authority_url is not None
        else os.environ.get("MATRADES_MT5_AUTHORITY_URL", "")
    )
    credential_authority_token = (
        authority_token
        if authority_token is not None
        else os.environ.get("MATRADES_MT5_AUTHORITY_TOKEN", "")
    )
    trusted_client_fingerprint = os.environ.get("MATRADES_MT5_CLIENT_CERT_FINGERPRINT", "")
    runtime_control_token = os.environ.get("MATRADES_MT5_RUNTIME_CONTROL_TOKEN", "")
    seen_nonces: dict[str, float] = {}
    sequences: dict[UUID, int] = {}
    latest_snapshots: dict[UUID, dict] = {}
    latest_received: dict[UUID, float] = {}
    latest_history: dict[UUID, list] = {}
    latest_market_data: dict[UUID, dict] = {}
    latest_market_received: dict[UUID, float] = {}
    command_queue = BridgeCommandQueue(os.environ.get("MATRADES_MT5_COMMAND_QUEUE_PATH"))
    app.state.command_queue = command_queue
    runtime_status_path = Path(
        os.environ.get("MATRADES_MT5_RUNTIME_STATUS_PATH", "/tmp/matrades-mt5-runtime.status")
    )

    @app.get("/")
    async def runtime_status() -> dict[str, str]:
        try:
            state = runtime_status_path.read_text(encoding="utf-8").strip()
        except OSError:
            state = "unknown"
        if state not in {
            "starting",
            "initializing_display",
            "initializing_wine",
            "installing_mt5",
            "starting_terminal",
            "terminal_started",
            "wine_failed",
            "display_failed",
            "installer_missing",
            "installer_download_failed",
            "installer_failed",
            "terminal_missing",
            "terminal_failed",
        }:
            state = "unknown"
        return {
            "service": "matrades-mt5-bridge",
            "runtime_status": state,
            "detail": "This endpoint reports bridge status; it does not display the MT5 desktop.",
        }

    async def verify_with_credential_authority(
        body: bytes, timestamp: str, nonce: str, signature: str
    ) -> None:
        try:
            if abs(time.time() - int(timestamp)) > 30:
                raise HTTPException(401, "stale signed request")
        except (TypeError, ValueError) as exc:
            raise HTTPException(401, "stale signed request") from exc
        payload = {
            "body_base64": b64encode(body).decode(),
            "timestamp": timestamp,
            "nonce": nonce,
            "signature": signature,
        }
        owns_client = authority_client is None
        client = authority_client or httpx.AsyncClient(timeout=5)
        try:
            response = await client.post(
                credential_authority_url,
                json=payload,
                headers={"X-Matrades-Service-Token": credential_authority_token},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(503, "MT5 credential authority unavailable") from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code == 401:
            raise HTTPException(401, "invalid signature")
        if response.is_error:
            raise HTTPException(503, "MT5 credential authority unavailable")

    async def authenticate(
        request: Request,
        x_timestamp: str = Header(),
        x_nonce: str = Header(),
        x_signature: str = Header(),
        x_client_cert_fingerprint: str | None = Header(default=None),
    ) -> None:
        now = time.time()
        for value, observed in tuple(seen_nonces.items()):
            if now - observed > 60:
                seen_nonces.pop(value, None)
        if x_nonce in seen_nonces:
            raise HTTPException(401, "replayed signed request")
        if trusted_client_fingerprint and not hmac.compare_digest(
            x_client_cert_fingerprint or "", trusted_client_fingerprint
        ):
            raise HTTPException(401, "client certificate verification failed")
        body = await request.body()
        if credential_authority_url:
            await verify_with_credential_authority(body, x_timestamp, x_nonce, x_signature)
        else:
            verify(body, x_timestamp, x_signature, bridge_secret, nonce=x_nonce)
        seen_nonces[x_nonce] = now

    @app.get("/health")
    async def health(_: None = Depends(authenticate)) -> dict:
        now = time.time()
        fresh = bool(reader) or any(now - observed <= 15 for observed in latest_received.values())
        capabilities = [
            "accounts.read",
            "positions.read",
            "history.read",
            "commands.poll",
            "commands.receipt",
        ]
        market_fresh = bool(reader and hasattr(reader, "symbols")) or any(
            now - observed <= 180 for observed in latest_market_received.values()
        )
        # Discovery is advertised only after broker-native symbol data is available.
        if market_fresh:
            capabilities.extend(
                [
                    "market.discovery",
                    "instruments.read",
                    "quotes.read",
                    "candles.read",
                    "contract_terms.read",
                ]
            )
        return {
            "status": "healthy" if fresh else "waiting_for_ea",
            "fresh": fresh,
            "market_data_fresh": market_fresh,
            "bridge_version": "1.0.0",
            "observed_at": datetime.now(UTC).isoformat(),
            "capabilities": capabilities,
            "writes": True,
        }

    @app.post("/runtime/start")
    async def start_runtime(
        x_runtime_token: str | None = Header(
            default=None, alias="X-Matrades-MT5-Runtime-Token"
        ),
    ) -> dict[str, object]:
        """Start the Wine/MT5 process on the cloud host running this bridge."""
        if not runtime_control_token or not hmac.compare_digest(
            x_runtime_token or "", runtime_control_token
        ):
            raise HTTPException(401, "invalid MT5 runtime control token")
        try:
            result = await ensure_local_mt5_started()
        except MT5StartupError as exc:
            raise HTTPException(503, "MT5 runtime could not be started") from exc
        if result.status != "ready":
            raise HTTPException(503, "MT5 runtime is not configured on the cloud host")
        return {
            "status": result.status,
            "wine_started": result.wine_started,
            "terminal_started": result.terminal_started,
            "detail": result.detail,
        }

    @app.post("/market-data/ingest")
    async def ingest_market_data(request: Request, _: None = Depends(authenticate)) -> dict:
        """Accept broker-native metal listings, quotes, terms, and bounded candles."""
        try:
            payload = BrokerMarketDataSnapshot.model_validate(await request.json())
        except Exception as exc:  # noqa: BLE001 - malformed EA payload is a client error
            raise HTTPException(422, "invalid broker market data snapshot") from exc
        previous = latest_market_data.get(payload.account_id)
        if previous is not None and payload.sequence <= int(previous["sequence"]):
            previous_observed_at = datetime.fromisoformat(str(previous["observed_at"]))
            restarted = payload.sequence == 1 and payload.observed_at > previous_observed_at
            if not restarted:
                raise HTTPException(409, "out-of-order or replayed market data snapshot")
        latest_market_data[payload.account_id] = payload.model_dump(mode="json")
        latest_market_received[payload.account_id] = time.time()
        return {
            "accepted": True,
            "account_id": str(payload.account_id),
            "sequence": payload.sequence,
            "instrument_count": len(payload.instruments),
        }

    @app.post("/ingest")
    async def ingest(request: Request, _: None = Depends(authenticate)) -> dict:
        """Accept a signed, read-only snapshot published by the MT5 EA."""
        try:
            payload = BrokerSnapshot.model_validate(await request.json())
        except Exception as exc:  # noqa: BLE001 - malformed EA payload is a client error
            raise HTTPException(422, "invalid broker snapshot") from exc
        previous = latest_snapshots.get(payload.account_id)
        if previous is not None and payload.sequence <= int(previous["sequence"]):
            previous_observed_at = datetime.fromisoformat(str(previous["observed_at"]))
            restarted = payload.sequence == 1 and payload.observed_at > previous_observed_at
            if not restarted:
                raise HTTPException(409, "out-of-order or replayed broker snapshot")
        latest_snapshots[payload.account_id] = payload.model_dump(mode="json")
        latest_received[payload.account_id] = time.time()
        latest_history[payload.account_id] = []
        return {
            "accepted": True,
            "account_id": str(payload.account_id),
            "sequence": payload.sequence,
        }

    @app.get("/positions")
    async def positions(account_id: UUID | None = None, _: None = Depends(authenticate)) -> list:
        if reader:
            return list(reader.positions())
        if account_id and account_id in latest_snapshots:
            return list(latest_snapshots[account_id]["positions"])
        return [
            position for snapshot in latest_snapshots.values() for position in snapshot["positions"]
        ]

    @app.get("/account")
    async def account(account_id: UUID | None = None, _: None = Depends(authenticate)) -> dict:
        if reader:
            return dict(reader.account())
        if account_id and account_id in latest_snapshots:
            snapshot = latest_snapshots[account_id]
            return {
                "balance": snapshot["balance"],
                "equity": snapshot["equity"],
                "realized_daily_pnl": snapshot["realized_daily_pnl"],
            }
        return {}

    @app.get("/history")
    async def history(account_id: UUID | None = None, _: None = Depends(authenticate)) -> list:
        if reader:
            return list(reader.history())
        return list(latest_history.get(account_id, [])) if account_id else []

    @app.get("/snapshot")
    async def snapshot(account_id: UUID, _: None = Depends(authenticate)) -> dict:
        if reader:
            account = dict(reader.account())
            positions_value = list(reader.positions())
            sequences[account_id] = sequences.get(account_id, 0) + 1
            sequence = sequences[account_id]
        elif account_id in latest_snapshots:
            return latest_snapshots[account_id]
        else:
            account = {}
            positions_value = []
            sequences[account_id] = sequences.get(account_id, 0) + 1
            sequence = sequences[account_id]
        return {
            "message_id": str(uuid4()),
            "account_id": str(account_id),
            "sequence": sequence,
            "observed_at": datetime.now(UTC).isoformat(),
            "balance": account.get("balance", 0),
            "equity": account.get("equity", 0),
            "realized_daily_pnl": account.get("realized_daily_pnl"),
            "positions": positions_value,
            "signature": "response-over-authenticated-channel",
        }

    @app.get("/instruments")
    async def instruments(
        account_id: UUID | None = None, _: None = Depends(authenticate)
    ) -> list[dict]:
        if reader and hasattr(reader, "symbols"):
            values = []
            for item in reader.symbols():
                symbol = getattr(item, "name", str(item))
                info = reader.symbol(symbol)
                if isinstance(info, dict):
                    values.append(info)
                else:
                    values.append({"symbol": symbol, "raw": str(info)})
            return values
        snapshots = (
            [latest_market_data[account_id]]
            if account_id and account_id in latest_market_data
            else list(latest_market_data.values())
        )
        return [
            {key: value for key, value in instrument.items() if key != "candles"}
            for snapshot in snapshots
            for instrument in snapshot["instruments"]
        ]

    @app.get("/market-data")
    async def market_data(account_id: UUID, _: None = Depends(authenticate)) -> dict:
        if account_id not in latest_market_data:
            raise HTTPException(503, "MT5 EA has not published market data for this account")
        return latest_market_data[account_id]

    @app.get("/symbol-details")
    async def symbol_details(
        account_id: UUID, symbol: str, _: None = Depends(authenticate)
    ) -> dict:
        if reader and hasattr(reader, "symbol"):
            info = reader.symbol(symbol)
            if isinstance(info, BrokerInstrument):
                return info.model_dump(mode="json")
            if isinstance(info, dict):
                return info
            return {"symbol": symbol, "raw": str(info), "account_id": str(account_id)}
        snapshot = latest_market_data.get(account_id)
        if snapshot:
            for instrument in snapshot["instruments"]:
                if instrument["symbol"].upper() == symbol.upper():
                    return instrument
        raise HTTPException(404, "symbol is not present in the latest MT5 market snapshot")

    @app.get("/events")
    async def events(
        account_id: UUID,
        after_sequence: int = 0,
        _: None = Depends(authenticate),
    ) -> dict:
        current = sequences.get(account_id, 0)
        return {
            "account_id": str(account_id),
            "after_sequence": after_sequence,
            "current_sequence": current,
            "events": [],
        }

    @app.get("/commands/poll")
    async def poll_commands(
        account_id: UUID, limit: int = 20, _: None = Depends(authenticate)
    ) -> list[dict]:
        commands = []
        for item in command_queue.poll(account_id, min(limit, 50)):
            # The EA has a deliberately small JSON parser. Flatten the bounded
            # postcondition so nested payload braces cannot truncate a command.
            data = item.model_dump(mode="json")
            payload = data.pop("payload", {})
            data.update(payload)
            commands.append(data)
        return commands

    @app.post("/commands", status_code=202)
    async def enqueue_command(
        command: BridgeCommand, _: None = Depends(authenticate)
    ) -> dict:
        if not command.authorization_id or not command.authorization_digest:
            raise HTTPException(403, "server authorization is required")
        return command_queue.enqueue(command).model_dump(mode="json")

    @app.post("/commands/receipts")
    async def command_receipt(
        receipt: BridgeReceipt, _: None = Depends(authenticate)
    ) -> dict:
        return command_queue.receipt(receipt).model_dump(mode="json")

    return app


app = create_app()
