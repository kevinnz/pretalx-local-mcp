# Local-Only pretalx MCP Server Implementation Plan

## Goal

Build a **local-only MCP server** that lets local MCP clients such as GitHub Copilot, VS Code, Claude Desktop, Cursor, or other desktop MCP clients interact with a pretalx instance through the official pretalx API.

The server must run on the user's machine and must not expose a network service.

The first implementation should be **read-only** and focused on conference-organiser workflows:

- List events
- Inspect event configuration
- List submissions
- Search submissions
- Inspect one submission
- List speakers
- Get schedule data
- Optionally expose reviews, tracks, rooms, tags, and submission types

pretalx provides a REST-style API with token-based authentication. This MCP server wraps that API for local use only.

---

## Local-only constraints

This project must remain local-only.

### Required constraints

- The MCP server must run as a local process.
- The MCP server must use MCP `stdio` transport by default.
- The MCP server must not listen on `0.0.0.0`.
- The MCP server must not expose an HTTP API.
- The MCP server must not expose SSE, WebSocket, or remote MCP transport.
- The MCP server must not include Docker Compose examples that publish ports.
- The MCP server must not include instructions for deploying to cloud hosting.
- The MCP server must not store pretalx API tokens in source code.
- The MCP server must not write credentials to logs.
- The MCP server must be read-only by default.

### Allowed network activity

The only intended network activity is outbound HTTPS from the local MCP server to the configured pretalx instance.

Examples:

```text
Local MCP client -> local stdio MCP process -> outbound HTTPS -> pretalx
```

This is acceptable.

The following is **not** acceptable for v1:

```text
Remote user/browser/client -> hosted MCP server -> pretalx
```

---

## Security posture

The design should assume pretalx data may include sensitive conference information:

- Unpublished talk proposals
- Speaker contact details
- Private speaker notes
- Reviewer comments
- Review scores
- Scheduling information not yet public

Therefore:

- Prefer read-only API tokens.
- Use least-privilege pretalx API tokens.
- Scope tokens to the required event only, where pretalx supports this.
- Run the MCP server only as a child process of the MCP client.
- Keep API tokens in environment variables or a local secret manager.
- Never commit `.env`.
- Never print the API token.
- Never include full private payloads in logs.
- Avoid returning huge raw JSON blobs by default.

---

## Non-goals for v1

Do **not** implement these in the first version:

- Creating submissions
- Updating submissions
- Accepting or rejecting talks
- Publishing schedules
- Sending emails to speakers
- Mutating organiser or reviewer data
- Running as a hosted service
- Providing a remote MCP endpoint
- Providing an HTTP API
- Providing a web UI
- Multi-user authentication
- OAuth flows
- Cloud deployment

The v1 server should be safe to run locally with limited API permissions.

---

## Recommended stack

Use Python because it keeps the project small and easy to run locally.

Recommended libraries:

- `fastmcp` — MCP server framework
- `httpx` — HTTP client
- `pydantic` — config and response validation
- `pydantic-settings` — environment-based settings
- `python-dotenv` — local `.env` support
- `pytest` — tests
- `respx` — mock HTTP API tests
- `ruff` — linting and formatting
- `mypy` — optional type checking
- `uv` — package management

---

## Target repository structure

```text
pretalx-mcp/
├── README.md
├── PLAN.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/
│   └── pretalx_mcp/
│       ├── __init__.py
│       ├── server.py
│       ├── config.py
│       ├── pretalx_client.py
│       ├── safety.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── events.py
│       │   ├── submissions.py
│       │   ├── speakers.py
│       │   ├── schedule.py
│       │   └── reviews.py
│       └── models/
│           ├── __init__.py
│           ├── common.py        # compact_* helpers, truncate_text — implement BEFORE tool phases
│           ├── event.py         # typed dicts / pydantic models for event API responses
│           ├── submission.py    # typed dicts / pydantic models for submission API responses
│           ├── speaker.py       # typed dicts / pydantic models for speaker API responses
│           └── schedule.py      # typed dicts / pydantic models for schedule API responses
├── tests/
│   ├── test_config.py
│   ├── test_pretalx_client.py
│   ├── test_events_tools.py
│   ├── test_submissions_tools.py
│   ├── test_speakers_tools.py
│   ├── test_reviews_tools.py
│   ├── test_models_common.py
│   └── test_schedule_tools.py
└── docs/
    ├── SECURITY.md
    └── MCP_CLIENT_SETUP.md
```

