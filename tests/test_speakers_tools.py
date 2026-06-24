from __future__ import annotations

import httpx
import pytest
import respx

from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.speakers import register_speaker_tools
from tests._tooling import BASE_URL, ToolRegistry, make_settings


@pytest.fixture
async def speaker_tool_context() -> tuple[dict[str, object], PretalxClient]:
    settings = make_settings(default_event="demo")
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_speaker_tools(registry, client, settings)

    try:
        yield registry.tools, client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_speakers_returns_compact_results_without_invented_email(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": None,
                "results": [
                    {
                        "code": "SPK1",
                        "name": "Ada",
                        "email": "ada@example.com",
                        "biography": {"en": "Compiler pioneer"},
                    },
                    {
                        "code": "SPK2",
                        "name": "Bob",
                        "biography": {"en": "Distributed systems builder"},
                    },
                ],
            },
        )
    )

    result = await tools["pretalx_list_speakers"](limit=5)

    assert route.called
    assert result["event"] == "demo"
    assert result["returned_count"] == 2
    assert result["total_count"] == 2
    assert result["truncated"] is False

    assert result["speakers"][0]["email"] == "ada@example.com"
    assert "email" not in result["speakers"][1]


@pytest.mark.asyncio
async def test_get_speaker_returns_detail_with_submission_context(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/SPK1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "SPK1",
                "name": "Ada",
                "email": "ada@example.com",
                "biography": {"en": "Compiler pioneer"},
                "submissions": [
                    {
                        "code": "SUB1",
                        "title": {"en": "Compilers 101"},
                        "state": "accepted",
                        "track": {"name": {"en": "Engineering"}},
                        "submission_type": {"name": {"en": "Talk"}},
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_get_speaker"](speaker="SPK1")

    assert route.called
    detail = result["speaker"]
    assert result["event"] == "demo"
    assert detail["code"] == "SPK1"
    assert detail["name"] == "Ada"
    assert detail["email"] == "ada@example.com"
    assert detail["biography"] == "Compiler pioneer"
    assert detail["submission_count"] == 1
    assert detail["submissions"] == [
        {
            "code": "SUB1",
            "title": "Compilers 101",
            "state": "accepted",
            "track": "Engineering",
            "submission_type": "Talk",
        }
    ]


@pytest.mark.asyncio
async def test_get_speaker_maps_not_found_to_clear_error(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/MISSING/").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(ValueError, match="Speaker 'MISSING' was not found"):
        await tools["pretalx_get_speaker"](speaker="MISSING")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_code"),
    [
        ("lovelace", "NAME1"),
        ("analytics", "BIO1"),
        ("scale", "SUB1"),
    ],
)
async def test_search_speakers_matches_name_bio_and_submission_title(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
    query: str,
    expected_code: str,
) -> None:
    tools, _ = speaker_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/").mock(
        side_effect=[
            httpx.Response(200, json={"count": 0, "next": None, "results": []}),
            httpx.Response(
                200,
                json={
                    "count": 3,
                    "next": None,
                    "results": [
                        {
                            "code": "NAME1",
                            "name": "Ada Lovelace",
                            "biography": "Compiler pioneer",
                            "submissions": [],
                        },
                        {
                            "code": "BIO1",
                            "name": "Grace Hopper",
                            "biography": "Edge analytics specialist",
                            "submissions": [],
                        },
                        {
                            "code": "SUB1",
                            "name": "Linus Torvalds",
                            "biography": "Kernel mentor",
                            "submissions": [{"title": {"en": "Operating Systems at Scale"}}],
                        },
                    ],
                },
            ),
        ]
    )

    result = await tools["pretalx_search_speakers"](query=query, limit=10)

    assert len(route.calls) == 2
    assert route.calls[0].request.url.params["q"] == query
    assert "q" not in route.calls[1].request.url.params

    assert result["query"] == query
    assert result["total_count"] == 1
    assert result["returned_count"] == 1
    assert result["truncated"] is False
    assert result["speakers"][0]["code"] == expected_code
    assert "email" not in result["speakers"][0]
