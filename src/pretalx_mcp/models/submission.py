"""Typed submission payload models."""

from __future__ import annotations

from typing import TypedDict

LocalizedValue = str | dict[str, str]


class NamedReference(TypedDict, total=False):
    code: str
    slug: str
    name: LocalizedValue


class SubmissionSpeaker(TypedDict, total=False):
    code: str
    name: str


class SubmissionModel(TypedDict, total=False):
    code: str
    title: LocalizedValue
    abstract: LocalizedValue
    description: LocalizedValue
    state: str
    duration: int
    track: NamedReference | str
    submission_type: NamedReference | str
    tags: list[str]
    speakers: list[SubmissionSpeaker | str]
