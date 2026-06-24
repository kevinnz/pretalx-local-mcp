from __future__ import annotations

import httpx
import pytest
import respx

from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.submissions import register_submission_tools
from tests._tooling import BASE_URL, ToolRegistry, make_settings


@pytest.fixture
async def submission_tool_context() -> tuple[dict[str, object], PretalxClient]:
    settings = make_settings(default_event="demo")
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_submission_tools(registry, client, settings)

    try:
        yield registry.tools, client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_submissions_applies_filters_and_limit(
    respx_mock: respx.MockRouter,
    submission_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = submission_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [
                    {
                        "code": "SUB1",
                        "title": {"en": "Scaling APIs"},
                        "state": "accepted",
                        "track": {"name": {"en": "Backend"}},
                        "submission_type": {"name": {"en": "Talk"}},
                        "speakers": [{"name": "Ada"}],
                        "tags": ["api"],
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_list_submissions"](
        state="accepted",
        track="backend",
        submission_type="talk",
        limit=999,
    )

    params = route.calls[0].request.url.params
    assert params["state"] == "accepted"
    assert params["track"] == "backend"
    assert params["submission_type"] == "talk"
    assert params["limit"] == "500"

    assert result["event"] == "demo"
    assert result["applied_limit"] == 500
    assert result["returned_count"] == 1
    assert result["total_count"] == 1
    assert result["truncated"] is False
    assert result["submissions"][0]["code"] == "SUB1"


@pytest.mark.asyncio
async def test_get_submission_by_code_returns_detail(
    respx_mock: respx.MockRouter,
    submission_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = submission_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/SUB42/").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "SUB42",
                "title": {"en": " Platform Patterns "},
                "abstract": {"en": "A short abstract."},
                "description": {"en": "Detailed description."},
                "track": {"name": {"en": "Architecture"}},
                "submission_type": {"name": {"en": "Workshop"}},
                "speakers": [{"name": "Grace Hopper"}],
            },
        )
    )

    result = await tools["pretalx_get_submission"](submission_code=" SUB42 ")

    assert route.called
    assert result["event"] == "demo"
    assert result["submission"]["title"] == "Platform Patterns"
    assert result["submission"]["track_name"] == "Architecture"
    assert result["submission"]["submission_type_name"] == "Workshop"
    assert result["submission"]["speaker_names"] == ["Grace Hopper"]
    assert result["submission"]["abstract_preview"] == "A short abstract."


@pytest.mark.asyncio
async def test_search_submissions_uses_server_side_query_and_counts(
    respx_mock: respx.MockRouter,
    submission_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = submission_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 4,
                "next": None,
                "results": [
                    {
                        "code": "SRV1",
                        "title": {"en": "GraphQL at Scale"},
                        "state": "accepted",
                    }
                ],
            },
        )
    )

    result = await tools["pretalx_search_submissions"](query="GraphQL", limit=1)

    assert len(route.calls) == 1
    assert route.calls[0].request.url.params["q"] == "GraphQL"
    assert route.calls[0].request.url.params["limit"] == "1"

    assert result["query"] == "GraphQL"
    assert result["returned_count"] == 1
    assert result["total_count"] == 4
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_search_submissions_local_fallback_matches_speakers_and_tags(
    respx_mock: respx.MockRouter,
    submission_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = submission_tool_context
    route = respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        side_effect=[
            httpx.Response(200, json={"count": 0, "next": None, "results": []}),
            httpx.Response(
                200,
                json={
                    "count": 3,
                    "next": None,
                    "results": [
                        {
                            "code": "SPK1",
                            "title": {"en": "Backend Futures"},
                            "speakers": [{"name": "Ada Lovelace"}],
                            "tags": ["infra"],
                        },
                        {
                            "code": "TAG1",
                            "title": {"en": "Cloud Native Journeys"},
                            "speakers": [{"name": "Grace"}],
                            "tags": ["ada"],
                        },
                        {
                            "code": "NONE1",
                            "title": {"en": "No Match"},
                            "speakers": [{"name": "Nobody"}],
                            "tags": ["none"],
                        },
                    ],
                },
            ),
        ]
    )

    result = await tools["pretalx_search_submissions"](query="Ada", limit=5)

    assert len(route.calls) == 2
    assert route.calls[0].request.url.params["q"] == "Ada"
    assert "q" not in route.calls[1].request.url.params
    assert route.calls[1].request.url.params["limit"] == "50"

    assert result["returned_count"] == 2
    assert result["total_count"] == 2
    assert result["truncated"] is False
    assert [item["code"] for item in result["submissions"]] == ["SPK1", "TAG1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group_by", "expected_counts"),
    [
        ("state", {"accepted": 2, "submitted": 1}),
        ("track", {"DevOps": 2, "Data": 1}),
        ("submission_type", {"Talk": 2, "Workshop": 1}),
        ("speaker", {"Ada": 2, "Bob": 1, "unspecified speaker": 1}),
        ("tag", {"ml": 2, "cloud": 1, "untagged": 1}),
    ],
)
async def test_summarise_submissions_groupings(
    respx_mock: respx.MockRouter,
    submission_tool_context: tuple[dict[str, object], PretalxClient],
    group_by: str,
    expected_counts: dict[str, int],
) -> None:
    tools, _ = submission_tool_context
    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 3,
                "next": None,
                "results": [
                    {
                        "code": "S1",
                        "state": "accepted",
                        "track": {"name": {"en": "DevOps"}},
                        "submission_type": {"name": {"en": "Talk"}},
                        "speakers": [{"name": "Ada"}, {"name": "Bob"}],
                        "tags": ["cloud", "ml", "cloud"],
                    },
                    {
                        "code": "S2",
                        "state": "submitted",
                        "track": {"name": {"en": "DevOps"}},
                        "submission_type": {"name": {"en": "Workshop"}},
                        "speakers": [{"name": "Ada"}],
                        "tags": ["ml"],
                    },
                    {
                        "code": "S3",
                        "state": "accepted",
                        "track": {"name": {"en": "Data"}},
                        "submission_type": {"name": {"en": "Talk"}},
                        "speakers": [],
                        "tags": [],
                    },
                ],
            },
        )
    )

    result = await tools["pretalx_summarise_submissions"](group_by=group_by)

    assert result["event"] == "demo"
    assert result["group_by"] == group_by
    assert result["total_submissions"] == 3
    assert result["total_count"] == 3
    assert result["truncated"] is False

    groups = {item["key"]: item["count"] for item in result["groups"]}
    assert groups == expected_counts
