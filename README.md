# pretalx-mcp (local-only)

`pretalx-mcp` is a local MCP server for pretalx. It is designed to run as a
child process of a local MCP client and communicates over stdio only.

```text
Local MCP client -> local stdio MCP process -> outbound HTTPS -> pretalx API
```

Only outbound HTTPS requests to pretalx are expected. No inbound network
service is exposed.

## Features

- Local-only architecture (no hosted or remote MCP endpoint).
- `stdio` is the only supported transport.
- Read-only by default (`PRETALX_READ_ONLY=true`).
- Environment-based configuration via `.env`.
- MCP tools for events, submissions, speakers, schedule, and optional reviews.

## Installation

1. Install Python 3.11+ and `uv`.
2. Clone this repository.
3. Sync dependencies:

```bash
uv sync
```

## Configuration

Copy `.env.example` to `.env` and fill in local values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Notes |
|---|---|---|---|
| `PRETALX_BASE_URL` | Yes | none | pretalx base URL, no trailing slash |
| `PRETALX_API_TOKEN` | Yes | empty | use a local token; never commit |
| `PRETALX_DEFAULT_EVENT` | No | empty | optional fallback event slug |
| `PRETALX_TIMEOUT_SECONDS` | No | `20` | HTTP timeout in seconds |
| `PRETALX_VERIFY_TLS` | No | `true` | keep TLS verification enabled |
| `PRETALX_READ_ONLY` | No | `true` | must remain true for v1 |
| `PRETALX_TRANSPORT` | No | `stdio` | only supported value is `stdio` |

## Running locally

Run the server locally with stdio transport:

```bash
uv run pretalx-mcp
```

This process is intended to be launched by an MCP client, not exposed as a web
service.

## MCP client configuration

See [docs/MCP_CLIENT_SETUP.md](docs/MCP_CLIENT_SETUP.md) for a generic MCP
client JSON configuration using:

```bash
uv --directory /path/to/pretalx-mcp run pretalx-mcp
```

## Security notes

- Keep API tokens local and out of git history.
- Prefer least-privilege, read-only pretalx tokens.
- Never log or print tokens.
- Do not run this project as a hosted/cloud MCP service.

See [docs/SECURITY.md](docs/SECURITY.md) for full guidance.

## Development

Common local commands:

```bash
uv sync
uv run ruff check .
uv run pytest
```

Project docs and metadata files:

- `.env.example`
- `.gitignore`
- `docs/SECURITY.md`
- `docs/MCP_CLIENT_SETUP.md`

## Roadmap

- Deliver read-only organiser workflows first.
- Keep transport local (`stdio`) and avoid any remote server mode.
- Add optional review-oriented tools where API permissions allow.
- Consider future write tools only behind explicit safety checks and opt-in
  configuration.