> **Phase ordering note:** `models/common.py` (Phase 10) contains output-shaping helpers required by every tool phase (Phases 5–9). Implement `models/common.py` as stubs **before** starting Phase 5. The phase numbers in this plan reflect logical grouping, not strict implementation sequence.

---

## Environment variables

Create a `.env.example` file:

```bash
PRETALX_BASE_URL=https://pretalx.com
PRETALX_API_TOKEN=replace-me
PRETALX_DEFAULT_EVENT=
PRETALX_TIMEOUT_SECONDS=20
PRETALX_VERIFY_TLS=true
PRETALX_READ_ONLY=true
PRETALX_TRANSPORT=stdio
```

Rules:

- `PRETALX_BASE_URL` must not include a trailing slash.
- `PRETALX_API_TOKEN` must never be committed.
- `PRETALX_READ_ONLY=true` must be the default.
- `PRETALX_TRANSPORT=stdio` must be the only supported transport in v1.
- For local or self-hosted pretalx, allow a custom base URL.
- TLS verification must default to enabled.
- Do not support binding to a TCP port in v1.

---

## Phase 1 — Project bootstrap

### Tasks

1. Create the Python package structure.
2. Add `pyproject.toml`.
3. Configure `uv`.
4. Add linting and formatting with `ruff`.
5. Add basic test scaffolding with `pytest`.
6. Add `.env.example`.
7. Add `.gitignore`.
8. Add `PLAN.md`.
9. Ensure no server socket, HTTP listener, SSE server, or WebSocket server is created.

### Suggested `pyproject.toml`

```toml
[project]
name = "pretalx-mcp"
version = "0.1.0"
description = "Local-only MCP server for pretalx"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastmcp",
    "httpx",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "respx",
    "ruff",
    "mypy",
]

[project.scripts]
pretalx-mcp = "pretalx_mcp.server:main"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

> **Note:** `pytest-asyncio` is required because all tool functions and `PretalxClient` methods are async. Without it, async test functions are silently skipped or error. `asyncio_mode = "auto"` removes the need for `@pytest.mark.asyncio` on every test.

### Acceptance criteria

- `uv sync` succeeds.
- `uv run pytest` succeeds.
- `uv run ruff check .` succeeds.
- `uv run pretalx-mcp` starts the MCP server over stdio.
- No TCP port is opened.
- No web server is started.

---

## Phase 2 — Configuration module

Create:

```text
src/pretalx_mcp/config.py
```

### Requirements

Implement a settings object using `pydantic-settings`.

Fields:

```python
base_url: str
api_token: str | None
default_event: str | None
timeout_seconds: float
verify_tls: bool
read_only: bool
transport: str
```

### Validation rules

- Strip trailing slash from `base_url`.
- Require `base_url`.
- Permit missing `api_token` only for public endpoints.
- Default timeout to 20 seconds.
- Default `read_only` to true.
- Default `transport` to `stdio`.
- Reject any `transport` value other than `stdio`.

### Acceptance criteria

- Config loads from environment variables.
- Config loads from `.env`.
- Invalid empty base URL raises a clear error.
- Trailing slash is removed from base URL.
- Non-stdio transport fails fast with a clear error.

---

## Phase 3 — pretalx HTTP client

Create:

```text
src/pretalx_mcp/pretalx_client.py
```

### Responsibilities

The client should wrap all pretalx HTTP calls.

Implement:

```python
class PretalxClient:
    def __init__(self, settings: Settings): ...

    async def __aenter__(self) -> "PretalxClient": ...
    async def __aexit__(self, *exc) -> None: ...  # closes AsyncClient cleanly

    async def get(self, path: str, params: dict | None = None) -> dict: ...

    async def get_paginated(
        self,
        path: str,
        params: dict | None = None,
        max_pages: int = 10,
        max_results: int | None = None,  # hard cap on accumulated results
    ) -> list[dict]: ...
