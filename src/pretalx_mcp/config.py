"""Environment-driven configuration for pretalx MCP."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from PRETALX_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="PRETALX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str
    api_token: str | None = None
    default_event: str | None = None
    timeout_seconds: float = Field(default=20.0, gt=0)
    verify_tls: bool = True
    read_only: bool = True
    transport: str = "stdio"

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            msg = "PRETALX_BASE_URL must be a non-empty URL."
            raise ValueError(msg)

        parsed = urlsplit(cleaned)
        if not parsed.scheme or not parsed.netloc:
            msg = "PRETALX_BASE_URL must include scheme and host, e.g. https://pretalx.com."
            raise ValueError(msg)
        return cleaned

    @field_validator("default_event")
    @classmethod
    def validate_default_event(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned != "stdio":
            msg = "PRETALX_TRANSPORT must be 'stdio'; network transports are not supported."
            raise ValueError(msg)
        return cleaned


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for process lifetime."""

    return Settings()
