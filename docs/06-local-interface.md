# 06 — Local Interface (CLI + localhost pages)

Local-first: `super` CLI owns the loop and the locks; a localhost SPA shows chat and settings. No fork, no cloud required.

## Architecture

- `super` CLI: serve, status, report/metrics, memory helpers, agent/capability commands.
- Local HTTP server (default `0.0.0.0:4311` / `127.0.0.1`) serves API + static SPA.
- Optional later: thin VS Code button or Tauri shell — same pages, no rewrite.

## Pages

| Path | Role |
|------|------|
| `/chat` | Streaming chat, tools, thinking, canvas, inline approvals |
| `/settings` | Model, think level, workspace, tools/MCP, agents, capabilities, memory, envelope |
| `/canvas` | Detached artifact viewer |

## API highlights

`/api/chat/stream`, `/api/sessions`, `/api/ledger`, `/api/report` (ledger summary), `/api/metrics`, `/api/agents`, `/api/capabilities`, `/api/memory`, `/api/approvals`, `/api/intelligence`, `/api/spans`, `/api/fs/pick`.
