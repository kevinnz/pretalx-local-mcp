"""Optional integration tests — skipped unless real PRETALX_* env vars are set."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from pretalx_mcp.config import Settings
from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.events import register_event_tools
from pretalx_mcp.tools.schedule import register_schedule_tools
from tests._tooling import ToolRegistry

# Check both shell environment and .env file for required credentials
_env_file_values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")


def _get_config(key: str) -> str:
    return os.environ.get(key) or _env_file_values.get(key, "") or ""


_REQUIRES_REAL_API = pytest.mark.skipif(
    not (_get_config("PRETALX_BASE_URL") and _get_config("PRETALX_API_TOKEN")),
    reason="Requires PRETALX_BASE_URL and PRETALX_API_TOKEN (env or .env)",
)


@pytest.fixture
def real_settings() -> Settings:
    return Settings()


@pytest.fixture
async def real_client(real_settings: Settings) -> PretalxClient:
    client = PretalxClient(real_settings)
    try:
        yield client
    finally:
        await client.aclose()


@_REQUIRES_REAL_API
@pytest.mark.asyncio
async def test_list_events_returns_at_least_one_event(
    real_client: PretalxClient, real_settings: Settings
) -> None:
    registry = ToolRegistry()
    register_event_tools(registry, real_client, real_settings)

    result = await registry.tools["pretalx_list_events"](limit=5)

    assert isinstance(result, dict)
    assert "events" in result
    assert isinstance(result["events"], list)
    assert len(result["events"]) >= 1
    assert "slug" in result["events"][0]


@_REQUIRES_REAL_API
@pytest.mark.asyncio
async def test_get_schedule_returns_expected_structure(
    real_client: PretalxClient, real_settings: Settings
) -> None:
    if not real_settings.default_event:
        pytest.skip("PRETALX_DEFAULT_EVENT not set")

    registry = ToolRegistry()
    register_schedule_tools(registry, real_client, real_settings)

    result = await registry.tools["pretalx_get_schedule"]()

    assert isinstance(result, dict)
    assert "event" in result
    assert "available" in result