```

Use `PretalxClient` as an async context manager in `server.py`, or register an `httpx.AsyncClient` shutdown via a FastMCP lifespan hook. This prevents `ResourceWarning: unclosed client session` on stdio process exit.

### HTTP behaviour

- Use `httpx.AsyncClient`.
- Add `Authorization: Token <token>` header when token is present.
- Set a clear `User-Agent`, for example:

```text
pretalx-mcp/0.1.0
```

- Raise readable MCP-friendly errors for:
  - 401 unauthorised
  - 403 forbidden
  - 404 not found
  - 429 rate-limited
  - 5xx server error
  - connection timeout

### Pagination

pretalx API resources may be paginated. Implement support for common paginated API shapes:

```json
{
  "count": 10,
  "next": "https://...",
  "previous": null,
  "results": []
}
```

If the response is not paginated (e.g., `/api/events/` returns an array directly), handle both shapes.

**`next` URL validation:** Before following a `next` link, validate it stays on the same scheme and host as `PRETALX_BASE_URL`. Reject and stop pagination if the URL host differs, to prevent host-redirect attacks from misconfigured or malicious servers.

**Pagination cap and partial results:** When `max_pages` or `max_results` is reached, stop fetching and include `{"truncated": true, "total_count": <API count>}` metadata so callers can report incomplete results to the user.

**Multilingual fields:** pretalx returns some fields (event names, track names, room names, descriptions) as multilingual objects (`{"en": "...", "de": "..."}` or `{"data": [{"language": "en", "content": "..."}]}`). Implement a `resolve_locale(value, preferred_locale=None)` helper that selects the event default locale, then falls back to English, then to the first available value. Apply this to all fields before compacting output.

### Local-only notes

This HTTP client is for outbound API calls only. It must not start a local HTTP server.

### Acceptance criteria

- Auth header is included when token is configured.
- No auth header is included when token is absent.
- Pagination follows `next`.
- Pagination respects `max_pages` and `max_results`.
- `next` URLs that change host/scheme are rejected.
- Results are marked truncated when capped.
- Multilingual fields are resolved to a single string.
- Errors are converted into clear messages.
- API token is never printed in errors or logs.

---

## Phase 4 — MCP server entrypoint

Create:

```text
src/pretalx_mcp/server.py
```

### Requirements

- Instantiate `FastMCP("pretalx")`.
- Load settings.
- Register tool modules.
- Start server using stdio transport only.
- Do not expose HTTP, SSE, WebSocket, or remote transport.

### Example shape

```python
from fastmcp import FastMCP

from pretalx_mcp.config import get_settings
from pretalx_mcp.pretalx_client import PretalxClient
from pretalx_mcp.tools.events import register_event_tools
from pretalx_mcp.tools.submissions import register_submission_tools
from pretalx_mcp.tools.schedule import register_schedule_tools
from pretalx_mcp.tools.speakers import register_speaker_tools

def create_server(settings, client) -> FastMCP:
    """Factory function — returns a fresh FastMCP instance for testability."""
    mcp = FastMCP("pretalx")
    register_event_tools(mcp, client, settings)
    register_submission_tools(mcp, client, settings)
    register_speaker_tools(mcp, client, settings)
    register_schedule_tools(mcp, client, settings)
    return mcp

def main() -> None:
    settings = get_settings()
    # Transport validation is enforced in config.py (pydantic).
    # No redundant check here — settings.transport is always "stdio" if we reach this point.

    client = PretalxClient(settings)
    mcp = create_server(settings, client)

    # Local-only stdio transport.
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

