from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pretalx_mcp.config import Settings

BASE_URL = "https://pretalx.example"


class ToolRegistry:
    """Tiny FastMCP test double that records tool functions by name."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(
        self,
        *,
        name: str,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return decorator


def make_settings(*, default_event: str | None = "demo") -> Settings:
    return Settings(base_url=BASE_URL, default_event=default_event, _env_file=None)
