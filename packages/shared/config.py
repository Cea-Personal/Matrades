from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MATRADES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./matrades.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: SecretStr = Field(default=SecretStr("development-only-secret-key-change-me"))
    mt5_authority_token: SecretStr = Field(
        default=SecretStr("development-mt5-authority-token")
    )
    blob_root: Path = Path("data/blobs")
    codex_enabled: bool = True
    codex_binary: str = "codex"
    default_codex_model: str = "gpt-5.6-terra"
    mt5_auto_start_enabled: bool = True
    mt5_wine_binary: str = "wine"
    mt5_wineboot_binary: str = "wineboot"
    mt5_wine_prefix: Path | None = None
    mt5_terminal_path: Path | None = None
    mt5_startup_timeout_seconds: int = Field(default=30, ge=3, le=180)
    mt5_runtime_control_url: str | None = None
    mt5_runtime_control_token: SecretStr | None = None
    litellm_enabled: bool = False
    litellm_url: str = "http://localhost:4000"
    litellm_api_key: SecretStr | None = None
    default_owner_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    twelve_data_api_key: SecretStr | None = None
    research_forex_universe: str = "EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD"
    research_metals_universe: str = "XAU/USD,XAG/USD"
    research_crypto_universe: str = "BTC-USD,ETH-USD,SOL-USD"
    research_stocks_universe: str = "AAPL,MSFT,NVDA,SPY"
    research_candle_count: int = Field(default=100, ge=20, le=500)
    research_schedule_enabled: bool = True
    research_schedule_hour_utc: int = Field(default=5, ge=0, le=23)
    research_schedule_minute_utc: int = Field(default=0, ge=0, le=59)
    forex_factory_schedule_enabled: bool = True
    forex_factory_schedule_hour_utc: int = Field(default=5, ge=0, le=23)
    forex_factory_schedule_minute_utc: int = Field(default=0, ge=0, le=59)
    research_agent_timeout_seconds: int = Field(default=90, ge=10, le=300)
    research_artifact_root: Path = Path("data/research_cycles")
    strategy_research_max_market_age_hours: int = Field(default=24, ge=1, le=168)
    strategy_research_history_days: int = Field(default=45, ge=7, le=365)
    strategy_research_timeframe: str = "4h"
    strategy_research_discovery_ratio: Decimal = Field(
        default=Decimal("0.70"), ge=Decimal("0.5"), le=Decimal("0.9")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
