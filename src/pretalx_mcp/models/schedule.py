"""Typed schedule payload models."""

from __future__ import annotations

from typing import Any, TypedDict

LocalizedValue = str | dict[str, str]


class ScheduleSpeaker(TypedDict, total=False):
    code: str
    name: str


class ScheduleSessionModel(TypedDict, total=False):
    code: str
    title: LocalizedValue
    start: str
    end: str
    room: str | dict[str, Any]
    track: LocalizedValue | dict[str, Any]
    speakers: list[ScheduleSpeaker | str]


class ScheduleDayModel(TypedDict, total=False):
    index: int
    date: str
    rooms: dict[str, list[ScheduleSessionModel]]


class ScheduleModel(TypedDict, total=False):
    version: str
    conference: dict[str, Any]