> **Do not declare `mcp` at module level.** A module-level `FastMCP` instance causes tool registrations to accumulate across test runs (no isolation). Use the `create_server` factory so tests can instantiate a fresh server each time.

> **Transport validation:** Phase 2 (`config.py`) already rejects non-`stdio` values via pydantic at startup. Do **not** add a redundant `if settings.transport != "stdio"` guard in `server.py` — it can never be reached and misleads readers about where validation occurs.

### Acceptance criteria

- MCP server starts cleanly.
- Tools are visible to a local MCP client.
- Missing required config produces a useful error.
- Server runs via stdio only.
- Server does not bind to any TCP interface.

---

## Phase 5 — Event tools

Create:

```text
src/pretalx_mcp/tools/events.py
```

### Tool: `pretalx_list_events`

Purpose:

List events visible to the configured API token.

Input:

```python
limit: int = 50
```

Output:

Return a compact list containing:

- event slug
- event name
- date range, where available
- timezone, where available
- public URL, where available

### Tool: `pretalx_get_event`

Purpose:

Fetch details for a single event.

Input:

```python
event: str | None = None
```

If `event` is omitted, use `PRETALX_DEFAULT_EVENT`.

Output:

Return event metadata.

### Acceptance criteria

- Works with explicit event slug.
- Works with default event slug.
- Fails cleanly when no event is supplied and no default is configured.
- Output is compact and avoids unnecessary raw payloads.

---

## Phase 6 — Submission tools

Create:

```text
src/pretalx_mcp/tools/submissions.py
```

### Tool: `pretalx_list_submissions`

Purpose:

List submissions for an event.

Input:

```python
event: str | None = None
state: str | None = None
track: str | None = None
submission_type: str | None = None
limit: int = 100
```

**Limit semantics:** Pass `limit` as the API's `limit` query param (page size). Collect up to `max_pages=10` pages. Return at most `limit` total results. If there are more results than `limit` after pagination, truncate and note `truncated: true` in the output.

Output:

Compact list of submissions:

- code
- title
- state
- track
- submission type
- speakers
- duration
- abstract preview

### Tool: `pretalx_get_submission`

Purpose:

Fetch full details for one submission.

Input:

```python
event: str | None
submission_code: str
```

Output:

Full submission details:

- code
- title
- abstract
- description
- notes, only if available to token
- state
- track
- submission type
- tags
- speakers
- duration
- created/modified timestamps
- review information, if included by API permissions

### Tool: `pretalx_search_submissions`

Purpose:

Search submissions for an event.

Input:

```python
event: str | None = None
query: str
state: str | None = None
track: str | None = None
limit: int = 25
```

**Search strategy:** Use the pretalx server-side `?q=<query>` parameter (which searches title, abstract, description) combined with `state`, `track`, and `submission_type` API filters where supported. For fields the API does not filter natively (speaker names, tags), fetch the filtered server-side results and apply local case-insensitive filtering on top. This avoids fetching all submissions when the server-side filter is sufficient.

Always include `total_count` (from the API `count` field) and `returned_count` in the output so the user knows whether results were capped.

Search fields:

- title (server-side via `?q=`)
- abstract (server-side via `?q=`)
- description (server-side via `?q=`)
- speaker names (local filter after server-side fetch)
- track (API filter)
- tags (local filter after server-side fetch)

Output:

Ranked compact list. Include `total_count` and `returned_count` fields.

### Tool: `pretalx_summarise_submissions`

Purpose:

Provide a structured overview of submissions.

Input:

```python
event: str | None = None
group_by: str = "state"
```

Allowed `group_by` values:

- `state`
- `track`
- `submission_type`
- `speaker`
- `tag`

Output:

Counts and grouped summaries.

### Acceptance criteria

- Can list submissions for an event.
- Can retrieve one submission by code.
- Search is case-insensitive.
- Search handles missing fields safely.
- Limits are enforced.
- Tool output avoids dumping huge raw JSON unless requested.

---

## Phase 7 — Speaker tools

