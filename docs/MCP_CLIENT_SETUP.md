# MCP client setup (local-only)

This project is configured for local MCP clients only. The server must run as a
local stdio process and should not be exposed over the network.

```text
Local MCP client -> local stdio MCP process -> outbound HTTPS -> pretalx API
```

## 1) Prepare the project

```bash
git clone <your-fork-or-repo-url> /path/to/pretalx-mcp
cd /path/to/pretalx-mcp
cp .env.example .env
uv sync
```

Set these values in `.env` (or in your client secret configuration):

- `PRETALX_BASE_URL`
- `PRETALX_API_TOKEN`
- `PRETALX_DEFAULT_EVENT`
- `PRETALX_TIMEOUT_SECONDS`
- `PRETALX_VERIFY_TLS`
- `PRETALX_READ_ONLY` (keep `true`)
- `PRETALX_TRANSPORT` (must be `stdio`)

## 2) Generic MCP config JSON

Use a local command-based MCP server entry. Example:

```json
{
  "mcpServers": {
    "pretalx": {
      "command": "uv",
      "args": ["--directory", "/path/to/pretalx-mcp", "run", "pretalx-mcp"],
      "env": {
        "PRETALX_BASE_URL": "https://pretalx.example.com",
        "PRETALX_API_TOKEN": "replace-with-local-token",
        "PRETALX_DEFAULT_EVENT": "",
        "PRETALX_TIMEOUT_SECONDS": "20",
        "PRETALX_VERIFY_TLS": "true",
        "PRETALX_READ_ONLY": "true",
        "PRETALX_TRANSPORT": "stdio"
      }
    }
  }
}
```

Use your MCP client's secret handling for tokens when available.

## 3) Validate local operation

- Start/reload your MCP client.
- Confirm the `pretalx` server starts successfully.
- Confirm tools are listed.
- Confirm no network listener is created by this process.

## Important constraints

- Supported transport: `stdio` only.
- Unsupported: HTTP/SSE/WebSocket/remote transport.
- This guide intentionally excludes cloud/hosted deployment examples.
