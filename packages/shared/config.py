from __future__ import annotations

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
    blob_root: Path = Path("data/blobs")
    codex_enabled: bool = True
    codex_binary: str = "codex"
    default_codex_model: str = "gpt-5.6-terra"
    litellm_enabled: bool = False
    litellm_url: str = "http://localhost:4000"
    litellm_api_key: SecretStr | None = None
    default_owner_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
