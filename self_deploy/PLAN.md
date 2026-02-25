# Self-Deploy Build Plan (Standalone Champion Council)

## Phase 0 — Baseline + Inventory (Done)

- [x] MCP status checked against `champion-ouroboros-space`
- [x] FelixBag catalog + key document extraction completed
- [x] VS Code wrapper + HF Space wrapper architecture reviewed
- [x] Created `self_deploy/` workspace scaffold

---

## Phase 1 — Local Runtime Skeleton

### Backend
- [x] Create local server entrypoint (`backend/server.py`) based on `Champion_Council/server.py`
- [x] Add capsule lifecycle manager (start/stop/restart/status)
- [x] Add `/api/health`, `/api/tools`, `/api/tool/{name}` endpoints
- [x] Add `/mcp/sse` + `/mcp/messages` reverse proxy for external MCP clients
- [x] Add MCP session lifecycle management with reconnect semantics
- [x] Add postprocessing patch layer (`get_genesis`, `compare`, `debate`, `orchestra`)
- [x] Add workflow normalization middleware in REST + JSON-RPC paths

### Frontend
- [x] Copy current Space panel into `frontend/` baseline
- [x] Wire frontend -> backend API base path (via `vscode-shim.js`)
- [ ] Verify core tabs: Overview, Council, Memory, Activity, Tools

Acceptance:
- [ ] Local app boots with one command and can call `get_status`, `list_slots`, `bag_catalog`

---

## Phase 2 — Secrets & Provider Integration Layer

- [x] Create `config/.env.example` + schema validator scaffold
- [ ] Implement runtime secrets resolver (priority: env > local secrets file > UI-set session)
- [ ] Add provider checks for:
  - Hugging Face (`HF_TOKEN`)
  - Vast (`VAST_API_KEY`)
  - Brave (`BRAVE_API_KEY`)
  - Serper (`SERPER_API_KEY`)
  - Google (`GOOGLE_API_KEY`)
  - OpenAI/Anthropic (optional)
  - Pinata/Web3Storage (optional)
- [ ] Add `/api/integrations/status` endpoint (redacted)
- [ ] Add UI panel for integration health (never display raw secrets)

Acceptance:
- [ ] One-click diagnostics show which integrations are configured and usable

---

## Phase 3 — Feature Parity Hardening

- [x] Bring over Dreamer tab aggregation routes (`/api/dreamer/*`)
- [x] Bring over Vast fleet aggregation route (`/api/vast/state`)
- [x] Keep activity SSE stream as single source of truth
- [x] Add workflow normalization middleware (`tool`/`tool_name` compatibility)
- [x] Add proxy-level compatibility patches currently used by Space
- [ ] Add cascade/relay/signal APIs for diagnostics parity
- [ ] Add evaluation harness parity with extension flow

Acceptance:
- [ ] Dreamer and GPU Fleet tabs update live locally without manual refresh loops

---

## Phase 4 — Standalone Packaging

- [x] Add local run scripts (`scripts/run.ps1`, `scripts/run.sh`)
- [x] Add optional Docker compose paths (`docker-compose.yml`, `docker-compose.split.yml`, `docker-compose.remote.yml`)
- [x] Add persistent state folder strategy (`data/`) for bag/workflows/slots/brain
- [ ] Add backup/export command set
- [x] Split requirements into server/capsule/full variants

Acceptance:
- [ ] New machine setup in <10 minutes with docs only

---

## Phase 5 — Wrapper Unification

- [ ] Define shared asset strategy (`frontend` reused by Space + extension)
- [ ] Define shared API contract package for both wrappers
- [ ] Add regression checklist for both wrappers before release

Acceptance:
- [ ] New feature can be added once and consumed by both wrappers with minimal divergence
