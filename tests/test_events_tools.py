from __future__ import annotations

import httpx
import pytest
import respx

from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.events import register_event_tools
from tests._tooling import BASE_URL, ToolRegistry, make_settings


@pytest.fixture
async def event_tool_context() -> tuple[dict[str, object], PretalxClient]:
    settings = make_settings(default_event="default-2026")
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_event_tools(registry, client, settings)

    try:
        yield registry.tools, client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_events_returns_compact_output(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "results": [
                    {
                        "slug": "demo-2026",
                        "name": {"en": "Demo Conference"},
                        "date_from": "2026-09-01",
                        "date_to": "2026-09-03",
                        "timezone": "Pacific/Auckland",
                        "is_public": True,
                        "public_url": "https://pretalx.example/demo-2026",
                        "ignored": "value",
                    },
                    {
                        "slug": "staff-summit",
                        "name": {"en": " Staff Summit "},
                        "timezone": "UTC",
                        "is_public": False,
                        "url": "https://pretalx.example/staff-summit",
                    },
                ],
            },
        )
    )

    result = await tools["pretalx_list_events"](limit=5)

    assert route.called
    assert route.calls[0].request.url.params["limit"] == "5"
    assert result["returned_count"] == 2
    assert result["total_count"] == 2
    assert result["truncated"] is False
    assert result["events"] == [
        {
            "slug": "demo-2026",
            "name": "Demo Conference",
            "date_from": "2026-09-01",
            "date_to": "2026-09-03",
            "timezone": "Pacific/Auckland",
            "is_public": True,
            "url": "https://pretalx.example/demo-2026",
        },
        {
            "slug": "staff-summit",
            "name": "Staff Summit",
            "timezone": "UTC",
            "is_public": False,
            "url": "https://pretalx.example/staff-summit",
        },
    ]


@pytest.mark.asyncio
async def test_get_event_uses_explicit_event_when_provided(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/explicit-2026/").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "explicit-2026",
                "name": {"en": " Explicit Event "},
                "timezone": "UTC",
            },
        )
    )

    result = await tools["pretalx_get_event"](event=" explicit-2026 ")

    assert route.called
    assert result["event"]["slug"] == "explicit-2026"
    assert result["event"]["name"] == "Explicit Event"


@pytest.mark.asyncio
async def test_get_event_falls_back_to_default_event(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/default-2026/").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "default-2026",
                "name": {"en": "Default Event"},
            },
        )
    )

    result = await tools["pretalx_get_event"]()

    assert route.called
    assert result["event"]["slug"] == "default-2026"
    assert result["event"]["name"] == "Default Event"


@pytest.mark.asyncio
async def test_get_event_raises_clear_error_without_event_or_default() -> None:
    settings = make_settings(default_event=None)
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_event_tools(registry, client, settings)

    with pytest.raises(RuntimeError, match="Event slug is required"):
        await registry.tools["pretalx_get_event"]()

    await client.aclose()
