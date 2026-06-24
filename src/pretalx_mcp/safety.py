"""Read-only safety helpers."""

from __future__ import annotations

from pretalx_mcp.config import Settings


def require_write_enabled(settings: Settings) -> None:
    """Raise if write operations are attempted in read-only mode."""

    if settings.read_only:
        msg = "This MCP server is running in read-only mode."
        raise RuntimeError(msg)
