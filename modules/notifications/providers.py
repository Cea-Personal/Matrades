"""Provider clients for outbound Telegram and Pushover notifications."""

from __future__ import annotations

from typing import Any

import httpx

SUPPORTED_PROVIDERS = {"TELEGRAM", "PUSHOVER"}


class NotificationDeliveryError(RuntimeError):
    """A provider rejected or could not receive a notification."""


def _safe_error(provider: str, response: httpx.Response) -> NotificationDeliveryError:
    try:
        payload = response.json()
        message = str(
            payload.get("description")
            or payload.get("errors")
            or payload.get("error")
            or "provider rejected request"
        )
    except (ValueError, TypeError):
        message = "provider rejected request"
    return NotificationDeliveryError(
        f"{provider} notification failed ({response.status_code}): {message[:180]}"
    )


async def send_notification(
    provider: str,
    secret: str,
    destination: str,
    *,
    title: str,
    message: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Send a message and return a redacted provider receipt."""
    normalized = provider.upper()
    if normalized not in SUPPORTED_PROVIDERS:
        raise NotificationDeliveryError("unsupported notification provider")
    if not secret or not destination:
        raise NotificationDeliveryError("notification credentials are incomplete")
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=10, headers={"User-Agent": "Matrades/1"})
    try:
        if normalized == "TELEGRAM":
            response = await http.post(
                f"https://api.telegram.org/bot{secret}/sendMessage",
                json={"chat_id": destination, "text": f"{title}\n\n{message}"[:4096]},
            )
            if response.is_error:
                raise _safe_error(normalized, response)
            payload = response.json()
            if not payload.get("ok"):
                raise _safe_error(normalized, response)
            return {
                "provider": normalized,
                "status": "DELIVERED",
                "message_id": payload.get("result", {}).get("message_id"),
            }

        response = await http.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": secret,
                "user": destination,
                "title": title[:250],
                "message": message[:1024],
            },
        )
        if response.is_error:
            raise _safe_error(normalized, response)
        payload = response.json()
        if int(payload.get("status", 0)) != 1:
            raise _safe_error(normalized, response)
        return {"provider": normalized, "status": "DELIVERED", "request": payload.get("request")}
    except httpx.HTTPError as exc:
        raise NotificationDeliveryError(f"{normalized} notification request failed") from exc
    finally:
        if owns_client:
            await http.aclose()
