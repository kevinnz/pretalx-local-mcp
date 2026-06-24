# GitHub Copilot Instructions — pretalx-local-mcp

## Project overview

`pretalx-mcp` is a **local-only MCP server** that lets local MCP clients
(GitHub Copilot, VS Code, Claude Desktop, Cursor, and others) interact with a
pretalx conference-management instance through the official pretalx REST API.

The server runs as a child process of the MCP client and communicates over
**stdio only**. It must never expose a network service.

---

## Tech stack

| Tool | Purpose |
|------|---------|
| Python ≥ 3.11 | Runtime |
| `fastmcp` | MCP server framework |
| `httpx` | Async HTTP client (outbound to pretalx only) |
| `pydantic` | Response models |
| `pydantic-settings` | Environment-based configuration |
| `python-dotenv` | Local `.env` file support |
| `pytest` | Test runner |
| `respx` | Mock HTTP calls in tests |
| `ruff` | Linting and formatting |
| `mypy` | Optional type checking |
| `uv` | Package management and script runner |

---

## Repository structure

```text
pretalx-mcp/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/
│   └── pretalx_mcp/
│       ├── __init__.py
│       ├── server.py          # FastMCP entrypoint — stdio only
│       ├── config.py          # pydantic-settings Settings class
│       ├── pretalx_client.py  # Outbound httpx client
│       ├── safety.py          # Read-only guardrail
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── events.py
│       │   ├── submissions.py
│       │   ├── speakers.py
│       │   ├── schedule.py
│       │   └── reviews.py
│       └── models/
│           ├── __init__.py
│           ├── common.py      # compact_* helpers, truncate_text
│           ├── event.py
│           ├── submission.py
│           ├── speaker.py
│           └── schedule.py
├── tests/
│   ├── test_config.py
│   ├── test_pretalx_client.py
│   ├── test_events_tools.py
│   ├── test_submissions_tools.py
│   └── test_schedule_tools.py
└── docs/
    ├── SECURITY.md
    └── MCP_CLIENT_SETUP.md
```

---

## Hard constraints — enforce every time

These rules are non-negotiable and must be respected in every file you create
or modify.

### Transport

- **stdio is the only supported transport.** Use `mcp.run(transport="stdio")`.
- Reject any `PRETALX_TRANSPORT` value other than `"stdio"` with a clear error.
- Never bind to `0.0.0.0`, `127.0.0.1`, or any TCP socket.
- Never start an HTTP server, SSE server, or WebSocket server.
- Never add `host`, `port`, `bind`, `sse`, or `websocket` config fields.

### Read-only

- `PRETALX_READ_ONLY=true` is the default. Never change this default.
- v1 contains **no write tools**. Do not implement any tool that mutates pretalx data.
- Any future write tool must call `require_write_enabled(settings)` from `safety.py`.

### Security

- Never commit `.env` or any file containing a real API token.
- Never print, log, or include `PRETALX_API_TOKEN` in error messages.
- Never include full private payloads in log output.
- Never add cloud deployment instructions (no Docker port publishing, no Kubernetes, no hosted MCP).

### v1 non-goals — do not implement

- `pretalx_create_submission`
- `pretalx_update_submission_state`
- `pretalx_add_submission_tag`
- `pretalx_update_speaker_note`
- `pretalx_create_schedule_slot`
- `pretalx_update_schedule_slot`
- Remote MCP transport, SSE transport, WebSocket transport, HTTP API, web UI

---

## Environment variables

```bash
PRETALX_BASE_URL=https://pretalx.com    # required; no trailing slash
PRETALX_API_TOKEN=                      # never commit a real value
PRETALX_DEFAULT_EVENT=                  # optional event slug fallback
PRETALX_TIMEOUT_SECONDS=20
PRETALX_VERIFY_TLS=true
PRETALX_READ_ONLY=true
PRETALX_TRANSPORT=stdio                 # only valid value
```

