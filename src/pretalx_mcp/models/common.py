"""Shared data shaping helpers for tool output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resolve_locale(
    value: str | Mapping[str, Any] | None,
    preferred: str | None = None,
) -> str | None:
    """Resolve plain or multilingual values to a single string."""

    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if not isinstance(value, Mapping):
        return _clean_text(str(value))

    locale_candidates: list[str] = []
    if preferred:
        locale_candidates.append(preferred)
        if "-" in preferred:
            locale_candidates.append(preferred.split("-", 1)[0])

    locale_candidates.extend(["en", "en-us", "en-gb"])

    for locale in locale_candidates:
        candidate = _clean_text(value.get(locale))
        if candidate is not None:
            return candidate

    for candidate in value.values():
        cleaned = _clean_text(candidate)
        if cleaned is not None:
            return cleaned
    return None


def truncate_text(value: str | None, max_length: int = 500) -> str | None:
    """Truncate a string and append an ellipsis when it exceeds max_length."""

    if value is None:
        return None
    if max_length < 1:
        return "…"
    text = value.strip()
    if len(text) <= max_length:
        return text
    if max_length == 1:
        return "…"
    truncated = text[: max_length - 1].rstrip()
    return f"{truncated}…"


def compact_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact event projection suitable for list/search views."""

    compact = {
        "slug": raw.get("slug"),
        "name": resolve_locale(_mapping_or_value(raw.get("name"))),
        "date_from": raw.get("date_from"),
        "date_to": raw.get("date_to"),
        "timezone": raw.get("timezone"),
        "is_public": raw.get("is_public"),
        "url": raw.get("url") or raw.get("public_url"),
    }
    return _drop_empty(compact)


def compact_submission(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact submission projection suitable for list/search views."""

    compact = {
        "code": raw.get("code"),
        "title": resolve_locale(_mapping_or_value(raw.get("title"))),
        "state": raw.get("state"),
        "submission_type": _resolve_named_field(raw.get("submission_type")),
        "track": _resolve_named_field(raw.get("track")),
        "speakers": _extract_names(raw.get("speakers")),
        "tags": _extract_tags(raw.get("tags")),
        "duration": raw.get("duration"),
        "abstract": truncate_text(resolve_locale(_mapping_or_value(raw.get("abstract")))),
    }
    return _drop_empty(compact)


def compact_speaker(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact speaker projection suitable for list/search views."""

    compact = {
        "code": raw.get("code"),
        "name": _clean_text(raw.get("name")),
        "email": _clean_text(raw.get("email")),
        "biography": truncate_text(resolve_locale(_mapping_or_value(raw.get("biography")))),
        "submission_count": _submission_count(raw.get("submissions")),
    }
    return _drop_empty(compact)


def compact_schedule_session(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact schedule session projection."""

    compact = {
        "code": raw.get("code"),
        "title": resolve_locale(_mapping_or_value(raw.get("title"))),
        "start": raw.get("start"),
        "end": raw.get("end"),
        "room": _resolve_named_field(raw.get("room")),
        "track": _resolve_named_field(raw.get("track")),
        "speakers": _extract_names(raw.get("speakers")),
    }
    return _drop_empty(compact)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
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


def _extract_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = _clean_text(item)
            if cleaned:
                names.append(cleaned)
            continue
        if isinstance(item, Mapping):
            candidate = _clean_text(item.get("name") or item.get("speaker"))
            if candidate:
                names.append(candidate)
    return names


def _extract_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        cleaned = _clean_text(item)
        if cleaned:
            tags.append(cleaned)
    return tags


def _resolve_named_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        named = resolve_locale(_mapping_or_value(value.get("name")))
        if named:
            return named
        return _clean_text(value.get("slug") or value.get("code"))
    return _clean_text(value)


def _submission_count(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    return None


def _mapping_or_value(value: Any) -> str | Mapping[str, Any] | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return value
    return _clean_text(value)
