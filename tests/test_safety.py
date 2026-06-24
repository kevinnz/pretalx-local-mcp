from __future__ import annotations

from pathlib import Path

import pytest

from pretalx_mcp.config import Settings
from pretalx_mcp.safety import require_write_enabled


def test_require_write_enabled_raises_in_read_only_mode() -> None:
    settings = Settings(base_url="https://pretalx.com", read_only=True, _env_file=None)

    with pytest.raises(RuntimeError, match="read-only mode"):
        require_write_enabled(settings)


def test_require_write_enabled_allows_when_writes_enabled() -> None:
    settings = Settings(base_url="https://pretalx.com", read_only=False, _env_file=None)

    require_write_enabled(settings)


def test_v1_exposes_no_write_tools() -> None:
    tools_dir = Path(__file__).resolve().parents[1] / "src" / "pretalx_mcp" / "tools"
    source = "\n".join(path.read_text() for path in tools_dir.glob("*.py"))

    forbidden_names = (
        "pretalx_create_submission",
        "pretalx_update_submission_state",
        "pretalx_add_submission_tag",
        "pretalx_update_speaker_note",
        "pretalx_create_schedule_slot",
        "pretalx_update_schedule_slot",
    )

    for name in forbidden_names:
        assert name not in source
