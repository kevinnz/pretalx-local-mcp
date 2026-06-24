from __future__ import annotations

import re

import httpx
import pytest
import respx

from pretalx_mcp.config import Settings
from pretalx_mcp.pretalx_client import PaginationMeta, PretalxClient, PretalxClientError

BASE_URL = "https://pretalx.example"


def make_settings(*, api_token: str | None = "test-token") -> Settings:
    return Settings(base_url=BASE_URL, api_token=api_token, _env_file=None)


@pytest.mark.asyncio
async def test_auth_header_present_when_token_is_configured(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"{BASE_URL}/api/events/").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    async with PretalxClient(make_settings(api_token="abc123")) as client:
        payload = await client.get("/api/events/")

    assert payload == {"ok": True}
    assert route.called
    request = route.calls[0].request
    assert request.headers.get("Authorization") == "Token abc123"


@pytest.mark.asyncio
async def test_auth_header_absent_when_token_missing(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/api/events/").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    async with PretalxClient(make_settings(api_token=None)) as client:
        await client.get("/api/events/")

    request = route.calls[0].request
    assert request.headers.get("Authorization") is None


@pytest.mark.asyncio
async def test_get_paginated_follows_next_link(respx_mock: respx.MockRouter) -> None:
    first = f"{BASE_URL}/api/events/demo/submissions/"
    second = f"{BASE_URL}/api/events/demo/submissions/?page=2"
    respx_mock.get(first).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "count": 3,
                    "next": second,
                    "results": [{"code": "A1"}, {"code": "B2"}],
                },
            ),
            httpx.Response(
                200,
                json={"count": 3, "next": None, "results": [{"code": "C3"}]},
            ),
        ]
    )

    async with PretalxClient(make_settings()) as client:
        results = await client.get_paginated("/api/events/demo/submissions/")

        assert [item["code"] for item in results] == ["A1", "B2", "C3"]
        assert client.last_pagination == PaginationMeta(
            truncated=False,
            total_count=3,
            pages_fetched=2,
        )


@pytest.mark.asyncio
async def test_get_paginated_rejects_changed_host_or_scheme(
    respx_mock: respx.MockRouter,
) -> None:
    first = f"{BASE_URL}/api/events/demo/submissions/"
    respx_mock.get(first).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 2,
                "next": "https://evil.example/api/events/demo/submissions/?page=2",
                "results": [{"code": "A1"}],
            },
        )
    )

    async with PretalxClient(make_settings()) as client:
        with pytest.raises(PretalxClientError, match="scheme or host changed"):
            await client.get_paginated("/api/events/demo/submissions/")


@pytest.mark.asyncio
async def test_get_paginated_marks_truncated_when_max_pages_hit(
    respx_mock: respx.MockRouter,
) -> None:
    first = f"{BASE_URL}/api/events/demo/submissions/"
    second = f"{BASE_URL}/api/events/demo/submissions/?page=2"
    respx_mock.get(first).mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 4,
                "next": second,
                "results": [{"code": "A1"}, {"code": "B2"}],
            },
        )
    )

    async with PretalxClient(make_settings()) as client:
        results = await client.get_paginated("/api/events/demo/submissions/", max_pages=1)

        assert [item["code"] for item in results] == ["A1", "B2"]
        assert client.last_pagination == PaginationMeta(
            truncated=True,
            total_count=4,
            pages_fetched=1,
        )


@pytest.mark.asyncio
async def test_get_paginated_marks_truncated_when_max_results_hit(
    respx_mock: respx.MockRouter,
) -> None:
    first = f"{BASE_URL}/api/events/demo/submissions/"
    second = f"{BASE_URL}/api/events/demo/submissions/?page=2"
    respx_mock.get(first).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "count": 4,
                    "next": second,
                    "results": [{"code": "A1"}, {"code": "B2"}],
                },
            ),
            httpx.Response(
                200,
                json={
                    "count": 4,
                    "next": None,
                    "results": [{"code": "C3"}, {"code": "D4"}],
                },
            ),
        ]
    )

    async with PretalxClient(make_settings()) as client:
        results = await client.get_paginated("/api/events/demo/submissions/", max_results=3)

        assert [item["code"] for item in results] == ["A1", "B2", "C3"]
        assert client.last_pagination == PaginationMeta(
            truncated=True,
            total_count=4,
            pages_fetched=2,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "Unauthorised: check PRETALX_API_TOKEN."),
        (403, "Forbidden: token does not have permission for this resource."),
        (404, "Not found: requested pretalx resource does not exist."),
        (429, "Rate-limited by pretalx API. Please retry later."),
        (503, "Pretalx server error (503). Try again later."),
    ],
)
async def test_http_status_errors_are_mapped(
    respx_mock: respx.MockRouter,
    status_code: int,
    message: str,
) -> None:
    respx_mock.get(f"{BASE_URL}/api/events/").mock(return_value=httpx.Response(status_code))

    async with PretalxClient(make_settings()) as client:
        with pytest.raises(PretalxClientError, match=re.escape(message)):
            await client.get("/api/events/")


@pytest.mark.asyncio
async def test_timeout_maps_to_friendly_error(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/api/events/").mock(
        side_effect=httpx.ReadTimeout("timed out"),
    )

    async with PretalxClient(make_settings()) as client:
        with pytest.raises(
            PretalxClientError,
            match="Connection timeout while contacting the pretalx API",
        ):
            await client.get("/api/events/")


def test_multilingual_field_resolution_helper() -> None:
    client = PretalxClient(make_settings())

    value = {"fr": " Bonjour ", "en": "Hello", "de": "Hallo"}
    assert client.resolve_multilingual_field(value, preferred="fr-FR") == "Bonjour"
    assert client.resolve_multilingual_field(value, preferred="it-IT") == "Hello"
    assert client.resolve_multilingual_field("  plain value  ") == "plain value"
