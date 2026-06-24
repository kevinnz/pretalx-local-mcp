"""FastMCP entrypoint for the local-only pretalx MCP server."""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP
from pydantic import ValidationError

from pretalx_mcp.config import Settings, get_settings
from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.events import register_event_tools
from pretalx_mcp.tools.reviews import register_review_tools
from pretalx_mcp.tools.schedule import register_schedule_tools
from pretalx_mcp.tools.speakers import register_speaker_tools
from pretalx_mcp.tools.submissions import register_submission_tools


def create_server(settings: Settings, client: PretalxClient) -> FastMCP:
    """Create a fresh MCP server instance and register tools."""

    mcp = FastMCP("pretalx")
    register_event_tools(mcp, client, settings)
    register_submission_tools(mcp, client, settings)
    register_speaker_tools(mcp, client, settings)
    register_schedule_tools(mcp, client, settings)
    register_review_tools(mcp, client, settings)
    return mcp


def main() -> None:
    """Run the MCP server with stdio transport."""

    try:
        settings = get_settings()
    except ValidationError as exc:
        msg = f"Invalid PRETALX_* configuration: {exc}"
        raise SystemExit(msg) from exc

    client = PretalxClient(settings)
    mcp = create_server(settings, client)

    try:
        mcp.run(transport="stdio")
    finally:
        asyncio.run(client.aclose())


if __name__ == "__main__":
    main()