Create:

```text
src/pretalx_mcp/tools/speakers.py
```

### Tool: `pretalx_list_speakers`

Purpose:

List speakers for an event.

Input:

```python
event: str | None = None
limit: int = 100
```

Output:

Compact list:

- speaker code / ID
- name
- submissions
- email, only if available to token
- biography preview

### Tool: `pretalx_get_speaker`

Purpose:

Fetch one speaker profile.

Input:

```python
event: str | None = None
speaker: str
```

Output:

Speaker profile and associated submissions.

### Tool: `pretalx_search_speakers`

Purpose:

Search speakers by name, bio, email, or submission title.

Input:

```python
event: str | None = None
query: str
limit: int = 25
```

**Search strategy:** Use the pretalx speaker endpoint's `?q=` param for name/email server-side search where supported. Apply local case-insensitive filtering on biography and submission titles after fetching. Include `total_count` and `returned_count` in the output.

### Acceptance criteria

- Does not expose speaker email unless returned by API.
- Search works across name, biography, and submission titles.
- Missing speaker returns a clear error.

---

## Phase 8 — Schedule tools

Create:

```text
src/pretalx_mcp/tools/schedule.py
```

### Schedule API endpoint strategy

The pretalx schedule API requires a two-step fetch:

1. `GET /api/events/{event}/schedules/` → paginated list of schedule versions (newest first).
2. Take `results[0]` (or the version named `"latest"`) as the current published schedule.
3. `GET /api/events/{event}/schedules/{version}/talks/` (or `/slots/`) → list of scheduled slots.

Use `?expand=room,submission,submission.speakers,submission.track` to avoid N+1 requests. Define which fields to expand at the start of implementation and test against the actual pretalx API response shape.

If no published schedule exists, return a helpful message rather than an error.

### Tool: `pretalx_get_schedule`

Purpose:

Fetch the current schedule for an event.

Input:

```python
event: str | None = None
```

Output:

Schedule summary:

- event
- schedule version, if present
- days
- rooms
- sessions
- start/end times
- speaker names
- track

### Tool: `pretalx_list_schedule_sessions`

Purpose:

Flatten schedule into a list of sessions.

Input:

```python
event: str | None = None
day: str | None = None
room: str | None = None
speaker: str | None = None
track: str | None = None
```

Output:

Compact list:

- title
- speakers
- room
- start
- end
- duration
- track

### Tool: `pretalx_find_schedule_conflicts`

Purpose:

Basic read-only analysis of schedule conflicts.

Input:

```python
event: str | None = None
```

Checks:

- Same speaker scheduled in overlapping sessions
- Same room with overlapping sessions
- Sessions with missing room
- Sessions with missing start/end

Output:

List of possible conflicts.

### Acceptance criteria

- Schedule can be fetched.
- Schedule can be flattened.
- Filters work.
- Conflict detection does not mutate pretalx.
- Empty schedules return helpful output.

---

## Phase 9 — Optional review tools

Create:

```text
src/pretalx_mcp/tools/reviews.py
```

Only implement if the API token can access review data.

### Tool: `pretalx_get_submission_reviews`

Purpose:

Fetch review information for a submission.

Input:

```python
event: str | None = None
submission_code: str
```

Output:

- review count
- scores (note: pretalx review `score` values may be strings or per-category objects; parse defensively and default to `null` when non-numeric)
- average score (only calculated when all scores are numeric; otherwise return `null`)
- comments, only if available
- reviewer names, only if available

### Tool: `pretalx_review_summary`

Purpose:

Summarise review status across submissions.

Input:

```python
event: str | None = None
```

Output:

- submissions with no reviews
- submissions with low review count
- average scores by track
- highest/lowest scoring submissions

### Acceptance criteria

- Tool degrades gracefully if review endpoints are unavailable.
- No reviewer-sensitive data is invented.
- Output clearly states when data is not available to the API token.

---

## Phase 10 — Data shaping and output safety

Create helper functions in:

