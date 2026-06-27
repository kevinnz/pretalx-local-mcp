from __future__ import annotations

import httpx
import pytest
import respx

from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.schedule import register_schedule_tools
from tests._tooling import BASE_URL, ToolRegistry, make_settings


@pytest.fixture
async def schedule_tool_context() -> tuple[dict[str, object], PretalxClient]:
    settings = make_settings(default_event="demo")
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_schedule_tools(registry, client, settings)

    try:
        yield registry.tools, client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_schedule_uses_two_step_fetch_with_slots_fallback(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    schedules = respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [{"version": "2026.1", "is_published": True}],
            },
        )
    )
    talks = respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/2026.1/talks/").mock(
        return_value=httpx.Response(404)
    )
    slots = respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/2026.1/slots/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [
                    {
                        "code": "SLOT1",
                        "start": "2026-09-12T09:00:00+00:00",
                        "end": "2026-09-12T10:00:00+00:00",
                        "room": {"name": {"en": "Main Hall"}},
                        "submission": {
                            "code": "SUB1",
                            "title": {"en": "Welcome"},
                            "track": {"name": {"en": "General"}},
                            "speakers": [{"name": "Ada"}],
                        },
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_get_schedule"]()

    assert schedules.called
    assert talks.called
    assert slots.called
    assert result["available"] is True
    assert result["endpoint_used"] == "slots"
    assert result["session_count"] == 1
    assert result["sessions"] == [
        {
            "code": "SLOT1",
            "title": "Welcome",
            "start": "2026-09-12T09:00:00+00:00",
            "end": "2026-09-12T10:00:00+00:00",
            "room": "Main Hall",
            "track": "General",
            "speakers": ["Ada"],
        }
    ]


@pytest.mark.asyncio
async def test_list_schedule_sessions_flattens_and_filters(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [{"version": "latest", "is_published": True}],
            },
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/latest/talks/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "results": [
                    {
                        "code": "A1",
                        "title": {"en": "Data Keynote"},
                        "start": "2026-09-12T09:00:00+00:00",
                        "end": "2026-09-12T10:00:00+00:00",
                        "room": {"name": {"en": "Main Hall"}},
                        "track": {"name": {"en": "Data"}},
                        "speakers": [{"name": "Ada"}],
                    },
                    {
                        "code": "B2",
                        "title": {"en": "Ops Panel"},
                        "start": "2026-09-13T09:00:00+00:00",
                        "end": "2026-09-13T10:00:00+00:00",
                        "room": {"name": {"en": "Room B"}},
                        "track": {"name": {"en": "Operations"}},
                        "speakers": [{"name": "Bob"}],
                    },
                ],
            },
        )
    )

    result = await tools["pretalx_list_schedule_sessions"](
        day="2026-09-12",
        room="main",
        speaker="ada",
        track="data",
    )

    assert result["available"] is True
    assert result["total_count"] == 2
    assert result["returned_count"] == 1
    assert result["filters"] == {
        "day": "2026-09-12",
        "room": "main",
        "speaker": "ada",
        "track": "data",
    }
    assert result["sessions"] == [
        {
            "code": "A1",
            "title": "Data Keynote",
            "start": "2026-09-12T09:00:00+00:00",
            "end": "2026-09-12T10:00:00+00:00",
            "room": "Main Hall",
            "track": "Data",
            "speakers": ["Ada"],
        }
    ]


