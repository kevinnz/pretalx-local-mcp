"""Review MCP tools."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import TYPE_CHECKING, Any

from pretalx_mcp.models.common import compact_submission, resolve_locale
from pretalx_mcp.pretalx_client import PretalxClientError

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pretalx_mcp.config import Settings
    from pretalx_mcp.pretalx_client import PretalxClient


LOW_REVIEW_THRESHOLD = 2
MAX_REVIEW_PAGES = 10


@dataclass(slots=True)
class ReviewFetchResult:
    """Review fetch result from one of the endpoint strategies."""

    available: bool
    reviews: list[dict[str, Any]]
    source: str | None
    notes: list[str]


def register_review_tools(mcp: FastMCP, client: PretalxClient, settings: Settings) -> None:
    """Register review tools."""

    @mcp.tool(name="pretalx_get_submission_reviews")
    async def pretalx_get_submission_reviews(
        event: str | None = None,
        submission_code: str = "",
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Get reviews for one submission and degrade gracefully when unavailable."""

        event_slug = _resolve_event_slug(event, settings)
        code = _require_text(submission_code, field_name="submission_code")

        fetched = await _fetch_submission_reviews(client, event_slug, code)
        if not fetched.available:
            return {
                "available": False,
                "event": event_slug,
                "submission_code": code,
                "review_count": 0,
                "numeric_score_count": 0,
                "average_score": None,
                "reviews": [],
                "message": (
                    "Review data is unavailable for this submission with the current token "
                    "or pretalx API configuration."
                ),
                "notes": fetched.notes,
            }

        normalised = [
            _normalise_review(item, submission_code_hint=code) for item in fetched.reviews
        ]
        numeric_scores = [
            score
            for score in (item.get("score_numeric") for item in normalised)
            if isinstance(score, (int, float))
        ]

        result: dict[str, Any] = {
            "available": True,
            "event": event_slug,
            "submission_code": code,
            "source": fetched.source,
            "review_count": len(normalised),
            "numeric_score_count": len(numeric_scores),
            "average_score": _rounded_mean(numeric_scores),
            "reviews": normalised,
        }
        if fetched.notes:
            result["notes"] = fetched.notes
        if include_raw:
            result["raw"] = fetched.reviews
        return result

    @mcp.tool(name="pretalx_review_summary")
    async def pretalx_review_summary(event: str | None = None) -> dict[str, Any]:
        """Summarise review coverage and score trends for an event."""

        event_slug = _resolve_event_slug(event, settings)
        submissions = await client.get_paginated(
            f"/api/events/{event_slug}/submissions/",
            params={"expand": "track"},
            max_pages=MAX_REVIEW_PAGES,
        )

        fetched = await _fetch_event_reviews(client, event_slug, submissions)
        if not fetched.available:
            return {
                "available": False,
                "event": event_slug,
                "submission_count": len(submissions),
                "review_count": 0,
                "message": (
                    "Review summary is unavailable because review endpoints are not "
                    "accessible for this token/event."
                ),
                "notes": fetched.notes,
            }

        review_items = [_normalise_review(item) for item in fetched.reviews]
        reviews_by_submission: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for review in review_items:
            submission_code_value = _clean_text(review.get("submission_code"))
            if submission_code_value:
                reviews_by_submission[submission_code_value].append(review)

        submission_rows: list[dict[str, Any]] = []
        track_scores: dict[str, list[float]] = defaultdict(list)
        track_submission_counts: dict[str, int] = defaultdict(int)

        for submission in submissions:
            code = _clean_text(submission.get("code"))
            if not code:
                continue

            submission_reviews = reviews_by_submission.get(code, [])
            numeric_scores = [
                score
                for score in (review.get("score_numeric") for review in submission_reviews)
                if isinstance(score, (int, float))
            ]

            track_name = _track_name(submission) or "Untracked"
            track_submission_counts[track_name] += 1
            track_scores[track_name].extend(numeric_scores)

            row = {
                "code": code,
                "title": _resolve_text(submission.get("title")),
                "track": track_name,
                "review_count": len(submission_reviews),
                "average_score": _rounded_mean(numeric_scores),
            }
            submission_rows.append(row)

        no_reviews = [row for row in submission_rows if row["review_count"] == 0]
        low_reviews = [
            row for row in submission_rows if 0 < row["review_count"] < LOW_REVIEW_THRESHOLD
        ]
        scored_rows = [
            row for row in submission_rows if isinstance(row.get("average_score"), (int, float))
        ]

        track_summary = [
            {
                "track": track_name,
                "submission_count": track_submission_counts[track_name],
                "numeric_score_count": len(scores),
                "average_score": _rounded_mean(scores),
            }
            for track_name, scores in sorted(
                track_scores.items(), key=lambda item: item[0].casefold()
            )
        ]

        return {
            "available": True,
            "event": event_slug,
            "source": fetched.source,
            "submission_count": len(submission_rows),
            "review_count": len(review_items),
            "no_reviews_count": len(no_reviews),
            "low_review_threshold": LOW_REVIEW_THRESHOLD,
            "low_review_count": len(low_reviews),
            "average_scores_by_track": track_summary,
            "highest_scoring_submission": _max_by_average(scored_rows),
            "lowest_scoring_submission": _min_by_average(scored_rows),
            "no_reviews": no_reviews,
            "low_review_submissions": low_reviews,
            "submissions": [_compact_submission_row(submission) for submission in submissions],
            "notes": fetched.notes,
        }