```text
src/pretalx_mcp/models/common.py
```

> **Implement this as stubs before Phase 5.** Every tool phase depends on these helpers. Start with pass-through stubs (`return raw`) and fill in the real implementations as tools are developed.

### Requirements

MCP tools should return concise, useful data rather than massive API payloads.

Implement helpers:

```python
def compact_event(raw: dict) -> dict: ...
def compact_submission(raw: dict) -> dict: ...
def compact_speaker(raw: dict) -> dict: ...
def compact_schedule_session(raw: dict) -> dict: ...
def truncate_text(value: str | None, max_length: int = 500) -> str | None: ...
def resolve_locale(value: str | dict | None, preferred: str | None = None) -> str | None: ...
```

`resolve_locale` handles multilingual fields that pretalx returns as dicts (`{"en": "...", "de": "..."}`). It selects the preferred locale, falls back to English, then to the first available value, and returns `None` for missing/empty values.

### Rules

- Truncate long abstracts/descriptions by default.
- Preserve full detail only in `get_*` tools.
- Avoid returning private fields unless the API returned them and the tool name implies detail.
- Include raw API fields only behind an explicit `include_raw: bool = False`.

### Model files

The sibling model files (`event.py`, `submission.py`, `speaker.py`, `schedule.py`) contain typed dicts or pydantic `BaseModel` subclasses that represent API response shapes. They are used for type safety in tool functions and to document expected API fields. They do not perform output shaping — that is `common.py`'s responsibility.

### Acceptance criteria

- List tools are readable.
- Detail tools provide enough context.
- Large text fields do not flood the MCP client.

---

## Phase 11 — Read-only guardrail

Create:

```text
src/pretalx_mcp/safety.py
```

### Implement

```python
def require_write_enabled(settings: Settings) -> None:
    if settings.read_only:
        raise RuntimeError("This MCP server is running in read-only mode.")
```

### Rules

- Any future write tool must call `require_write_enabled`.
- `PRETALX_READ_ONLY=true` must be the default.
- README must explain that write mode is intentionally unsupported in v1.

### Acceptance criteria

- Tests prove write actions are blocked by default.
- Future write tools have a clear pattern.
- v1 contains no write tools.

---

## Phase 12 — Local-only guardrail tests

Add tests proving the project remains local-only.

### Required tests

- `PRETALX_TRANSPORT=stdio` is accepted.
- Missing `PRETALX_TRANSPORT` defaults to `stdio`.
- Any other transport value is rejected.
- Server startup calls `mcp.run(transport="stdio")`.
- `create_server()` returns a fresh `FastMCP` instance each call (no shared global state).
- No config fields exist for host, bind address, or port.
- No code path starts an HTTP listener.

### Acceptance criteria

- Tests fail if someone adds `host`, `port`, `sse`, `websocket`, or remote transport support.
- Tests document that stdio is the intended local-only transport.

---

## Phase 13 — General tests

### Unit tests

Add tests for:

- Config loading
- Base URL normalisation
- Auth header generation
- Pagination
- Pagination `next` URL host-change rejection
- Partial results / truncated flag when `max_pages` hit
- Multilingual field resolution (`resolve_locale`)
- API error handling
- Submission search (server-side `?q=` usage)
- Schedule flattening
- Conflict detection
- Speaker search completeness
- Review graceful degradation when endpoint returns 403/404
- `compact_*` helpers return expected fields
- `truncate_text` truncates at boundary
- Read-only guardrail
- Local-only transport guardrail

### Mock API tests

Use `respx` to mock pretalx responses.

Example test cases:

```python
async def test_list_submissions_handles_paginated_results():
    ...

async def test_get_submission_404_returns_clear_error():
    ...

async def test_search_submissions_uses_server_side_q_param():
    ...

async def test_search_submissions_includes_total_count():
    ...

async def test_search_submissions_matches_speaker_name_locally():
    ...

async def test_schedule_conflict_detects_same_speaker_overlap():
    ...

async def test_pagination_next_url_host_change_rejected():
    ...

async def test_reviews_degrade_gracefully_on_403():
    ...

def test_transport_must_be_stdio():
    ...

def test_resolve_locale_falls_back_to_english():
    ...
```

