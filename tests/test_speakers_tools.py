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


@pytest.mark.asyncio
async def test_list_speakers_with_include_raw_returns_raw_list(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    raw = [{"code": "SP1", "name": "Ada"}]
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/").mock(
        return_value=httpx.Response(200, json={"count": 1, "next": None, "results": raw})
    )

    result = await tools["pretalx_list_speakers"](include_raw=True)

    assert "raw" in result
    assert result["raw"] == raw


@pytest.mark.asyncio
async def test_get_speaker_with_include_raw_returns_raw_dict(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    raw = {"code": "SP1", "name": "Ada", "extra": "data"}
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/SP1/").mock(
        return_value=httpx.Response(200, json=raw)
    )

    result = await tools["pretalx_get_speaker"](speaker="SP1", include_raw=True)

    assert "raw" in result
    assert result["raw"]["extra"] == "data"


@pytest.mark.asyncio
async def test_search_speakers_with_include_raw_returns_raw_list(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    raw = [{"code": "SP1", "name": "Ada Lovelace"}]
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/").mock(
        return_value=httpx.Response(200, json={"count": 1, "next": None, "results": raw})
    )

    result = await tools["pretalx_search_speakers"](query="Ada", include_raw=True)

    assert "raw" in result


@pytest.mark.asyncio
async def test_list_speakers_raises_without_event_and_no_default() -> None:
    from pretalx_mcp.tools.speakers import register_speaker_tools
    from tests._tooling import ToolRegistry, make_settings

    settings = make_settings(default_event=None)
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_speaker_tools(registry, client, settings)

    with pytest.raises(ValueError, match="Event slug is required"):
        await registry.tools["pretalx_list_speakers"]()

    await client.aclose()


@pytest.mark.asyncio
async def test_get_speaker_raises_without_event_and_no_default() -> None:
    from pretalx_mcp.tools.speakers import register_speaker_tools
    from tests._tooling import ToolRegistry, make_settings

    settings = make_settings(default_event=None)
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_speaker_tools(registry, client, settings)

    with pytest.raises(ValueError, match="Event slug is required"):
        await registry.tools["pretalx_get_speaker"](speaker="SP1")

    await client.aclose()


@pytest.mark.asyncio
async def test_list_speakers_raises_on_zero_limit(
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context

    with pytest.raises(ValueError, match="limit must be at least 1"):
        await tools["pretalx_list_speakers"](limit=0)


@pytest.mark.asyncio
async def test_get_speaker_raises_on_unexpected_list_payload(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = speaker_tool_context
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/SP1/").mock(
        return_value=httpx.Response(200, json=[{"code": "SP1"}])
    )

    with pytest.raises(RuntimeError, match="unexpected speaker payload"):
        await tools["pretalx_get_speaker"](speaker="SP1")


@pytest.mark.asyncio
async def test_merge_speakers_deduplicates_by_code(
    respx_mock: respx.MockRouter,
    speaker_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    """Speaker appearing in server-side and local pool is deduplicated."""
    tools, _ = speaker_tool_context
    item = {"code": "SP1", "name": "Ada Lovelace"}
    respx_mock.get(f"{BASE_URL}/api/events/demo/speakers/").mock(
        return_value=httpx.Response(200, json={"count": 1, "next": None, "results": [item]})
    )

    result = await tools["pretalx_search_speakers"](query="Ada")

    assert result["returned_count"] == 1
