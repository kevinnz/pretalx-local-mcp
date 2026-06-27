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


@pytest.mark.asyncio
async def test_list_events_with_include_raw_returns_raw_events(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    raw_data = [{"slug": "raw-2026", "name": {"en": "Raw Event"}}]
    respx_mock.get(f"{BASE_URL}/api/events/").mock(
        return_value=httpx.Response(200, json={"count": 1, "next": None, "results": raw_data})
    )

    result = await tools["pretalx_list_events"](include_raw=True)

    assert "raw_events" in result
    assert result["raw_events"] == raw_data


@pytest.mark.asyncio
async def test_get_event_with_include_raw_returns_raw_event(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    raw_data = {"slug": "demo-2026", "name": {"en": "Demo"}, "extra_field": "value"}
    respx_mock.get(f"{BASE_URL}/api/events/demo-2026/").mock(
        return_value=httpx.Response(200, json=raw_data)
    )

    result = await tools["pretalx_get_event"](event="demo-2026", include_raw=True)

    assert "raw_event" in result
    assert result["raw_event"]["extra_field"] == "value"


@pytest.mark.asyncio
async def test_get_event_raises_on_unexpected_non_mapping_payload(
    respx_mock: respx.MockRouter,
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context
    respx_mock.get(f"{BASE_URL}/api/events/demo-2026/").mock(
        return_value=httpx.Response(200, json=[{"slug": "demo-2026"}])
    )

    with pytest.raises(RuntimeError, match="unexpected payload"):
        await tools["pretalx_get_event"](event="demo-2026")


@pytest.mark.asyncio
async def test_list_events_raises_on_zero_limit(
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context

    with pytest.raises(RuntimeError, match="limit must be at least 1"):
        await tools["pretalx_list_events"](limit=0)


@pytest.mark.asyncio
async def test_list_events_raises_on_negative_limit(
    event_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = event_tool_context

    with pytest.raises(RuntimeError, match="limit must be at least 1"):
        await tools["pretalx_list_events"](limit=-5)