### Acceptance criteria

- At least 80% coverage for project code (use `pytest-cov` with `--cov=src/pretalx_mcp`).
- No tests require real pretalx credentials.
- One optional integration test can run against a real instance if env vars are present.
- No integration test opens a listening port.
- Test files cover all tool modules: events, submissions, speakers, schedule, reviews, models/common.

---

## Phase 14 — MCP client setup docs

Create:

```text
docs/MCP_CLIENT_SETUP.md
```

Include setup examples for local MCP clients.

### Generic local MCP command

```json
{
  "mcpServers": {
    "pretalx": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/pretalx-mcp",
        "run",
        "pretalx-mcp"
      ],
      "env": {
        "PRETALX_BASE_URL": "https://pretalx.com",
        "PRETALX_API_TOKEN": "your-token",
        "PRETALX_DEFAULT_EVENT": "your-event-slug",
        "PRETALX_TRANSPORT": "stdio",
        "PRETALX_READ_ONLY": "true"
      }
    }
  }
}
```

### Document

- How to create a pretalx API token
- How to restrict the token
- How to configure default event
- How to run without a token for public schedule-only use
- How to debug startup errors
- That the server runs locally over stdio
- That no hosted deployment is supported

### Do not include

- Public server examples
- Reverse proxy examples
- Docker port publishing examples
- Cloud deployment examples
- systemd socket activation examples
- Kubernetes examples

---

## Phase 15 — README

The README should include:

```markdown
# pretalx MCP Server

A local-only MCP server for interacting with pretalx conference data.

## Features

- Local stdio MCP server
- List events
- List and search submissions
- Inspect speakers
- Fetch schedules
- Find basic schedule conflicts
- Read-only by default

## Installation

...

## Configuration

...

## Running locally

...

## MCP client configuration

...

## Security notes

...

## Development

...

## Roadmap

...
```

### Security notes to include

- This is a local-only MCP server.
- The only supported transport is stdio.
- Do not commit API tokens.
- Use the least privileged pretalx API token possible.
- Prefer read-only mode.
- Use a separate token per event where possible.
- Do not expose this MCP server on a public network.
- Treat proposal, speaker, and review data as confidential.

---

## Phase 16 — Explicitly deferred future work

These may be considered later, but must not be implemented in v1:

```text
pretalx_create_submission
pretalx_update_submission_state
pretalx_add_submission_tag
pretalx_update_speaker_note
pretalx_create_schedule_slot
pretalx_update_schedule_slot
remote_mcp_transport
sse_transport
websocket_transport
http_api
web_ui
cloud_hosted_mcp
```

### Metadata lookup tools (v2 candidate)

These are read-only helpers that would significantly improve the filter UX in tool inputs. Defer to v2 but keep in mind when designing tool input parameters:

```text
pretalx_list_tracks        — list available tracks (id + name) for an event
pretalx_list_submission_types — list submission types (id + name)
pretalx_list_tags          — list tags used in an event
pretalx_list_rooms         — list rooms (id + name) for an event
```

These would allow users to discover valid filter values before calling list/search tools. Without them, filter params like `track` and `submission_type` should accept both name strings and numeric IDs, with internal resolution logic.

Before implementing write support in a later version:

- Keep local-only by default.
- Add confirmation-friendly tool descriptions.
- Require `PRETALX_READ_ONLY=false`.
- Require a token with explicit write permissions.
- Add dry-run support.
- Add audit logging.
- Add tests for every write action.
- Never silently publish schedules or send speaker emails.

---

## Suggested Copilot implementation order

Ask Copilot to implement in this order:

