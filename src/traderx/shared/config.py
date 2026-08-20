from __future__ import annotations

from functools import lru_cache
from os import getenv
from pathlib import Path

from pydantic import BaseModel, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from sqlalchemy.engine import make_url


def database_url_from_environment() -> str:
    """Resolve the optional database password secret without logging it."""
    raw_url = getenv(
        "TRADERX_DATABASE_URL", "postgresql+psycopg://traderx:traderx@localhost/traderx"
    )
    password_file = getenv("TRADERX_DATABASE_PASSWORD_FILE")
    if not password_file:
        return raw_url

    password = Path(password_file).read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("TRADERX_DATABASE_PASSWORD_FILE must contain a password")
    return make_url(raw_url).set(password=password).render_as_string(hide_password=False)


def secret_from_environment(name: str, default: str) -> str:
    """Load a startup secret from an environment value or a Docker secret file."""

    secret_file = getenv(f"{name}_FILE")
    if secret_file:
        value = Path(secret_file).read_text(encoding="utf-8").strip()
        if not value:
            raise ValueError(f"{name}_FILE must contain a value")
        return value
    return getenv(name, default)


class Settings(BaseModel):
    """Non-secret runtime configuration; secrets are injected only at process startup."""

    environment: str = Field(default="development", pattern=r"^(development|test|production)$")
    database_url: PostgresDsn
    redis_url: RedisDsn
    session_pepper: SecretStr = SecretStr("development-only-change-me")
    encryption_key_b64: SecretStr = SecretStr("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    session_idle_minutes: int = Field(default=30, ge=5, le=1440)
    session_absolute_hours: int = Field(default=12, ge=1, le=720)
    provider_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    provider_read_timeout_seconds: int = Field(default=30, ge=1, le=180)
    specialist_maximum_attempts: int = Field(default=3, ge=1, le=3)
    llm_attempt_timeout_seconds: int = Field(default=180, ge=1, le=180)
    llm_overall_timeout_seconds: int = Field(default=600, ge=1, le=600)
    market_research_due_scan_seconds: int = Field(default=60, ge=15, le=300)
    market_research_minimum_interval_seconds: int = Field(default=3600, ge=3600, le=2592000)
    market_research_maximum_interval_seconds: int = Field(default=2592000, ge=3600, le=2592000)
    provider_retention_posture: str = Field(
        default="STANDARD", pattern=r"^(STANDARD|ADMIN_VERIFIED)$"
    )
    # This is intentionally off by default.  It controls a local-only scraper
    # experiment and is not a provider entitlement or an approval to use its
    # output for live decisions.
    experimental_calendar_scraper_enabled: bool = False

    @field_validator("session_pepper", "encryption_key_b64")
    @classmethod
    def reject_default_secrets_in_production(cls, value: SecretStr) -> SecretStr:
        return value

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            environment=getenv("TRADERX_ENVIRONMENT", "development"),
            database_url=database_url_from_environment(),
            redis_url=getenv("TRADERX_REDIS_URL", "redis://localhost:6379/0"),
            session_pepper=SecretStr(
                secret_from_environment("TRADERX_SESSION_PEPPER", "development-only-change-me")
            ),
            encryption_key_b64=SecretStr(
                secret_from_environment(
                    "TRADERX_ENCRYPTION_KEY_B64",
                    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                )
            ),
            experimental_calendar_scraper_enabled=(
                getenv("TRADERX_ENABLE_EXPERIMENTAL_CALENDAR_SCRAPER", "false").lower()
                == "true"
            ),
        )

    def validate_startup(self) -> None:
        if (
            self.market_research_minimum_interval_seconds
            > self.market_research_maximum_interval_seconds
        ):
            raise ValueError("market research interval bounds are invalid")
        if self.environment == "production":
            if self.experimental_calendar_scraper_enabled:
                raise ValueError(
                    "TRADERX_ENABLE_EXPERIMENTAL_CALENDAR_SCRAPER cannot be enabled in production"
                )
            if self.session_pepper.get_secret_value() == "development-only-change-me":
                raise ValueError("TRADERX_SESSION_PEPPER must be set in production")
            if (
                self.encryption_key_b64.get_secret_value()
                == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
            ):
                raise ValueError("TRADERX_ENCRYPTION_KEY_B64 must be set in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings.from_environment()
    settings.validate_startup()
    return settings
