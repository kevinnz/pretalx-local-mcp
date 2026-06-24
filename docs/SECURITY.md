# Security posture

`pretalx-mcp` is intentionally local-only.

```text
Local MCP client -> local stdio MCP process -> outbound HTTPS -> pretalx API
```

Only local stdio communication and outbound HTTPS to pretalx are in scope.

## Token handling

- Store `PRETALX_API_TOKEN` in local environment variables or a local secret
  manager.
- Never commit `.env` or token-bearing files.
- Never print or log API tokens.
- Rotate tokens if exposure is suspected.

## Least privilege

- Use read-only tokens wherever possible.
- Scope tokens to only the event(s) required for your workflow.
- Keep `PRETALX_READ_ONLY=true` unless a future version explicitly supports
  writes with additional guardrails.

## Local execution and transport

- `PRETALX_TRANSPORT=stdio` is the only supported transport.
- Do not expose HTTP, SSE, WebSocket, or any remote MCP transport.
- Do not bind to TCP addresses or publish ports.
- Run the MCP server as a local child process of your MCP client.

## Sensitive data handling

pretalx data may include unpublished submissions, speaker contact information,
private notes, and review data.

- Avoid sharing raw private payloads unnecessarily.
- Minimize logs and diagnostic output containing sensitive content.
- Restrict machine/user access where local config and logs are stored.

## Hosted deployment non-goals (v1)

The following are explicit non-goals for this project version:

- Hosted/cloud MCP deployment
- Public or private remote MCP endpoints
- Docker/Kubernetes deployment guidance with exposed ports
- HTTP API, web UI, SSE, or WebSocket server modes
