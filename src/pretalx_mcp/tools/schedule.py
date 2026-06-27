"""Schedule MCP tools."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pretalx_mcp.models.common import compact_schedule_session, resolve_locale
from pretalx_mcp.pretalx_client import PretalxClientError

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from pretalx_mcp.config import Settings
    from pretalx_mcp.pretalx_client import PretalxClient


MAX_SCHEDULE_PAGES = 10
SCHEDULE_EXPAND = "room,submission,submission.speakers,submission.track"


@dataclass(slots=True)
class ScheduleSnapshot:
    """Loaded schedule metadata and normalised sessions."""

    event: str
    schedule: dict[str, Any] | None
    schedules_raw: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    sessions_raw: list[dict[str, Any]]
    endpoint_used: str | None
    message: str | None


def register_schedule_tools(mcp: FastMCP, client: PretalxClient, settings: Settings) -> None:
    """Register schedule tools."""

    @mcp.tool(name="pretalx_get_schedule")
    async def pretalx_get_schedule(
        event: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Fetch and summarise the current schedule for an event."""

        event_slug = _resolve_event_slug(event, settings)
        snapshot = await _load_schedule_snapshot(client, event_slug)

        if snapshot.schedule is None:
            result: dict[str, Any] = {
                "event": event_slug,
                "available": False,
                "message": snapshot.message or "No published schedule is available for this event.",
                "session_count": 0,
                "day_count": 0,
                "room_count": 0,
                "days": [],
                "rooms": [],
                "sessions": [],
            }
            if include_raw:
                result["raw"] = {"schedules": snapshot.schedules_raw}
            return result

        day_counts = _count_by_day(snapshot.sessions)
        room_counts = _count_by_room(snapshot.sessions)
        start, end = _schedule_time_bounds(snapshot.sessions)

        summary: dict[str, Any] = {
            "event": event_slug,
            "available": True,
            "schedule_version": _clean_text(snapshot.schedule.get("version")) or "latest",
            "schedule_published": _is_published(snapshot.schedule),
            "endpoint_used": snapshot.endpoint_used,
            "session_count": len(snapshot.sessions),
            "day_count": len(day_counts),
            "room_count": len(room_counts),
            "days": [{"day": day, "session_count": count} for day, count in day_counts.items()],
            "rooms": [
                {"room": room, "session_count": count} for room, count in room_counts.items()
            ],
            "start": start,
            "end": end,
            "sessions": [compact_schedule_session(item) for item in snapshot.sessions],
        }
        if snapshot.message:
            summary["message"] = snapshot.message
        if include_raw:
            summary["raw"] = {
                "schedules": snapshot.schedules_raw,
                "sessions": snapshot.sessions_raw,
            }
        return summary

    @mcp.tool(name="pretalx_list_schedule_sessions")
    async def pretalx_list_schedule_sessions(
        event: str | None = None,
        day: str | None = None,
        room: str | None = None,
        speaker: str | None = None,
        track: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """Flatten schedule sessions with optional case-insensitive filters."""

        event_slug = _resolve_event_slug(event, settings)
        snapshot = await _load_schedule_snapshot(client, event_slug)

        if snapshot.schedule is None:
            result: dict[str, Any] = {
                "event": event_slug,
                "available": False,
                "message": snapshot.message or "No schedule is available for this event.",
                "total_count": 0,
                "returned_count": 0,
                "sessions": [],
            }
            if include_raw:
                result["raw"] = {"schedules": snapshot.schedules_raw}
            return result

        filters = {
            "day": _clean_text(day),
            "room": _clean_text(room),
            "speaker": _clean_text(speaker),
            "track": _clean_text(track),
        }

        filtered = [
            item
            for item in snapshot.sessions
            if _matches_filters(
                item,
                day_filter=filters["day"],
                room_filter=filters["room"],
                speaker_filter=filters["speaker"],
                track_filter=filters["track"],
            )
        ]

        result = {
            "event": event_slug,
            "available": True,
            "schedule_version": _clean_text(snapshot.schedule.get("version")) or "latest",
            "endpoint_used": snapshot.endpoint_used,
            "filters": _drop_empty(filters),
            "total_count": len(snapshot.sessions),
            "returned_count": len(filtered),
            "sessions": [compact_schedule_session(item) for item in filtered],
        }
        if include_raw:
            result["raw"] = filtered
        return result

    @mcp.tool(name="pretalx_find_schedule_conflicts")
    async def pretalx_find_schedule_conflicts(event: str | None = None) -> dict[str, Any]:
        """Detect potential overlaps and missing schedule data."""

        event_slug = _resolve_event_slug(event, settings)
        snapshot = await _load_schedule_snapshot(client, event_slug)

        if snapshot.schedule is None:
            return {
                "event": event_slug,
                "available": False,
                "message": snapshot.message or "No schedule is available for conflict analysis.",
                "counts": {
                    "speaker_overlaps": 0,
                    "room_overlaps": 0,
                    "missing_room": 0,
                    "missing_time": 0,
                    "total_conflicts": 0,
                },
                "speaker_overlaps": [],
                "room_overlaps": [],
                "missing_room": [],
                "missing_time": [],
            }

        conflicts = _detect_conflicts(snapshot.sessions)
        return {
            "event": event_slug,
            "available": True,
            "schedule_version": _clean_text(snapshot.schedule.get("version")) or "latest",
            "counts": {
                "speaker_overlaps": len(conflicts["speaker_overlaps"]),
                "room_overlaps": len(conflicts["room_overlaps"]),
                "missing_room": len(conflicts["missing_room"]),
                "missing_time": len(conflicts["missing_time"]),
                "total_conflicts": (
                    len(conflicts["speaker_overlaps"])
                    + len(conflicts["room_overlaps"])
                    + len(conflicts["missing_room"])
                    + len(conflicts["missing_time"])
                ),
            },
            "speaker_overlaps": conflicts["speaker_overlaps"],
            "room_overlaps": conflicts["room_overlaps"],
            "missing_room": conflicts["missing_room"],
            "missing_time": conflicts["missing_time"],
        }


async def _load_schedule_snapshot(client: PretalxClient, event_slug: str) -> ScheduleSnapshot:
    schedules = await client.get_paginated(
        f"/api/events/{event_slug}/schedules/",
        max_pages=MAX_SCHEDULE_PAGES,
    )

    selected, message = _select_schedule(schedules)
    if selected is None:
        return ScheduleSnapshot(
            event=event_slug,
            schedule=None,
            schedules_raw=schedules,
            sessions=[],
            sessions_raw=[],
            endpoint_used=None,
            message=message,
        )

    version = _clean_text(selected.get("version")) or "latest"
    try:
        sessions_raw, endpoint_used = await _fetch_schedule_items(client, event_slug, version)
    except PretalxClientError as exc:
        if "not found" in str(exc).casefold():
            return ScheduleSnapshot(
                event=event_slug,
                schedule=None,
                schedules_raw=schedules,
                sessions=[],
                sessions_raw=[],
                endpoint_used=None,
                message=(
                    f"Schedule version '{version}' exists but its sessions are not yet "
                    "accessible (talks/slots endpoints returned 404). "
                    "The schedule may not be published yet."
                ),
            )
        raise
    sessions = [_normalise_session(item) for item in sessions_raw]

    return ScheduleSnapshot(
        event=event_slug,
        schedule=selected,
        schedules_raw=schedules,
        sessions=sessions,
        sessions_raw=sessions_raw,
        endpoint_used=endpoint_used,
        message=message,
    )


def _select_schedule(
    schedules: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if not schedules:
        return None, "No schedule versions are available for this event yet."

    published = [item for item in schedules if _is_published(item)]
    if published:
        return published[0], None

    latest_named = next(
        (
            item
            for item in schedules
            if (_clean_text(item.get("version")) or "").casefold() == "latest"
        ),
        None,
    )
    if latest_named is not None:
        msg = "No published schedule found; using the latest available version."
        return latest_named, msg

    msg = "No published schedule found; using the newest available schedule version."
    return schedules[0], msg


async def _fetch_schedule_items(
    client: PretalxClient,
    event_slug: str,
    version: str,
) -> tuple[list[dict[str, Any]], str]:
    first_error: PretalxClientError | None = None

    for endpoint in ("talks", "slots"):
        path = f"/api/events/{event_slug}/schedules/{version}/{endpoint}/"
        try:
            payload = await client.get_paginated(
                path,
                params={"expand": SCHEDULE_EXPAND},
                max_pages=MAX_SCHEDULE_PAGES,
            )
            return payload, endpoint
        except PretalxClientError as exc:
            if first_error is None:
                first_error = exc

    if first_error is not None:
        raise first_error

    msg = "Failed to fetch schedule items from pretalx."
    raise RuntimeError(msg)


def _normalise_session(item: Mapping[str, Any]) -> dict[str, Any]:
    submission = item.get("submission") if isinstance(item.get("submission"), Mapping) else {}

    title = _resolve_text(item.get("title")) or _resolve_text(submission.get("title"))
    start = _clean_text(item.get("start"))
    end = _clean_text(item.get("end"))
    room = item.get("room")
    track = item.get("track") or submission.get("track")

    speakers = _normalise_speakers(item.get("speakers"))
    if not speakers:
        speakers = _normalise_speakers(submission.get("speakers"))

    session = {
        "code": _clean_text(item.get("code")) or _clean_text(submission.get("code")),
        "title": title,
        "start": start,
        "end": end,
        "room": room,
        "track": track,
        "speakers": speakers,
        "day": _day_from_start(start),
        "submission_code": _clean_text(submission.get("code")),
        "duration_minutes": _duration_minutes(start, end),
    }
    return _drop_empty(session)


def _normalise_speakers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    names: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            name = _clean_text(item.get("name") or item.get("speaker"))
        else:
            name = _clean_text(item)
        if name:
            names.append(name)
    return names


def _matches_filters(
    session: Mapping[str, Any],
    day_filter: str | None,
    room_filter: str | None,
    speaker_filter: str | None,
    track_filter: str | None,
) -> bool:
    if day_filter:
        day_folded = day_filter.casefold()
        day = _clean_text(session.get("day"))
        start = _clean_text(session.get("start"))
        if not (
            (day and day.casefold() == day_folded) or (start and day_folded in start.casefold())
        ):
            return False

    if room_filter:
        room_name = _room_name(session)
        if not room_name or room_filter.casefold() not in room_name.casefold():
            return False

    if speaker_filter:
        speaker_folded = speaker_filter.casefold()
        speakers = session.get("speakers") if isinstance(session.get("speakers"), list) else []
        if not any(speaker_folded in str(name).casefold() for name in speakers):
            return False

    if track_filter:
        track_name = _track_name(session)
        if not track_name or track_filter.casefold() not in track_name.casefold():
            return False

    return True


def _detect_conflicts(sessions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    speaker_overlaps: list[dict[str, Any]] = []
    room_overlaps: list[dict[str, Any]] = []
    missing_room: list[dict[str, Any]] = []
    missing_time: list[dict[str, Any]] = []

    timed_sessions: list[tuple[dict[str, Any], datetime, datetime]] = []

    for session in sessions:
        start = _parse_datetime(_clean_text(session.get("start")))
        end = _parse_datetime(_clean_text(session.get("end")))

        room_name = _room_name(session)
        if room_name is None:
            missing_room.append(
                {"session": compact_schedule_session(session), "reason": "missing_room"}
            )

        if start is None or end is None or end <= start:
            reason = "missing_start_or_end"
            if start is not None and end is not None and end <= start:
                reason = "end_before_or_equal_start"
            missing_time.append({"session": compact_schedule_session(session), "reason": reason})
            continue

        timed_sessions.append((session, start, end))

    speaker_groups: dict[str, list[tuple[str, dict[str, Any], datetime, datetime]]] = defaultdict(
        list
    )
    room_groups: dict[str, list[tuple[str, dict[str, Any], datetime, datetime]]] = defaultdict(list)

    for session, start, end in timed_sessions:
        for speaker in session.get("speakers", []):
            name = _clean_text(speaker)
            if name:
                speaker_groups[name.casefold()].append((name, session, start, end))

        room_name = _room_name(session)
        if room_name:
            room_groups[room_name.casefold()].append((room_name, session, start, end))

    for entries in speaker_groups.values():
        speaker_overlaps.extend(_pair_overlaps(entries, field_name="speaker"))

    for entries in room_groups.values():
        room_overlaps.extend(_pair_overlaps(entries, field_name="room"))

    return {
        "speaker_overlaps": speaker_overlaps,
        "room_overlaps": room_overlaps,
        "missing_room": missing_room,
        "missing_time": missing_time,
    }


def _pair_overlaps(
    entries: list[tuple[str, dict[str, Any], datetime, datetime]],
    field_name: str,
) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    ordered = sorted(entries, key=lambda item: item[2])

    for index, current in enumerate(ordered):
        current_label, current_session, current_start, current_end = current
        for other in ordered[index + 1 :]:
            _, other_session, other_start, other_end = other
            if other_start >= current_end:
                break
            if current_start < other_end and other_start < current_end:
                overlaps.append(
                    {
                        field_name: current_label,
                        "session_a": compact_schedule_session(current_session),
                        "session_b": compact_schedule_session(other_session),
                    }
                )
    return overlaps


def _count_by_day(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for session in sessions:
        day = _clean_text(session.get("day"))
        if day:
            counts[day] += 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _count_by_room(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for session in sessions:
        room = _room_name(session)
        if room:
            counts[room] += 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def _schedule_time_bounds(sessions: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    starts = [_parse_datetime(_clean_text(item.get("start"))) for item in sessions]
    ends = [_parse_datetime(_clean_text(item.get("end"))) for item in sessions]
    start_values = [value for value in starts if value is not None]
    end_values = [value for value in ends if value is not None]

    start = min(start_values).isoformat() if start_values else None
    end = max(end_values).isoformat() if end_values else None
    return start, end


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end)
    if start_dt is None or end_dt is None or end_dt <= start_dt:
        return None
    seconds = int((end_dt - start_dt).total_seconds())
    return seconds // 60


def _day_from_start(start: str | None) -> str | None:
    if not start:
        return None
    if "T" in start:
        return start.split("T", 1)[0]
    if " " in start:
        return start.split(" ", 1)[0]
    return start[:10] if len(start) >= 10 else start


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _room_name(session: Mapping[str, Any]) -> str | None:
    room = session.get("room")
    if isinstance(room, str):
        return _clean_text(room)
    if isinstance(room, Mapping):
        return _resolve_text(room.get("name")) or _clean_text(room.get("slug"))
    return None


def _track_name(session: Mapping[str, Any]) -> str | None:
    track = session.get("track")
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


def _is_published(schedule: Mapping[str, Any]) -> bool:
    for key in ("is_published", "published", "published_at", "released"):
        value = schedule.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


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


def _drop_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, str) and not item:
            continue
        if isinstance(item, (list, dict)) and not item:
            continue
        result[key] = item
    return result
