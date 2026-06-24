"""Tool module registrations."""

from pretalx_mcp.tools.events import register_event_tools
from pretalx_mcp.tools.reviews import register_review_tools
from pretalx_mcp.tools.schedule import register_schedule_tools
from pretalx_mcp.tools.speakers import register_speaker_tools
from pretalx_mcp.tools.submissions import register_submission_tools

__all__ = [
    "register_event_tools",
    "register_review_tools",
    "register_schedule_tools",
    "register_speaker_tools",
    "register_submission_tools",
]