---

## MCP tools to implement

### Event tools (`tools/events.py`)
- `pretalx_list_events` — list events visible to the token (compact output)
- `pretalx_get_event` — fetch one event by slug (detailed output)

### Submission tools (`tools/submissions.py`)
- `pretalx_list_submissions` — list submissions for an event
- `pretalx_get_submission` — fetch one submission by code (full detail)
- `pretalx_search_submissions` — local case-insensitive search across title, abstract, description, speaker names, track, tags
- `pretalx_summarise_submissions` — counts grouped by state, track, submission_type, speaker, or tag

### Speaker tools (`tools/speakers.py`)
- `pretalx_list_speakers` — list speakers (compact)
- `pretalx_get_speaker` — fetch one speaker profile (detailed)
- `pretalx_search_speakers` — search by name, bio, email, submission title

### Schedule tools (`tools/schedule.py`)
- `pretalx_get_schedule` — fetch and summarise the current schedule
- `pretalx_list_schedule_sessions` — flatten schedule with optional filters (day, room, speaker, track)
- `pretalx_find_schedule_conflicts` — detect overlapping speakers, overlapping rooms, missing room/time data

### Optional review tools (`tools/reviews.py`)
- `pretalx_get_submission_reviews` — reviews for one submission (degrade gracefully if unavailable)
- `pretalx_review_summary` — review status overview across the event

---

## Output shaping rules

- List and search tools return **compact** output (use `compact_*` helpers from `models/common.py`).
- `get_*` tools return **full detail**.
- Truncate abstracts and descriptions to 500 characters by default (use `truncate_text`).
- Never return raw API JSON unless the tool has `include_raw: bool = False`.

---

## HTTP client (`pretalx_client.py`)

- Use `httpx.AsyncClient`.
- Add `Authorization: Token <token>` header when token is present.
- Set `User-Agent: pretalx-mcp/0.1.0`.
- Support paginated responses: follow `next` up to `max_pages=10`.
- Convert HTTP errors into clear MCP-friendly messages:
  - 401 → unauthorised
  - 403 → forbidden
  - 404 → not found
  - 429 → rate-limited
  - 5xx → server error
  - timeout → connection timeout

---

## Testing requirements

- Use `pytest` and `respx` for all tests.
- No test may require real pretalx credentials or make real HTTP requests.
- Tests must explicitly verify:
  - `stdio` is the only accepted transport value.
  - `PRETALX_READ_ONLY` defaults to `true`.
  - No `host`, `port`, or bind address config fields exist.
  - No write tools are implemented.
- Aim for ≥80% coverage of project code.
- One optional integration test (skipped unless real env vars are set) is allowed.

---

## Implementation order

When asked to implement the project, follow this order:

1. Bootstrap package and tests (pyproject.toml, package structure, ruff, pytest).
2. Config loading with stdio-only transport validation (`config.py`).
3. `PretalxClient` with auth, pagination, and error handling.
4. MCP server entrypoint with `mcp.run(transport="stdio")`.
5. Event tools.
6. Submission tools.
7. Speaker tools.
8. Schedule tools.
9. Output shaping helpers (`models/common.py`).
10. Read-only guardrail (`safety.py`).
11. Local-only guardrail tests.
12. General unit and mock-API tests.
13. README and setup docs (`docs/MCP_CLIENT_SETUP.md`, `docs/SECURITY.md`).
14. Optional integration test.

---

## Definition of done

- `uv sync` succeeds.
- `uv run pytest` passes with ≥80% coverage.
- `uv run ruff check .` passes with no errors.
- `uv run pretalx-mcp` starts the MCP server over stdio (no TCP port opened).
- All listed tools are visible to a local MCP client.
- At least one tool works against a real pretalx instance using a token.
- `PRETALX_READ_ONLY=true` is the default.
- Non-stdio transport is rejected with a clear error.
- README explains setup, configuration, local-only operation, and security.
