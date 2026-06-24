from __future__ import annotations

import pytest
from pydantic import ValidationError

from pretalx_mcp.config import Settings

_PRETALX_ENV_KEYS = (
    "PRETALX_BASE_URL",
    "PRETALX_API_TOKEN",
    "PRETALX_DEFAULT_EVENT",
    "PRETALX_TIMEOUT_SECONDS",
    "PRETALX_VERIFY_TLS",
    "PRETALX_READ_ONLY",
    "PRETALX_TRANSPORT",
)


@pytest.fixture(autouse=True)
def clear_pretalx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PRETALX_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_defaults_and_base_url_cleanup_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRETALX_BASE_URL", "https://pretalx.com/")

    settings = Settings(_env_file=None)

    assert settings.base_url == "https://pretalx.com"
    assert settings.transport == "stdio"
    assert settings.read_only is True


def test_settings_rejects_non_stdio_transport() -> None:
    with pytest.raises(ValidationError, match="PRETALX_TRANSPORT must be 'stdio'"):
        Settings(base_url="https://pretalx.com", transport="sse", _env_file=None)


def test_settings_requires_base_url() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert any(error["loc"] == ("base_url",) for error in exc_info.value.errors())


def test_settings_model_has_no_network_bind_fields() -> None:
    forbidden = {"host", "port", "bind", "sse", "websocket"}
    assert forbidden.isdisjoint(Settings.model_fields)
