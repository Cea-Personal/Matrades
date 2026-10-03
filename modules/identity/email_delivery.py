"""Private transactional-email boundary for authentication links."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlsplit

from packages.shared.config import Settings, get_settings


class AuthEmailUnavailable(RuntimeError):
    """Authentication email cannot be delivered safely."""


def delivery_mode(settings: Settings | None = None) -> str:
    config = settings or get_settings()
    if config.env == "development" and config.auth_dev_tokens_enabled:
        return "DEVELOPMENT_TOKEN"
    try:
        app_url = urlsplit(config.public_app_url or "")
        hostname = app_url.hostname
    except ValueError as exc:
        raise AuthEmailUnavailable("authentication email is not configured") from exc
    if (
        not hostname
        or app_url.scheme not in {"https", "http"}
        or (config.env != "development" and app_url.scheme != "https")
        or app_url.username is not None
        or app_url.password is not None
        or app_url.path not in {"", "/"}
        or bool(app_url.query or app_url.fragment)
        or not config.smtp_host
        or not config.smtp_username
        or not config.smtp_password
        or not config.smtp_from
    ):
        raise AuthEmailUnavailable("authentication email is not configured")
    return "SMTP"


def _send_smtp(message: EmailMessage, settings: Settings) -> None:
    password = settings.smtp_password
    assert password is not None
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=10, context=context
        ) as client:
            client.login(settings.smtp_username, password.get_secret_value())
            client.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            client.starttls(context=context)
            client.login(settings.smtp_username, password.get_secret_value())
            client.send_message(message)


async def deliver_auth_link(destination: str, purpose: str, token: str) -> str | None:
    """Return a browser-visible token only in explicitly enabled local development."""
    settings = get_settings()
    mode = delivery_mode(settings)
    if mode == "DEVELOPMENT_TOKEN":
        return token
    if purpose not in {"verify", "recover"}:
        raise ValueError("unsupported authentication email purpose")
    base = (settings.public_app_url or "").rstrip("/")
    link = f"{base}/auth#{purpose}={quote(token, safe='')}"
    try:
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = destination
        message["Subject"] = (
            "Verify your Matrades email"
            if purpose == "verify"
            else "Reset your Matrades password"
        )
        action = "verify your email" if purpose == "verify" else "reset your password"
        message.set_content(
            f"Open this one-time Matrades link to {action}:\n\n"
            f"{link}\n\nIf you did not request this, ignore this message.\n"
        )
        await asyncio.to_thread(_send_smtp, message, settings)
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        raise AuthEmailUnavailable("authentication email could not be delivered") from exc
    return None
