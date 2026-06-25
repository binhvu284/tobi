# TOBI "MCP Hub" — Model Context Protocol Server + Client

> **Queue status:** 🟡 Queued · **Depends on:** Genesis vault ([GENESIS_SPEC.md](GENESIS_SPEC.md)) for credential storage · **Owner-reviewed:** 30 Q&A + research below
> Part of the [Feature Development Queue](QUEUE.md). Makes TOBI both an **MCP server** (other agents connect in) and an **MCP client** (TOBI connects out to other servers/agents) — interoperable across platforms, configured entirely in Mission Control.

## Context

The owner wants TOBI to interoperate with the wider agent ecosystem: external agents should connect to **TOBI's MCP server** to talk to/command TOBI, and TOBI should connect out as an **MCP client** to use other platforms' tools and converse with other AI agents. All configuration must be **easy and convenient in MC**. TOBI has **no MCP today** (only Evolution-tier text mentions "Gmail MCP"). TOBI is a Python/FastAPI backend, so it can host an MCP server (FastMCP mounted in the existing app) and run a client connection manager, with MC managing both and credentials living in the Genesis vault.

## Research summary (MCP state, mid-2026)

- Latest spec = **2026-07-28 RC** — the largest revision since launch: a **stateless HTTP core**, **Streamable HTTP** transport (replaced legacy SSE) for **remote** servers, **OAuth 2.1 / OIDC**-aligned auth, plus **MCP Apps** (server-rendered UIs) and a **Tasks** extension (long-running work). Official SDKs for **Python (+FastMCP)**, TS, C#, Java, Swift; 500+ public servers.
- **A2A** (Agent2Agent) is the complementary *agent-to-agent* protocol (agent cards + messaging) — used here for richer agent collaboration alongside MCP.
- Sources: [MCP blog/roadmap](https://blog.modelcontextprotocol.io/) · [MCP 2026 guide](https://dev.to/x4nent/complete-guide-to-mcp-model-context-protocol-in-2026-architecture-implementation-and-4a11). *(Web-search quota was hit mid-research; deepen A2A/OAuth specifics at build time.)*

## Decisions (from Q&A)

| Area | Decision |
|---|---|
| Direction | **Both** — TOBI as MCP **server** AND **client** |
| Purpose | **Tool interoperability** (share/use tools across platforms) |
| Transport (primary) | **Streamable HTTP** (remote) |
| Protocol | **MCP + A2A** |
| Server exposes (tools) | **All**: chat/ask TOBI, run engines & missions, query Brain/memory, status/reports/data |
| Server exposes (more) | **Resources + prompts** too (Brain memories/docs/reports + prompt templates) |
| Server hosting | **Mounted in the existing FastAPI app** (FastMCP at `/mcp`) |
| Reachability | **Internet-exposed** via secure tunnel/VPS |
| Inbound auth | **Both OAuth 2.1 + issued API tokens** |
| Access control | **Per-client scopes** (allowed tools/resources per client) |
| Sensitive actions | **Human-in-the-loop approval** (MC/Telegram notify) |
| Inbound guardrails | **Audit log + rate limiting** per client |
| Add external servers | **Manual config + curated catalog** |
| Client transports | **All**: Streamable HTTP, stdio, legacy SSE, **A2A endpoints** |
| External tool routing | **Global to all TOBI agents** |
| External call approval | **Per-tool permission model** (allow/ask/deny) |
| Credential storage | **Reuse the Genesis encrypted vault** |
| Tool discovery | **Auto-list on connect + per-tool enable/disable + refresh** |
| Add-server test | **Test (handshake + list) and block on failure** |
| Connection health | **Live status + auto-reconnect + failure alerts** |
| Placement | **Dedicated 'MCP' page** in nav |
| Layout | **Two tabs: Server + Clients** |
| Connection cards | Status/transport/auth · tools+toggles · recent call logs · scopes + kill-switch |
| Tool browser | **Browser + 'try it' tester** (exposed + connected tools) |
| Observability | **Full inspector** (request/response, latency, errors, filterable) |
| Connected agents | **Live sessions view** (who's connected, scopes, active sessions) |
| Notifications | **Connections + approval requests + failures** |
| A2A discovery | **Agent cards** (publish TOBI's card + discover peers') |
| Scope | **Everything in v1** (phased internally) |
| North star | **Interoperability reach** |

## Architecture & key choices

- **Server = FastMCP mounted in the existing FastAPI app** at `/mcp` over **Streamable HTTP**. TOBI capabilities become MCP **tools** (wrapping existing functions: chat→`model_router`+Brain; run engines/missions→existing `runEngine`/mission APIs; query Brain→Brain retrieval; status/reports→`get_dashboard` et al.), with Brain memories/reports as **resources** and reusable **prompts**. Exposure to the internet via a **secure tunnel** (e.g. cloudflared) or the VPS.
- **Client = a connection manager** (`core/mcp_client.py`) maintaining sessions to configured servers across **all transports** (Streamable HTTP, stdio, legacy SSE, A2A), auto-discovering tools and surfacing them **globally** into TOBI's tool-use loop, gated by a **per-tool permission model** (allow/ask/deny). Auto-reconnect + live health.
- **Security is layered** (this opens TOBI to outside agents): **OAuth 2.1 + issued tokens** for inbound, **per-client scopes**, **human-in-the-loop approval** for sensitive tools (reuse the existing proposal/approval + Telegram notify pattern), **rate limiting**, and a **full audit log**. All MCP/A2A credentials live in the **Genesis vault** (`get_secret`) — never inline.
- **A2A** (`core/a2a.py`): publish TOBI's **agent card** (skills/endpoints) and discover/添加 peer cards for agent-to-agent messaging.
- **Untrusted-input posture:** treat tools/outputs from external servers as untrusted (prompt-injection risk) — per-tool permissions + approvals + the owner stays in the loop for anything sensitive.

## Data model — new tables (`core/database.py`, idempotent `_ensure_mcp_schema(conn)`)

- **`mcp_server_config`** — `enabled, transport, public_url, tunnel_status, auth_modes_json (oauth|token), rate_limit_json, updated_at`.
- **`mcp_clients`** — inbound: `id, name, auth_type, token_ref (→vault), scopes_json, status, created_at, last_seen`.
- **`mcp_connections`** — outbound: `id, name, transport ('http'|'stdio'|'sse'|'a2a'), endpoint/command, auth_ref (→vault), enabled, status, last_tested_at, tools_count`.
- **`mcp_tools`** — `id, source ('self'|connection_id), name, schema_json, enabled, permission ('allow'|'ask'|'deny'), scopes_json`.
- **`mcp_call_log`** — `id, ts, direction ('in'|'out'), peer, tool, status, latency_ms, request_json, response_json, error`.
- **`mcp_approvals`** — `id, client, tool, args_json, status ('pending'|'approved'|'rejected'), created_at`.
- **`a2a_agents`** — `id, name, card_json, endpoint, status` (+ TOBI's own card config).
- Reuse Genesis **`vault_secrets`** for all tokens/OAuth creds.

## Backend work (`tobi/`)

1. **Deps** — `mcp` (official Python SDK) / `fastmcp`, an A2A SDK, an OAuth 2.1 provider lib, and a tunnel (cloudflared) for exposure.
2. **`core/mcp_server.py`** — FastMCP server: tool/resource/prompt definitions wrapping TOBI capabilities; scope enforcement; sensitive-action approval gating; emits to the audit log + live-sessions registry.
3. **`core/mcp_client.py`** — multi-transport connection manager: connect/test/discover/refresh, session pool, auto-reconnect, invoke-with-permission, health.
4. **`core/a2a.py`** — agent-card publish + peer discovery + A2A messaging.
5. **`core/mcp_security.py`** — OAuth 2.1 + token verification, per-client scope checks, rate limiting, audit writer.
6. **Mount + control API** in `api/dashboard.py`/app: the MCP server at **`/mcp`** (Streamable HTTP), plus REST `/api/mcp/*` for config/management. Reuse vault `get_secret` for creds.
7. **Tool-loop integration** — surface enabled external tools into the model-router/agent tool set (global), respecting per-tool permission.

### API endpoints (`/api/mcp/*`, gated by `X-API-Key` + vault session)
- Server: `GET/PUT /server/config`, `POST /server/enable|disable`, `GET /server/tunnel`.
- Clients (inbound): `GET /clients`, `POST /clients` (issue token/OAuth client), `PATCH /clients/{id}` (scopes), `DELETE /clients/{id}`; `GET /clients/sessions` (live), SSE `/clients/sessions/stream`.
- Connections (outbound): `GET /connections`, `POST /connections` (add+test, block on fail), `POST /connections/{id}/test`, `POST /connections/{id}/refresh`, `PATCH /connections/{id}` (enable), `DELETE /connections/{id}`.
- Tools: `GET /tools` (exposed + connected), `PATCH /tools/{id}` (enable/permission), `POST /tools/{id}/invoke` ('try it').
- Approvals: `GET /approvals`, `POST /approvals/{id}/(approve|reject)`.
- Logs: `GET /logs` (filterable), SSE `/logs/stream`.
- A2A: `GET/PUT /a2a/card`, `GET /a2a/peers`, `POST /a2a/peers`.

## Frontend work (`tobi/dashboard/src/`)

1. **Routing/nav** — register `/mcp` in `App.tsx`; nav item in `AppShell.tsx` (`Share2`/`Workflow` icon); `PageLoader` preset `mcp`.
2. **`api.ts`** — types (`McpServerConfig`, `McpClient`, `McpConnection`, `McpTool`, `CallLogEntry`, `Approval`, `A2aPeer`) + functions for every endpoint.
3. **`pages/Mcp.tsx`** — **two tabs**: **Server** (expose config, internet/tunnel status, OAuth/token issuance, per-client scopes, **live connected-sessions** view, exposed-tools toggles) and **Clients** (connection cards + add-server flow with catalog). Shared: **tool browser + 'try it'**, **call inspector**, **approval queue**, **A2A peers/card**.
4. **Components** — `McpServerPanel`, `McpConnectionCard` (status/transport/auth, tools+toggles, recent logs, scopes + kill-switch), `AddConnectionModal` (manual + catalog + import), `ToolBrowser` + `TryItModal`, `CallInspector` (live, filterable), `ApprovalQueue`, `LiveSessions`, `A2aPeers`. Reuse the Genesis **vault unlock** for entering credentials, `useToast`, `ConfirmTransitionModal`.
5. **Notifications** — connections/approvals/failures via the existing toast/notification system (+ Telegram for approvals).

## v1 build phases (everything ships in v1, sequenced)

- **M1 — MCP server:** FastMCP mounted at `/mcp`, expose tools + resources + prompts, **token auth**, scopes, audit log, approval gating for sensitive tools.
- **M2 — MCP client:** connection manager (all transports), discovery + per-tool permissions, vault-backed creds, test-on-add, health + auto-reconnect.
- **M3 — MC UI:** MCP page (Server/Clients tabs), connection cards, tool browser + try-it, call inspector, approvals, live sessions.
- **M4 — Reach + interop:** **OAuth 2.1**, **internet exposure** (tunnel/VPS), **A2A** (agent cards + peers), rate limiting, notifications, polish.

## Verification (end-to-end)

1. **Server up:** `python main.py api`; `/mcp` serves Streamable HTTP; an external MCP client (e.g. Claude/Inspector) connects with a token and lists TOBI's tools/resources.
2. **Inbound action + approval:** external client calls "run mission" → it **pauses for approval** (MC/Telegram) → approve → executes; call appears in the **inspector** and **audit log**; rate limit enforced; out-of-scope tool is denied.
3. **Outbound client:** add an external server (catalog + manual) → **test passes**, tools auto-list; disable one tool; an 'ask' tool prompts before TOBI calls it; kill-switch disables the whole connection; creds stored in the **vault**.
4. **Health:** drop a connection → live status flips + auto-reconnect + alert.
5. **A2A:** TOBI publishes its **agent card**; add a peer; exchange a message.
6. **Live sessions:** connected agents appear in real time with scopes.
7. `cd tobi/dashboard && npm run build` clean; backend imports without error.

## Risks / watch-items

- **Internet exposure = attack surface** — mitigate with OAuth 2.1, per-client scopes, approvals, rate limiting, audit, and a kill-switch; default sensitive tools to approval.
- **Prompt injection from external servers** — treat external tools/outputs as untrusted; per-tool permissions + owner-in-the-loop for sensitive follow-on actions.
- **Depends on Genesis vault** — credentials should live there; sequence Genesis first (or stub a minimal secure store).
- **Spec churn** — target the current Streamable HTTP + OAuth spec; isolate transport/auth so spec updates are contained; A2A is younger — keep it behind a clean module.
- **Tunnel/exposure security** — lock down the tunnel, rotate tokens, scope public surface to intended tools only.
- **Reuse, don't duplicate** — wrap existing engines/missions/Brain/status functions as MCP tools rather than reimplementing; reuse the approval/notification patterns already in the codebase.
