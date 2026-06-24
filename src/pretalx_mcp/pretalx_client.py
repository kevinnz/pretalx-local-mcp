"""Async pretalx API client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from pretalx_mcp.config import Settings
from pretalx_mcp.models.common import resolve_locale

JsonObject = dict[str, Any]
JsonArray = list[JsonObject]


class PretalxClientError(RuntimeError):
    """Raised when pretalx API requests fail with user-facing messages."""


@dataclass(frozen=True, slots=True)
class PaginationMeta:
    """Metadata from the last paginated query."""

    truncated: bool = False
    total_count: int | None = None
    pages_fetched: int = 0


class PretalxClient:
    """Outbound-only async client for pretalx REST API."""

    user_agent = "pretalx-mcp/0.1.0"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.base_url
        self._base_parts = urlsplit(self._base_url)
        self._client: httpx.AsyncClient | None = None
        self.last_pagination = PaginationMeta()

    async def __aenter__(self) -> PretalxClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying httpx client, if opened."""

        if self._client is None:
            return
        await self._client.aclose()
        self._client = None

    async def get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> JsonObject | list[Any]:
        """Perform a GET request and parse JSON body."""

        url = self._build_url(path)
        payload = await self._request_json(url, params=params)
        if isinstance(payload, (dict, list)):
            return payload
        msg = "Pretalx API returned an unexpected JSON payload."
        raise PretalxClientError(msg)

    async def get_paginated(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        max_pages: int = 10,
        max_results: int | None = None,
    ) -> JsonArray:
        """Fetch paginated list responses and flatten into a list of objects."""

        if max_pages < 1:
            msg = "max_pages must be at least 1."
            raise ValueError(msg)
        if max_results is not None and max_results < 1:
            msg = "max_results must be at least 1 when provided."
            raise ValueError(msg)

        next_url: str | None = self._build_url(path)
        next_params = dict(params) if params else None

        pages_fetched = 0
        total_count: int | None = None
        truncated = False
        results: JsonArray = []

        while next_url and pages_fetched < max_pages:
            payload = await self._request_json(next_url, params=next_params)
            pages_fetched += 1
            next_params = None

            if isinstance(payload, list):
                results.extend(_to_object_list(payload))
                total_count = len(results)
                next_url = None
            elif isinstance(payload, dict):
                page_results = payload.get("results")
                if isinstance(page_results, list):
                    results.extend(_to_object_list(page_results))
                    count = payload.get("count")
                    if isinstance(count, int):
                        total_count = count
                    next_link = payload.get("next")
                    if isinstance(next_link, str) and next_link:
                        next_url = self._validate_next_url(next_link)
                    else:
                        next_url = None
                else:
                    results.append(payload)
                    total_count = 1
                    next_url = None
            else:
                msg = "Pretalx API returned an unexpected JSON payload."
                raise PretalxClientError(msg)

            if max_results is not None and len(results) >= max_results:
                results = results[:max_results]
                truncated = True
                break

        if next_url and pages_fetched >= max_pages:
            truncated = True

        self.last_pagination = PaginationMeta(
            truncated=truncated,
            total_count=total_count,
            pages_fetched=pages_fetched,
        )
        return results

    def resolve_multilingual_field(
        self,
        value: str | Mapping[str, Any] | None,
        preferred: str | None = None,
    ) -> str | None:
        """Resolve multilingual pretalx fields to one string value."""

        return resolve_locale(value, preferred=preferred)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client

        headers = {"User-Agent": self.user_agent}
        if self._settings.api_token:
            headers["Authorization"] = f"Token {self._settings.api_token}"

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.timeout_seconds),
            verify=self._settings.verify_tls,
            headers=headers,
        )
        return self._client

    def _build_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        relative = path if path.startswith("/") else f"/{path}"
        return f"{self._base_url}{relative}"

    def _validate_next_url(self, next_url: str) -> str:
        parsed = urlsplit(next_url)
        if not parsed.scheme and not parsed.netloc:
            return self._build_url(next_url)

        if (parsed.scheme, parsed.netloc) != (self._base_parts.scheme, self._base_parts.netloc):
            msg = "Pagination next link rejected: URL scheme or host changed from PRETALX_BASE_URL."
            raise PretalxClientError(msg)
        return next_url

    async def _request_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        client = await self._ensure_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            msg = "Connection timeout while contacting the pretalx API."
            raise PretalxClientError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = _status_to_message(exc.response.status_code)
            raise PretalxClientError(msg) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to contact pretalx API: {exc}."
            raise PretalxClientError(msg) from exc

        try:
            return response.json()
        except ValueError as exc:
            msg = "Pretalx API returned invalid JSON."
            raise PretalxClientError(msg) from exc


def _status_to_message(status_code: int) -> str:
    if status_code == 401:
        return "Unauthorised: check PRETALX_API_TOKEN."
    if status_code == 403:
        return "Forbidden: token does not have permission for this resource."
    if status_code == 404:
        return "Not found: requested pretalx resource does not exist."
    if status_code == 429:
        return "Rate-limited by pretalx API. Please retry later."
    if status_code >= 500:
        return f"Pretalx server error ({status_code}). Try again later."
    return f"Pretalx API request failed with status {status_code}."


def _to_object_list(payload: list[Any]) -> JsonArray:
    results: JsonArray = []
    for item in payload:
        if isinstance(item, dict):
            results.append(item)
    return results