1. Bootstrap package and tests.
2. Implement config loading with stdio-only transport validation.
3. Implement `PretalxClient` (async context manager, pagination with `max_results`, `next` URL validation, `resolve_locale`).
4. Implement MCP server entrypoint with `create_server` factory and `mcp.run(transport="stdio")`.
5. **Implement `models/common.py` output-shaping stubs first** (`compact_*`, `truncate_text`, `resolve_locale`) — required by all tool phases.
6. Implement event tools.
7. Implement submission tools.
8. Implement speaker tools.
9. Implement schedule tools (two-step schedule fetch with `expand`).
10. Implement review tools.
11. Fill in full `models/common.py` implementations.
12. Implement read-only guardrail.
13. Implement local-only guardrail tests.
14. Add general tests (including `test_speakers_tools.py`, `test_reviews_tools.py`, `test_models_common.py`).
15. Write README and setup docs.
16. Add optional integration test.

---

## Copilot task prompt

Use this as the main prompt for GitHub Copilot Coding Agent:

```text
Implement a Python MCP server named pretalx-mcp.

The server must be local-only. It must use MCP stdio transport only. It must not expose HTTP, SSE, WebSocket, or any remote MCP transport. It must not bind to a host or port.

Use FastMCP, httpx, pydantic-settings, pytest, respx, and uv.

The server talks to the pretalx REST API using outbound HTTPS only. It must be read-only by default.

Implement the repository structure described in PLAN.md.

Required tools:
- pretalx_list_events
- pretalx_get_event
- pretalx_list_submissions
- pretalx_get_submission
- pretalx_search_submissions
- pretalx_summarise_submissions
- pretalx_list_speakers
- pretalx_get_speaker
- pretalx_search_speakers
- pretalx_get_schedule
- pretalx_list_schedule_sessions
- pretalx_find_schedule_conflicts

Configuration must come from environment variables:
- PRETALX_BASE_URL
- PRETALX_API_TOKEN
- PRETALX_DEFAULT_EVENT
- PRETALX_TIMEOUT_SECONDS
- PRETALX_VERIFY_TLS
- PRETALX_READ_ONLY
- PRETALX_TRANSPORT

PRETALX_TRANSPORT must default to stdio. Reject any value other than stdio.

The HTTP client must:
- Use token authentication when PRETALX_API_TOKEN is set
- Support paginated responses; accept a `max_results` cap and return a `truncated` flag when hit
- Validate that `next` pagination URLs stay on the same host as PRETALX_BASE_URL
- Resolve multilingual pretalx fields (dicts like `{"en": "...", "de": "..."}`) to a single string using a `resolve_locale` helper
- Implement `PretalxClient` as an async context manager so the httpx client is closed on exit
- Convert HTTP errors into clear MCP-friendly errors
- Use a clear User-Agent
- Never print or log the API token

The output must be compact for list/search tools and detailed for get tools. Search tools must use server-side `?q=` params where available and include `total_count`/`returned_count` in results.

Use a `create_server(settings, client) -> FastMCP` factory function instead of a module-level `mcp` instance, to keep tests isolated.

Implement `models/common.py` (compact_* helpers, truncate_text, resolve_locale) BEFORE implementing tool phases.

Add unit tests using pytest, pytest-asyncio, and respx. Set asyncio_mode = "auto" in pytest config. Tests must not require a real pretalx instance.

Add tests proving:
- stdio is the only supported transport
- no host/port config exists
- read-only mode is enabled by default
- no write tools are implemented

Add README.md, .env.example, docs/SECURITY.md, and docs/MCP_CLIENT_SETUP.md.

Do not implement write tools in this version.
Do not implement remote MCP transport.
Do not add cloud deployment instructions.
```

---

## Definition of done

The project is complete when:

- `uv sync` works.
- `uv run pytest` passes.
- `uv run ruff check .` passes.
- `uv run pretalx-mcp` starts the MCP server locally over stdio.
- MCP client can see all listed tools.
- At least one tool works against a real pretalx instance using a token.
- Read-only mode is enabled by default.
- Non-stdio transport is rejected.
- No TCP port is opened.
- README explains setup, configuration, local-only operation, and security.
