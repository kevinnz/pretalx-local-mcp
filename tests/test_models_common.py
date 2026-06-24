from __future__ import annotations

from pretalx_mcp.models.common import (
    compact_event,
    compact_schedule_session,
    compact_speaker,
    compact_submission,
    resolve_locale,
    truncate_text,
)


def test_resolve_locale_prefers_preferred_then_english_then_first_available() -> None:
    value = {"fr": " Bonjour ", "en": "Hello", "de": "Hallo"}

    assert resolve_locale(value, preferred="fr-FR") == "Bonjour"
    assert resolve_locale(value, preferred="it-IT") == "Hello"
    assert resolve_locale({"de": " Guten Tag ", "fr": "Salut"}, preferred="it") == "Guten Tag"
    assert resolve_locale("  plain text  ") == "plain text"
    assert resolve_locale(None) is None


def test_truncate_text_handles_boundaries() -> None:
    assert truncate_text(None) is None
    assert truncate_text("  abc  ", max_length=3) == "abc"
    assert truncate_text("abcd", max_length=3) == "ab…"
    assert truncate_text("abcd", max_length=1) == "…"
    assert truncate_text("abcd", max_length=0) == "…"


def test_compact_event_and_submission_fields() -> None:
    event = compact_event(
        {
            "slug": "demo",
            "name": {"en": " Demo Event "},
            "date_from": "2026-09-01",
            "date_to": "2026-09-03",
            "timezone": "Pacific/Auckland",
            "is_public": True,
            "public_url": "https://pretalx.example/demo",
            "ignored": "value",
        }
    )
    assert event == {
        "slug": "demo",
        "name": "Demo Event",
        "date_from": "2026-09-01",
        "date_to": "2026-09-03",
        "timezone": "Pacific/Auckland",
        "is_public": True,
        "url": "https://pretalx.example/demo",
    }

    abstract = "x" * 510
    submission = compact_submission(
        {
            "code": "SUB1",
            "title": {"en": "  Keynote  "},
            "state": "accepted",
            "submission_type": {"name": {"en": "Talk"}},
            "track": {"slug": "data-eng"},
            "speakers": [{"name": " Ada "}, "Bob"],
            "tags": ["ml", ""],
            "duration": 45,
            "abstract": abstract,
        }
    )

    assert submission["code"] == "SUB1"
    assert submission["title"] == "Keynote"
    assert submission["state"] == "accepted"
    assert submission["submission_type"] == "Talk"
    assert submission["track"] == "data-eng"
    assert submission["speakers"] == ["Ada", "Bob"]
    assert submission["tags"] == ["ml"]
    assert submission["duration"] == 45
    assert submission["abstract"].endswith("…")
    assert len(submission["abstract"]) == 500


def test_compact_speaker_and_schedule_session_fields() -> None:
    speaker = compact_speaker(
        {
            "code": "SP1",
            "name": " Ada ",
            "biography": {"en": "Systems engineer"},
            "submissions": [{"code": "S1"}, {"code": "S2"}],
        }
    )
    assert speaker == {
        "code": "SP1",
        "name": "Ada",
        "biography": "Systems engineer",
        "submission_count": 2,
    }

    session = compact_schedule_session(
        {
            "code": "A1",
            "title": {"en": "Opening"},
            "start": "2026-09-12T09:00:00+00:00",
            "end": "2026-09-12T10:00:00+00:00",
            "room": {"name": {"en": "Main Hall"}},
            "track": {"name": {"en": "General"}},
            "speakers": [{"name": "Ada"}],
        }
    )
    assert session == {
        "code": "A1",
        "title": "Opening",
        "start": "2026-09-12T09:00:00+00:00",
        "end": "2026-09-12T10:00:00+00:00",
        "room": "Main Hall",
        "track": "General",
        "speakers": ["Ada"],
    }
