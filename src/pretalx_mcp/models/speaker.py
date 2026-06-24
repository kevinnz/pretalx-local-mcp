"""Typed speaker payload models."""

from __future__ import annotations

from typing import TypedDict

LocalizedValue = str | dict[str, str]


class SpeakerSubmissionRef(TypedDict, total=False):
    code: str
    title: LocalizedValue


class SpeakerModel(TypedDict, total=False):
    code: str
    name: str
    email: str
    biography: LocalizedValue
    submissions: list[SpeakerSubmissionRef]