async def _fetch_submission_reviews(
    client: PretalxClient,
    event_slug: str,
    submission_code: str,
) -> ReviewFetchResult:
    notes: list[str] = []

    candidates: tuple[tuple[str, str, dict[str, Any] | None, bool], ...] = (
        (
            "submission_reviews",
            f"/api/events/{event_slug}/submissions/{submission_code}/reviews/",
            None,
            False,
        ),
        (
            "event_reviews_by_submission",
            f"/api/events/{event_slug}/reviews/",
            {"submission": submission_code},
            True,
        ),
        (
            "event_reviews_by_proposal",
            f"/api/events/{event_slug}/reviews/",
            {"proposal": submission_code},
            True,
        ),
    )

    for source, path, params, needs_filter in candidates:
        try:
            payload = await client.get_paginated(path, params=params, max_pages=MAX_REVIEW_PAGES)
        except PretalxClientError as exc:
            if _is_review_endpoint_unavailable(exc):
                notes.append(str(exc))
                continue
            raise

        reviews = payload
        if needs_filter:
            reviews = [
                item
                for item in payload
                if (_review_submission_code(item) or "").casefold() == submission_code.casefold()
            ]

        if not needs_filter:
            reviews = [_ensure_submission_code(item, submission_code) for item in reviews]

        return ReviewFetchResult(available=True, reviews=reviews, source=source, notes=notes)

    return ReviewFetchResult(available=False, reviews=[], source=None, notes=notes)


async def _fetch_event_reviews(
    client: PretalxClient,
    event_slug: str,
    submissions: list[dict[str, Any]],
) -> ReviewFetchResult:
    notes: list[str] = []

    for source, path in (
        ("event_reviews", f"/api/events/{event_slug}/reviews/"),
        ("submission_reviews_collection", f"/api/events/{event_slug}/submissions/reviews/"),
    ):
        try:
            payload = await client.get_paginated(path, max_pages=MAX_REVIEW_PAGES)
            return ReviewFetchResult(available=True, reviews=payload, source=source, notes=notes)
        except PretalxClientError as exc:
            if _is_review_endpoint_unavailable(exc):
                notes.append(str(exc))
                continue
            raise

    combined_reviews: list[dict[str, Any]] = []
    fallback_used = False

    for submission in submissions:
        code = _clean_text(submission.get("code"))
        if not code:
            continue

        fetched = await _fetch_submission_reviews(client, event_slug, code)
        if fetched.available:
            fallback_used = True
            combined_reviews.extend(fetched.reviews)
        else:
            notes.extend(fetched.notes)

    if fallback_used:
        return ReviewFetchResult(
            available=True,
            reviews=combined_reviews,
            source="submission_reviews_fallback",
            notes=notes,
        )

    return ReviewFetchResult(available=False, reviews=[], source=None, notes=notes)