@pytest.mark.asyncio
async def test_find_schedule_conflicts_reports_overlaps_and_missing_data(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [{"version": "latest", "is_published": True}],
            },
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/latest/talks/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 6,
                "next": None,
                "results": [
                    {
                        "code": "A1",
                        "title": "Speaker overlap 1",
                        "start": "2026-09-12T09:00:00+00:00",
                        "end": "2026-09-12T10:00:00+00:00",
                        "room": {"name": {"en": "Room A"}},
                        "speakers": [{"name": "Ada"}],
                    },
                    {
                        "code": "A2",
                        "title": "Speaker overlap 2",
                        "start": "2026-09-12T09:30:00+00:00",
                        "end": "2026-09-12T10:30:00+00:00",
                        "room": {"name": {"en": "Room B"}},
                        "speakers": [{"name": "Ada"}],
                    },
                    {
                        "code": "R1",
                        "title": "Room overlap 1",
                        "start": "2026-09-12T11:00:00+00:00",
                        "end": "2026-09-12T12:00:00+00:00",
                        "room": {"name": {"en": "Shared"}},
                        "speakers": [{"name": "Bob"}],
                    },
                    {
                        "code": "R2",
                        "title": "Room overlap 2",
                        "start": "2026-09-12T11:30:00+00:00",
                        "end": "2026-09-12T12:30:00+00:00",
                        "room": {"name": {"en": "Shared"}},
                        "speakers": [{"name": "Carol"}],
                    },
                    {
                        "code": "M1",
                        "title": "Missing room",
                        "start": "2026-09-12T13:00:00+00:00",
                        "end": "2026-09-12T14:00:00+00:00",
                        "speakers": [{"name": "Dana"}],
                    },
                    {
                        "code": "M2",
                        "title": "Missing time",
                        "start": "2026-09-12T15:00:00+00:00",
                        "room": {"name": {"en": "Room C"}},
                        "speakers": [{"name": "Eve"}],
                    },
                ],
            },
        )
    )

    result = await tools["pretalx_find_schedule_conflicts"]()

    assert result["available"] is True
    assert result["counts"] == {
        "speaker_overlaps": 1,
        "room_overlaps": 1,
        "missing_room": 1,
        "missing_time": 1,
        "total_conflicts": 4,
    }

    assert result["speaker_overlaps"][0]["speaker"] == "Ada"
    assert result["room_overlaps"][0]["room"] == "Shared"
    assert result["missing_room"][0]["reason"] == "missing_room"
    assert result["missing_time"][0]["reason"] == "missing_start_or_end"


@pytest.mark.asyncio
async def test_get_schedule_handles_unpublished_schedule_with_helpful_message(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "results": [
                    {"version": "latest", "is_published": False},
                    {"version": "2026.0", "is_published": False},
                ],
            },
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/latest/talks/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [
                    {
                        "code": "U1",
                        "title": {"en": "Preview Session"},
                        "start": "2026-09-12T08:00:00+00:00",
                        "end": "2026-09-12T08:30:00+00:00",
                        "room": {"name": {"en": "Preview"}},
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_get_schedule"]()

    assert result["available"] is True
    assert result["schedule_version"] == "latest"
    assert "No published schedule found" in result["message"]
    assert result["session_count"] == 1


@pytest.mark.asyncio
async def test_get_schedule_returns_unavailable_when_no_schedules(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(200, json={"count": 0, "next": None, "results": []})
    )

    result = await tools["pretalx_get_schedule"]()

    assert result["available"] is False
    assert result["event"] == "demo"
    assert result["session_count"] == 0
    assert "available" in result["message"].casefold() or "schedule" in result["message"].casefold()


@pytest.mark.asyncio
async def test_get_schedule_with_include_raw_returns_raw(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    raw_schedule = {"version": "2026.1", "is_published": True}
    raw_session = {
        "code": "S1",
        "start": "2026-09-12T09:00:00+00:00",
        "end": "2026-09-12T10:00:00+00:00",
        "room": {"name": {"en": "Room A"}},
    }
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200, json={"count": 1, "next": None, "results": [raw_schedule]}
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/2026.1/talks/").mock(
        return_value=httpx.Response(
            200, json={"count": 1, "next": None, "results": [raw_session]}
        )
    )

    result = await tools["pretalx_get_schedule"](include_raw=True)

    assert result["available"] is True
    assert "raw" in result
    assert "schedules" in result["raw"]
    assert "sessions" in result["raw"]


@pytest.mark.asyncio
async def test_list_schedule_sessions_returns_unavailable_when_no_schedules(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(200, json={"count": 0, "next": None, "results": []})
    )

    result = await tools["pretalx_list_schedule_sessions"]()

    assert result["available"] is False
    assert result["total_count"] == 0
    assert result["returned_count"] == 0


@pytest.mark.asyncio
async def test_list_schedule_sessions_with_include_raw_returns_raw(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [{"version": "v1", "is_published": True}],
            },
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/v1/talks/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [
                    {
                        "code": "S1",
                        "start": "2026-09-12T09:00:00+00:00",
                        "end": "2026-09-12T10:00:00+00:00",
                        "room": {"name": {"en": "Main"}},
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_list_schedule_sessions"](include_raw=True)

    assert result["available"] is True
    assert "raw" in result


@pytest.mark.asyncio
async def test_find_schedule_conflicts_returns_unavailable_when_no_schedules(
    respx_mock: respx.MockRouter,
    schedule_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = schedule_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/schedules/").mock(
        return_value=httpx.Response(200, json={"count": 0, "next": None, "results": []})
    )

    result = await tools["pretalx_find_schedule_conflicts"]()

    assert result["available"] is False
    assert result["counts"]["total_conflicts"] == 0
