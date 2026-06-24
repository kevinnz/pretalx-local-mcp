"""Event tool registrations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pretalx_mcp.models.common import compact_event, resolve_locale

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pretalx_mcp.config import Settings
    from pretalx_mcp.pretalx_client import PretalxClient

_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 500


def register_event_tools(mcp: FastMCP, client: PretalxClient, settings: Settings) -> None:
    """Register event-focused MCP tools."""

    @mcp.tool(name="pretalx_list_events")
    async def pretalx_list_events(
        limit: int = _DEFAULT_LIST_LIMIT,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """List visible events in a compact form."""

        applied_limit = _normalise_limit(limit, max_limit=_MAX_LIST_LIMIT)
        raw_events = await client.get_paginated(
            "/api/events/",
            params={"limit": applied_limit},
            max_pages=10,
            max_results=applied_limit,
        )

        compact_events = [compact_event(event) for event in raw_events]
        returned_count = len(compact_events)
        total_count = client.last_pagination.total_count
        truncated = client.last_pagination.truncated or (
            total_count is not None and returned_count < total_count
        )

        result: dict[str, Any] = {
            "events": compact_events,
            "returned_count": returned_count,
            "truncated": truncated,
        }
        if total_count is not None:
            result["total_count"] = total_count
        if applied_limit != limit:
            result["applied_limit"] = applied_limit
        if include_raw:
            result["raw_events"] = raw_events
        return result

    @mcp.tool(name="pretalx_get_event")
    async def pretalx_get_event(
        event: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Fetch one event in detail."""

        event_slug = _resolve_event_slug(event, settings.default_event)
        payload = await client.get(f"/api/events/{event_slug}/")
        if not isinstance(payload, Mapping):
            msg = "Pretalx API returned an unexpected payload while loading the event."
            raise RuntimeError(msg)

        raw_event = dict(payload)
        detail = _shape_event_detail(raw_event)
        result: dict[str, Any] = {"event": detail}
        if include_raw:
            result["raw_event"] = raw_event
        return result


def _resolve_event_slug(event: str | None, default_event: str | None) -> str:
    for value in (event, default_event):
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    msg = "Event slug is required. Pass event='<slug>' or set PRETALX_DEFAULT_EVENT."
    raise RuntimeError(msg)


def _normalise_limit(limit: int, max_limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        msg = "limit must be a positive integer."
        raise RuntimeError(msg)
    if limit < 1:
        msg = "limit must be at least 1."
        raise RuntimeError(msg)
    return min(limit, max_limit)


def _shape_event_detail(raw: Mapping[str, Any]) -> dict[str, Any]:
    detail = dict(raw)
    resolved_name = resolve_locale(_mapping_or_value(raw.get("name")))
    if resolved_name is not None:
        detail["name"] = resolved_name
    return detail


def _mapping_or_value(value: Any) -> str | Mapping[str, Any] | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return value
    text = str(value).strip()
    return text or None