def _normalise_review(
    value: Mapping[str, Any],
    submission_code_hint: str | None = None,
) -> dict[str, Any]:
    score_raw = value.get("score")
    score_values = _extract_numeric_values(score_raw)

    review = {
        "id": value.get("id") or value.get("pk"),
        "submission_code": _review_submission_code(value) or submission_code_hint,
        "reviewer": _reviewer_name(value),
        "score": score_raw,
        "score_numeric": _rounded_mean(score_values),
        "comment": _clean_text(
            value.get("text") or value.get("comment") or value.get("review") or value.get("summary")
        ),
        "created": value.get("created") or value.get("submitted"),
        "updated": value.get("updated") or value.get("modified"),
        "state": _clean_text(value.get("state")),
    }
    return _drop_empty(review, keep_none={"score_numeric"})


def _ensure_submission_code(value: Mapping[str, Any], submission_code: str) -> dict[str, Any]:
    as_dict = dict(value)
    if _review_submission_code(as_dict):
        return as_dict
    as_dict["submission"] = submission_code
    return as_dict


def _extract_numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []

    if isinstance(value, (int, float)):
        number = float(value)
        return [number] if isfinite(number) else []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            number = float(text)
        except ValueError:
            return []
        return [number] if isfinite(number) else []

    if isinstance(value, Mapping):
        numbers: list[float] = []
        for nested in value.values():
            numbers.extend(_extract_numeric_values(nested))
        return numbers

    if isinstance(value, list):
        numbers: list[float] = []
        for nested in value:
            numbers.extend(_extract_numeric_values(nested))
        return numbers

    return []


def _review_submission_code(review: Mapping[str, Any]) -> str | None:
    for field in ("submission", "proposal", "submission_code", "proposal_code"):
        value = review.get(field)
        if isinstance(value, Mapping):
            code = _clean_text(value.get("code") or value.get("submission_code"))
            if code:
                return code
        else:
            code = _clean_text(value)
            if code:
                return code
    return None


def _reviewer_name(review: Mapping[str, Any]) -> str | None:
    for field in ("reviewer", "user"):
        value = review.get(field)
        if isinstance(value, Mapping):
            for key in ("name", "full_name", "display_name", "username", "email"):
                name = _clean_text(value.get(key))
                if name:
                    return name
        else:
            name = _clean_text(value)
            if name:
                return name

    for field in ("reviewer_name", "user_name", "reviewed_by"):
        name = _clean_text(review.get(field))
        if name:
            return name

    return None


def _compact_submission_row(value: Mapping[str, Any]) -> dict[str, Any]:
    compact = compact_submission(value)
    compact["track"] = _track_name(value)
    return compact


def _max_by_average(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda item: float(item.get("average_score", float("-inf"))))


def _min_by_average(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return min(rows, key=lambda item: float(item.get("average_score", float("inf"))))


def _track_name(submission: Mapping[str, Any]) -> str | None:
    track = submission.get("track")
    if isinstance(track, str):
        return _clean_text(track)
    if isinstance(track, Mapping):
        return _resolve_text(track.get("name")) or _clean_text(track.get("slug"))
    return None


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


def _require_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        msg = f"{field_name} is required."
        raise ValueError(msg)
    return cleaned


def _is_review_endpoint_unavailable(exc: PretalxClientError) -> bool:
    text = str(exc).casefold()
    return any(token in text for token in ("forbidden", "not found", "status 405", "status 501"))


def _resolve_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return resolve_locale(value)
    return _clean_text(value)


def _rounded_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(fmean(values), 3)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _drop_empty(
    values: Mapping[str, Any],
    keep_none: set[str] | None = None,
) -> dict[str, Any]:
    keep_none = keep_none or set()
    result: dict[str, Any] = {}

    for key, value in values.items():
        if value is None and key not in keep_none:
            continue
        if isinstance(value, str) and not value:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        result[key] = value

    return result
