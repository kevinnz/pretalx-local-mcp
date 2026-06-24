"""Submission tool registrations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pretalx_mcp.models.common import compact_submission, resolve_locale, truncate_text

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pretalx_mcp.config import Settings
    from pretalx_mcp.pretalx_client import PretalxClient

_DEFAULT_LIST_LIMIT = 100
_DEFAULT_SEARCH_LIMIT = 25
_MAX_LIST_LIMIT = 500
_MAX_SEARCH_LIMIT = 200
_MAX_SEARCH_SCAN_LIMIT = 500
_SUMMARY_PAGE_SIZE = 100
_ALLOWED_GROUP_BY = {"state", "track", "submission_type", "speaker", "tag"}


@dataclass(slots=True)
class _RankedSubmission:
    raw: dict[str, Any]
    score: int
    source_priority: int


def register_submission_tools(mcp: FastMCP, client: PretalxClient, settings: Settings) -> None:
    """Register submission-focused MCP tools."""

    @mcp.tool(name="pretalx_list_submissions")
    async def pretalx_list_submissions(
        event: str | None = None,
        state: str | None = None,
        track: str | None = None,
        submission_type: str | None = None,
        limit: int = _DEFAULT_LIST_LIMIT,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """List submissions for an event with optional server-side filters."""

        event_slug = _resolve_event_slug(event, settings.default_event)
        applied_limit = _normalise_limit(limit, max_limit=_MAX_LIST_LIMIT)
        params = _build_submission_params(
            state=state,
            track=track,
            submission_type=submission_type,
            limit=applied_limit,
        )
        raw_submissions = await client.get_paginated(
            f"/api/events/{event_slug}/submissions/",
            params=params,
            max_pages=10,
            max_results=applied_limit,
        )

        compact_submissions = [compact_submission(submission) for submission in raw_submissions]
        returned_count = len(compact_submissions)
        total_count = client.last_pagination.total_count
        truncated = client.last_pagination.truncated or (
            total_count is not None and returned_count < total_count
        )

        result: dict[str, Any] = {
            "event": event_slug,
            "submissions": compact_submissions,
            "returned_count": returned_count,
            "truncated": truncated,
        }
        if total_count is not None:
            result["total_count"] = total_count
        if applied_limit != limit:
            result["applied_limit"] = applied_limit
        if include_raw:
            result["raw_submissions"] = raw_submissions
        return result

    @mcp.tool(name="pretalx_get_submission")
    async def pretalx_get_submission(
        event: str | None = None,
        submission_code: str = "",
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Fetch full details for one submission."""

        event_slug = _resolve_event_slug(event, settings.default_event)
        code = _require_text(submission_code, field_name="submission_code")
        payload = await client.get(f"/api/events/{event_slug}/submissions/{code}/")
        if not isinstance(payload, Mapping):
            msg = "Pretalx API returned an unexpected payload while loading the submission."
            raise RuntimeError(msg)

        raw_submission = dict(payload)
        detail = _shape_submission_detail(raw_submission)
        result: dict[str, Any] = {"event": event_slug, "submission": detail}
        if include_raw:
            result["raw_submission"] = raw_submission
        return result

    @mcp.tool(name="pretalx_search_submissions")
    async def pretalx_search_submissions(
        event: str | None = None,
        query: str = "",
        state: str | None = None,
        track: str | None = None,
        submission_type: str | None = None,
        limit: int = _DEFAULT_SEARCH_LIMIT,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Search submissions using server-side q plus local matching."""

        event_slug = _resolve_event_slug(event, settings.default_event)
        query_text = _require_text(query, field_name="query")
        query_norm = query_text.casefold()
        applied_limit = _normalise_limit(limit, max_limit=_MAX_SEARCH_LIMIT)

        endpoint = f"/api/events/{event_slug}/submissions/"
        base_params = _build_submission_params(
            state=state,
            track=track,
            submission_type=submission_type,
            limit=applied_limit,
        )
        server_params = {**base_params, "q": query_text}
        primary_results = await client.get_paginated(
            endpoint,
            params=server_params,
            max_pages=10,
            max_results=applied_limit,
        )
        primary_meta = client.last_pagination

        ranked: dict[str, _RankedSubmission] = {}
        for index, submission in enumerate(primary_results):
            score = max(_score_submission_match(submission, query_norm), 1)
            _merge_ranked_submission(
                ranked,
                submission,
                score=score,
                source_priority=2,
                index=index,
            )

        fallback_truncated = False
        if len(ranked) < applied_limit:
            fallback_page_size = min(max(applied_limit, 50), _MAX_LIST_LIMIT)
            fallback_scan_limit = min(max(applied_limit * 4, applied_limit), _MAX_SEARCH_SCAN_LIMIT)
            fallback_params = _build_submission_params(
                state=state,
                track=track,
                submission_type=submission_type,
                limit=fallback_page_size,
            )
            fallback_results = await client.get_paginated(
                endpoint,
                params=fallback_params,
                max_pages=10,
                max_results=fallback_scan_limit,
            )
            fallback_truncated = client.last_pagination.truncated

            for index, submission in enumerate(fallback_results, start=len(primary_results)):
                score = _score_submission_match(submission, query_norm)
                if score < 1:
                    continue
                _merge_ranked_submission(
                    ranked,
                    submission,
                    score=score,
                    source_priority=1,
                    index=index,
                )

        ranked_results = sorted(ranked.values(), key=_rank_sort_key)
        selected = ranked_results[:applied_limit]
        selected_raw = [match.raw for match in selected]
        compact_results = [compact_submission(submission) for submission in selected_raw]
        returned_count = len(compact_results)

        total_count = primary_meta.total_count
        if total_count is None:
            total_count = len(ranked_results)
        else:
            total_count = max(total_count, len(ranked_results))

        truncated = (
            primary_meta.truncated
            or fallback_truncated
            or len(ranked_results) > applied_limit
            or (total_count > returned_count)
        )

        result: dict[str, Any] = {
            "event": event_slug,
            "query": query_text,
            "submissions": compact_results,
            "returned_count": returned_count,
            "total_count": total_count,
            "truncated": truncated,
        }
        if applied_limit != limit:
            result["applied_limit"] = applied_limit
        if include_raw:
            result["raw_submissions"] = selected_raw
        return result

    @mcp.tool(name="pretalx_summarise_submissions")
    async def pretalx_summarise_submissions(
        event: str | None = None,
        group_by: str = "state",
    ) -> dict[str, Any]:
        """Summarise submissions grouped by one selected attribute."""

        event_slug = _resolve_event_slug(event, settings.default_event)
        group_key = _normalise_group_by(group_by)
        submissions = await client.get_paginated(
            f"/api/events/{event_slug}/submissions/",
            params={"limit": _SUMMARY_PAGE_SIZE},
            max_pages=10,
        )

        counts: Counter[str] = Counter()
        for submission in submissions:
            for value in _group_values(submission, group_key):
                counts[value] += 1

        grouped = [
            {"key": key, "count": count}
            for key, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )
        ]

        returned_count = len(submissions)
        total_count = client.last_pagination.total_count
        if total_count is None:
            total_count = returned_count
        truncated = client.last_pagination.truncated or (returned_count < total_count)

        return {
            "event": event_slug,
            "group_by": group_key,
            "total_submissions": returned_count,
            "total_count": total_count,
            "truncated": truncated,
            "groups": grouped,
        }


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


def _normalise_group_by(group_by: str) -> str:
    cleaned = group_by.strip().lower()
    if cleaned not in _ALLOWED_GROUP_BY:
        allowed = ", ".join(sorted(_ALLOWED_GROUP_BY))
        msg = f"group_by must be one of: {allowed}."
        raise RuntimeError(msg)
    return cleaned


def _build_submission_params(
    *,
    state: str | None,
    track: str | None,
    submission_type: str | None,
    limit: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}

    state_value = _clean_text(state)
    if state_value is not None:
        params["state"] = state_value

    track_value = _clean_text(track)
    if track_value is not None:
        params["track"] = track_value

    submission_type_value = _clean_text(submission_type)
    if submission_type_value is not None:
        params["submission_type"] = submission_type_value

    return params


def _shape_submission_detail(raw: Mapping[str, Any]) -> dict[str, Any]:
    detail = dict(raw)
    title = resolve_locale(_mapping_or_value(raw.get("title")))
    abstract = resolve_locale(_mapping_or_value(raw.get("abstract")))
    description = resolve_locale(_mapping_or_value(raw.get("description")))

    if title is not None:
        detail["title"] = title
    if abstract is not None:
        detail["abstract"] = abstract
        detail["abstract_preview"] = truncate_text(abstract)
    if description is not None:
        detail["description"] = description
        detail["description_preview"] = truncate_text(description)

    track_name = _resolve_named_field(raw.get("track"))
    if track_name is not None:
        detail["track_name"] = track_name

    submission_type_name = _resolve_named_field(raw.get("submission_type"))
    if submission_type_name is not None:
        detail["submission_type_name"] = submission_type_name

    speaker_names = _extract_speaker_names(raw.get("speakers"))
    if speaker_names:
        detail["speaker_names"] = speaker_names

    return detail


def _score_submission_match(raw: Mapping[str, Any], query: str) -> int:
    score = 0

    title = resolve_locale(_mapping_or_value(raw.get("title")))
    if _contains_text(title, query):
        score += 12
        if title and title.casefold() == query:
            score += 5

    if _contains_text(resolve_locale(_mapping_or_value(raw.get("abstract"))), query):
        score += 6
    if _contains_text(resolve_locale(_mapping_or_value(raw.get("description"))), query):
        score += 4
    if _contains_text(_resolve_named_field(raw.get("track")), query):
        score += 3
    if _contains_text(_resolve_named_field(raw.get("submission_type")), query):
        score += 2
    if _contains_text(_clean_text(raw.get("code")), query):
        score += 2
    if _contains_any(_extract_speaker_names(raw.get("speakers")), query):
        score += 8
    if _contains_any(_extract_tags(raw.get("tags")), query):
        score += 7

    return score


def _merge_ranked_submission(
    ranked: dict[str, _RankedSubmission],
    raw: Mapping[str, Any],
    *,
    score: int,
    source_priority: int,
    index: int,
) -> None:
    raw_submission = dict(raw)
    key = _submission_key(raw_submission, index=index)
    candidate = _RankedSubmission(raw=raw_submission, score=score, source_priority=source_priority)
    current = ranked.get(key)
    if current is None or (candidate.score, candidate.source_priority) > (
        current.score,
        current.source_priority,
    ):
        ranked[key] = candidate


def _rank_sort_key(value: _RankedSubmission) -> tuple[int, int, str, str]:
    title = resolve_locale(_mapping_or_value(value.raw.get("title"))) or ""
    code = _clean_text(value.raw.get("code")) or ""
    return (-value.score, -value.source_priority, title.casefold(), code.casefold())


def _group_values(raw: Mapping[str, Any], group_by: str) -> list[str]:
    if group_by == "state":
        return [_clean_text(raw.get("state")) or "unknown"]
    if group_by == "track":
        return [_resolve_named_field(raw.get("track")) or "unassigned"]
    if group_by == "submission_type":
        return [_resolve_named_field(raw.get("submission_type")) or "unassigned"]
    if group_by == "speaker":
        speakers = _extract_speaker_names(raw.get("speakers"))
        return list(dict.fromkeys(speakers)) or ["unspecified speaker"]
    tags = _extract_tags(raw.get("tags"))
    return list(dict.fromkeys(tags)) or ["untagged"]


def _resolve_named_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        name = resolve_locale(_mapping_or_value(value.get("name")))
        if name is not None:
            return name
        return _clean_text(value.get("slug") or value.get("code"))
    return _clean_text(value)


def _extract_speaker_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    names: list[str] = []
    for speaker in value:
        if isinstance(speaker, str):
            cleaned = _clean_text(speaker)
            if cleaned is not None:
                names.append(cleaned)
            continue
        if isinstance(speaker, Mapping):
            cleaned = _clean_text(speaker.get("name") or speaker.get("speaker"))
            if cleaned is not None:
                names.append(cleaned)
    return names


def _extract_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    tags: list[str] = []
    for tag in value:
        cleaned = _clean_text(tag)
        if cleaned is not None:
            tags.append(cleaned)
    return tags


def _mapping_or_value(value: Any) -> str | Mapping[str, Any] | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return value
    return _clean_text(value)


def _submission_key(raw: Mapping[str, Any], *, index: int) -> str:
    code = _clean_text(raw.get("code"))
    if code is not None:
        return f"code:{code.casefold()}"

    title = resolve_locale(_mapping_or_value(raw.get("title")))
    if title is not None:
        return f"title:{title.casefold()}:{index}"
    return f"index:{index}"


def _contains_any(values: list[str], query: str) -> bool:
    for value in values:
        if query in value.casefold():
            return True
    return False


def _contains_text(value: str | None, query: str) -> bool:
    return value is not None and query in value.casefold()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    cleaned = str(value).strip()
    return cleaned or None


def _require_text(value: str, *, field_name: str) -> str:
    cleaned = _clean_text(value)
    if cleaned is not None:
        return cleaned
    msg = f"{field_name} must be provided."
    raise RuntimeError(msg)
