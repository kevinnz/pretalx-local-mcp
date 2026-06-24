"""Typed event payload models."""

from __future__ import annotations

from typing import TypedDict

LocalizedValue = str | dict[str, str]


class EventModel(TypedDict, total=False):
    slug: str
    name: LocalizedValue
    timezone: str
    date_from: str
    date_to: str
    is_public: bool
    is_live: bool
    url: str
    public_url: str
