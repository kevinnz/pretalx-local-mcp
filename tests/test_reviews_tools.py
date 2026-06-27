from __future__ import annotations

import httpx
import pytest
import respx

from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.reviews import register_review_tools
from tests._tooling import BASE_URL, ToolRegistry, make_settings


@pytest.fixture
async def review_tool_context() -> tuple[dict[str, object], PretalxClient]:
    settings = make_settings(default_event="demo")
    registry = ToolRegistry()
    client = PretalxClient(settings)
    register_review_tools(registry, client, settings)

    try:
        yield registry.tools, client
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_submission_reviews_degrades_gracefully_when_unavailable(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/SUB1/reviews/").mock(
        return_value=httpx.Response(403)
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/reviews/").mock(
        side_effect=[httpx.Response(404), httpx.Response(405)]
    )

    result = await tools["pretalx_get_submission_reviews"](submission_code="SUB1")

    assert result["available"] is False
    assert result["event"] == "demo"
    assert result["submission_code"] == "SUB1"
    assert result["review_count"] == 0
    assert result["numeric_score_count"] == 0
    assert result["average_score"] is None
    assert "Review data is unavailable" in result["message"]
    assert len(result["notes"]) == 3
    assert any("forbidden" in note.casefold() for note in result["notes"])
    assert any("not found" in note.casefold() for note in result["notes"])
    assert any("status 405" in note.casefold() for note in result["notes"])


@pytest.mark.asyncio
async def test_get_submission_reviews_parses_scores_and_averages(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/SUB1/reviews/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 4,
                "next": None,
                "results": [
                    {"id": "r1", "score": 4, "reviewer": {"name": "Alice"}},
                    {
                        "id": "r2",
                        "score": "3.5",
                        "submission": {"code": "SUB1"},
                        "reviewer": "Bob",
                    },
                    {
                        "id": "r3",
                        "score": {"overall": "bad", "criteria": [2, "n/a"]},
                        "reviewer_name": "Cara",
                    },
                    {"id": "r4", "score": "n/a", "reviewed_by": "Dana"},
                ],
            },
        )
    )

    result = await tools["pretalx_get_submission_reviews"](submission_code="SUB1")

    assert result["available"] is True
    assert result["source"] == "submission_reviews"
    assert result["review_count"] == 4
    assert result["numeric_score_count"] == 3
    assert result["average_score"] == pytest.approx(3.167, abs=1e-3)

    reviews_by_id = {item["id"]: item for item in result["reviews"]}
    assert reviews_by_id["r1"]["submission_code"] == "SUB1"
    assert reviews_by_id["r2"]["score_numeric"] == pytest.approx(3.5)
    assert reviews_by_id["r3"]["score_numeric"] == pytest.approx(2.0)
    assert reviews_by_id["r4"]["score_numeric"] is None


@pytest.mark.asyncio
async def test_review_summary_returns_expected_structure(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 3,
                "next": None,
                "results": [
                    {
                        "code": "A1",
                        "title": {"en": "Keynote"},
                        "track": {"name": {"en": "Data"}},
                    },
                    {
                        "code": "B2",
                        "title": {"en": "Workshop"},
                        "track": {"name": {"en": "Data"}},
                    },
                    {
                        "code": "C3",
                        "title": {"en": "Ops Talk"},
                        "track": {"name": {"en": "Ops"}},
                    },
                ],
            },
        )
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/reviews/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 3,
                "next": None,
                "results": [
                    {"id": "rv1", "submission": "A1", "score": 5},
                    {"id": "rv2", "submission": {"code": "A1"}, "score": 3},
                    {"id": "rv3", "proposal": "B2", "score": "2"},
                ],
            },
        )
    )

    result = await tools["pretalx_review_summary"]()

    assert result["available"] is True
    assert result["event"] == "demo"
    assert result["source"] == "event_reviews"
    assert result["submission_count"] == 3
    assert result["review_count"] == 3
    assert result["no_reviews_count"] == 1
    assert result["low_review_threshold"] == 2
    assert result["low_review_count"] == 1

    track_summary = {row["track"]: row for row in result["average_scores_by_track"]}
    assert track_summary["Data"]["submission_count"] == 2
    assert track_summary["Data"]["numeric_score_count"] == 3
    assert track_summary["Data"]["average_score"] == pytest.approx(3.333, abs=1e-3)
    assert track_summary["Ops"]["submission_count"] == 1
    assert track_summary["Ops"]["numeric_score_count"] == 0
    assert track_summary["Ops"]["average_score"] is None

    assert result["highest_scoring_submission"]["code"] == "A1"
    assert result["lowest_scoring_submission"]["code"] == "B2"
    assert {row["code"] for row in result["no_reviews"]} == {"C3"}
    assert {row["code"] for row in result["low_review_submissions"]} == {"B2"}

    assert isinstance(result["submissions"], list)
    assert result["notes"] == []


@pytest.mark.asyncio
async def test_get_submission_reviews_with_include_raw_returns_raw(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context
    raw_reviews = [{"id": "r1", "score": 4}]
    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/SUB1/reviews/").mock(
        return_value=httpx.Response(200, json={"count": 1, "next": None, "results": raw_reviews})
    )

    result = await tools["pretalx_get_submission_reviews"](
        submission_code="SUB1", include_raw=True
    )

    assert result["available"] is True
    assert "raw" in result
    assert len(result["raw"]) == 1
    assert result["raw"][0]["id"] == "r1"
    assert result["raw"][0]["score"] == 4


@pytest.mark.asyncio
async def test_review_summary_degrades_when_all_review_endpoints_unavailable(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(200, json={"count": 0, "next": None, "results": []})
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/reviews/").mock(
        return_value=httpx.Response(403)
    )
    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/reviews/").mock(
        return_value=httpx.Response(404)
    )

    result = await tools["pretalx_review_summary"]()

    assert result["available"] is False
    assert result["event"] == "demo"
    assert "unavailable" in result["message"].casefold()


@pytest.mark.asyncio
async def test_review_summary_falls_back_to_per_submission_reviews(
    respx_mock: respx.MockRouter,
    review_tool_context: tuple[dict[str, object], PretalxClient],
) -> None:
    tools, _ = review_tool_context

    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [{"code": "S1", "title": {"en": "Talk"}}],
            },
        )
    )
    # Both collection endpoints unavailable
    respx_mock.get(f"{BASE_URL}/api/events/demo/reviews/").mock(return_value=httpx.Response(403))
    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/reviews/").mock(
        return_value=httpx.Response(403)
    )
    # Per-submission fallback succeeds
    respx_mock.get(f"{BASE_URL}/api/events/demo/submissions/S1/reviews/").mock(
        return_value=httpx.Response(
            200, json={"count": 1, "next": None, "results": [{"id": "r1", "score": 5}]}
        )
    )

    result = await tools["pretalx_review_summary"]()

    assert result["available"] is True
    assert result["source"] == "submission_reviews_fallback"
    assert result["review_count"] == 1
