from __future__ import annotations

import pytest
from fastmcp import FastMCP

import pretalx_mcp.server as server_module
from pretalx_mcp.config import Settings
from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.server import create_server


def test_create_server_returns_fresh_instances() -> None:
    settings = Settings(base_url="https://pretalx.com", _env_file=None)
    client = PretalxClient(settings)

    first = create_server(settings, client)
    second = create_server(settings, client)

    assert isinstance(first, FastMCP)
    assert isinstance(second, FastMCP)
    assert first is not second


def test_main_runs_server_over_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(base_url="https://pretalx.com", _env_file=None)
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, provided_settings: Settings) -> None:
            calls["client_settings"] = provided_settings

        async def aclose(self) -> None:
            calls["closed"] = True

    class FakeMCP:
        def run(self, *, transport: str) -> None:
            calls["transport"] = transport

    def fake_get_settings() -> Settings:
        return settings

    def fake_create_server(provided_settings: Settings, client: FakeClient) -> FakeMCP:
        calls["server_settings"] = provided_settings
        calls["server_client"] = client
        return FakeMCP()

    monkeypatch.setattr(server_module, "get_settings", fake_get_settings)
    monkeypatch.setattr(server_module, "PretalxClient", FakeClient)
    monkeypatch.setattr(server_module, "create_server", fake_create_server)

    server_module.main()

    assert calls["transport"] == "stdio"
    assert calls["client_settings"] is settings
    assert calls["server_settings"] is settings
    assert isinstance(calls["server_client"], FakeClient)
    assert calls["closed"] is True


def test_main_raises_system_exit_on_invalid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError as PydanticValidationError

    def bad_get_settings() -> Settings:
        raise PydanticValidationError.from_exception_data(
            title="Settings",
            input_type="python",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("base_url",),
                    "msg": "Field required",
                    "input": {},
                    "url": "https://errors.pydantic.dev/2/v/missing",
                }
            ],
        )

    monkeypatch.setattr(server_module, "get_settings", bad_get_settings)

    with pytest.raises(SystemExit, match="Invalid PRETALX_\\* configuration"):
        server_module.main()
