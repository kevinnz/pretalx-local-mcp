"""Speaker MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pretalx_mcp.models.common import compact_speaker, resolve_locale
from pretalx_mcp.pretalx_client import PretalxClientError

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pretalx_mcp.config import Settings
    from pretalx_mcp.pretalx_client import PretalxClient


MAX_SEARCH_PAGES = 10


def register_speaker_tools(mcp: FastMCP, client: PretalxClient, settings: Settings) -> None:
    """Register speaker tools."""

    @mcp.tool(name="pretalx_list_speakers")
    async def pretalx_list_speakers(
        event: str | None = None,
        limit: int = 100,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """List speakers for an event with compact output."""

        event_slug = _resolve_event_slug(event, settings)
        max_results = _validate_limit(limit, field_name="limit")

        speakers = await client.get_paginated(
            f"/api/events/{event_slug}/speakers/",
            max_pages=MAX_SEARCH_PAGES,
            max_results=max_results,
        )

        pagination = client.last_pagination
        compact_results = [compact_speaker(item) for item in speakers]
        total_count = (
            pagination.total_count if pagination.total_count is not None else len(compact_results)
        )

        result: dict[str, Any] = {
            "event": event_slug,
            "returned_count": len(compact_results),
            "total_count": total_count,
            "truncated": bool(pagination.truncated),
            "speakers": compact_results,
        }
        if include_raw:
            result["raw"] = speakers
        return result

    @mcp.tool(name="pretalx_get_speaker")
    async def pretalx_get_speaker(
        event: str | None = None,
        speaker: str = "",
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Fetch one speaker profile with submission context."""

        event_slug = _resolve_event_slug(event, settings)
        speaker_code = _require_text(speaker, field_name="speaker")

        try:
            payload = await client.get(f"/api/events/{event_slug}/speakers/{speaker_code}/")
        except PretalxClientError as exc:
            if _is_not_found(exc):
                msg = f"Speaker '{speaker_code}' was not found in event '{event_slug}'."
                raise ValueError(msg) from exc
            raise

        if not isinstance(payload, Mapping):
            msg = "Pretalx API returned an unexpected speaker payload."
            raise RuntimeError(msg)

        speaker_detail = _build_speaker_detail(payload)
        result: dict[str, Any] = {
            "event": event_slug,
            "speaker": speaker_detail,
        }
        if include_raw:
            result["raw"] = dict(payload)
        return result

    @mcp.tool(name="pretalx_search_speakers")
    async def pretalx_search_speakers(
        event: str | None = None,
        query: str = "",
        limit: int = 25,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Search speakers by name/email server-side and bio/submission titles locally."""

        event_slug = _resolve_event_slug(event, settings)
        query_text = _require_text(query, field_name="query")
        max_results = _validate_limit(limit, field_name="limit")

        path = f"/api/events/{event_slug}/speakers/"
        server_side = await client.get_paginated(
            path,
            params={"q": query_text},
            max_pages=MAX_SEARCH_PAGES,
        )

        local_pool = await client.get_paginated(path, max_pages=MAX_SEARCH_PAGES)
        merged = _merge_speakers(server_side, local_pool)

        query_folded = query_text.casefold()
        matched = [
            speaker_item for speaker_item in merged if _matches_query(speaker_item, query_folded)
        ]
        limited = matched[:max_results]

        result: dict[str, Any] = {
            "event": event_slug,
            "query": query_text,
            "total_count": len(matched),
            "returned_count": len(limited),
            "truncated": len(matched) > len(limited),
            "speakers": [compact_speaker(item) for item in limited],
        }
        if include_raw:
            result["raw"] = limited
        return result


def _resolve_event_slug(event: str | None, settings: Settings) -> str:
    candidate = event if event is not None else settings.default_event
    if candidate is None:
        msg = "Event slug is required. Provide 'event' or set PRETALX_DEFAULT_EVENT."
        raise ValueError(msg)

    slug = candidate.strip()
    if not slug:
        msg = "Event slug is required. Provide 'event' or set PRETALX_DEFAULT_EVENT."
        raise ValueError(msg)
    return slug


def _validate_limit(value: int, field_name: str) -> int:
    if value < 1:
        msg = f"{field_name} must be at least 1."
        raise ValueError(msg)
    return value


def _require_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        msg = f"{field_name} is required."
        raise ValueError(msg)
    return cleaned


def _is_not_found(exc: PretalxClientError) -> bool:
    return "not found" in str(exc).casefold()


def _merge_speakers(
    preferred: list[dict[str, Any]],
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def add(item: Mapping[str, Any]) -> None:
        key = _speaker_key(item)
        if key not in merged:
            merged[key] = dict(item)

    for entry in preferred:
        add(entry)
    for entry in fallback:
        add(entry)
    return list(merged.values())


def _speaker_key(item: Mapping[str, Any]) -> str:
    code = _clean_text(item.get("code"))
    if code:
        return f"code:{code.casefold()}"

    name = _clean_text(item.get("name")) or ""
    email = _clean_text(item.get("email")) or ""
    return f"fallback:{name.casefold()}::{email.casefold()}"


def _matches_query(item: Mapping[str, Any], query_folded: str) -> bool:
    fields: list[str] = []

    for candidate in (item.get("name"), item.get("email"), _resolve_text(item.get("biography"))):
        text = _clean_text(candidate)
        if text:
            fields.append(text)

    submissions = item.get("submissions")
    if isinstance(submissions, list):
        for submission in submissions:
            if isinstance(submission, Mapping):
                title = _resolve_text(submission.get("title"))
                if title:
                    fields.append(title)
            else:
                text = _clean_text(submission)
                if text:
                    fields.append(text)

    return any(query_folded in field.casefold() for field in fields)


def _build_speaker_detail(item: Mapping[str, Any]) -> dict[str, Any]:
    submissions = _normalise_submission_refs(item.get("submissions"))

    detail = {
        "code": _clean_text(item.get("code")),
        "name": _clean_text(item.get("name")),
        "email": _clean_text(item.get("email")),
        "biography": _resolve_text(item.get("biography")),
        "avatar": item.get("avatar"),
        "avatar_thumbnail": item.get("avatar_thumbnail"),
        "locale": _clean_text(item.get("locale")),
        "resource_uri": _clean_text(item.get("resource_uri")),
        "submission_count": len(submissions),
        "submissions": submissions,
        "answers": item.get("answers") if isinstance(item.get("answers"), list) else None,
        "availabilities": (
            item.get("availabilities") if isinstance(item.get("availabilities"), list) else None
        ),
    }
    return _drop_empty(detail)


def _normalise_submission_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalised: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, Mapping):
            submission = {
                "code": _clean_text(entry.get("code")),
                "title": _resolve_text(entry.get("title")),
                "state": _clean_text(entry.get("state")),
                "track": _named_value(entry.get("track")),
                "submission_type": _named_value(entry.get("submission_type")),
            }
            compact = _drop_empty(submission)
            if compact:
                normalised.append(compact)
            continue

        code = _clean_text(entry)
        if code:
            normalised.append({"code": code})

    return normalised


def _named_value(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        return _resolve_text(value.get("name")) or _clean_text(value.get("slug"))
    return _clean_text(value)


def _resolve_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return resolve_locale(value)
    return _clean_text(value)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _drop_empty(raw: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        result[key] = value
    return result
