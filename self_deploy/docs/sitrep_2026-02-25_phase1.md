# SITREP — Self-Deploy Standalone · 2026-02-25 05:58 ET

## Status: Phase 1 COMPLETE · Phase 2–5 OPEN · Docker READY

---

## What Exists Now (48 files)

### Backend (`backend/`) — 11 files, fully functional

| File | Lines | Purpose |
|------|-------|---------|
| `server.py` | 504 | FastAPI main — all routes, lifespan, static mounts |
| `settings.py` | 93 | Frozen dataclass config + minimal .env loader |
| `capsule_manager.py` | 139 | Subprocess lifecycle, gz decompression, Windows `CREATE_NEW_PROCESS_GROUP` |
| `mcp_client.py` | 142 | MCP SDK session with exponential backoff reconnect (`min(2^n, 30)s`) |
| `postprocessing.py` | 122 | 4 capsule bug patches: `get_genesis`, `compare`, `debate`, `orchestra` |
| `activity.py` | 127 | SSE hub, subscriber management, `SILENT_TOOLS` noise filter |
| `mcp_proxy.py` | 86 | `PendingCallRegistry` + JSON-RPC tool/workflow parsers |
| `persistence.py` | 430 | Dual-mode `local\|hf\|both`, autosave loop, HF Dataset sync |
| `dreamer_routes.py` | 182 | Dreamer state aggregation, config CRUD, training history tracking |
| `vast_routes.py` | 59 | Vast fleet state aggregation with cache |
| `__init__.py` | 2 | Package marker |

### API Surface

```
GET  /                       → Landing page
GET  /panel                  → Full control panel
GET  /api/health             → Status + capsule + MCP + persistence + reconnect state
GET  /api/tools              → List all capsule tools via MCP
POST /api/tool/{name}        → Proxy tool call (with postprocessing + workflow normalization)
GET  /api/capsule-log        → Tail capsule stdout
POST /api/capsule/restart    → Restart local capsule (guarded: local mode only)
POST /api/persist/save       → Manual state save
POST /api/persist/restore    → Manual state restore
GET  /api/persist/status     → Persistence config/status
GET  /api/activity-stream    → SSE live activity feed
GET  /api/activity-log       → Recent activity entries
GET  /api/dreamer/state      → Dreamer aggregation
GET  /api/dreamer/config     → Dreamer config (from bag or defaults)
POST /api/dreamer/config     → Save dreamer config to bag
POST /api/dreamer/config/reset → Reset to defaults
GET  /api/vast/state         → Vast fleet aggregation
GET  /mcp/sse                → MCP SSE reverse proxy (for IDE agents)
POST /mcp/message(s)         → MCP JSON-RPC reverse proxy
```

### Frontend (`frontend/`) — 7 files

Copied from Space baseline. `vscode-shim.js` (701 lines) bridges VS Code messaging API to HTTP.

| File | Size | Notes |
|------|------|-------|
| `panel.html` | 120 KB | Full control panel |
| `main.js` | 354 KB | UI logic (Space variant — 160 lines diverged from `media/main.js`) |
| `vscode-shim.js` | 33 KB | Browser bridge — 72 command types |
| `index.html` | 10 KB | Landing → panel redirect |
| `peerjs.min.js` | 93 KB | Vendor |
| `svg-pan-zoom.min.js` | 30 KB | Vendor |
| `logo.png` | 132 B | Placeholder |

### Docker — 7 files, all 3 architectures

| File | Architecture | Image Size |
|------|-------------|------------|
| `Dockerfile` | Single container (proxy + capsule) | ~4 GB |
| `Dockerfile.proxy` | Proxy only | ~200 MB |
| `Dockerfile.capsule` | Capsule only | ~4 GB |
| `docker-compose.yml` | Option A: single container | Default |
| `docker-compose.split.yml` | Option B: proxy + capsule containers | Split |
| `docker-compose.remote.yml` | Option C: proxy + remote capsule | Lightweight |
| `.dockerignore` | Build exclusions | — |

`Dockerfile` and `Dockerfile.capsule` include `git` for model downloads; `Dockerfile.proxy` intentionally omits git for a smaller image. All three Dockerfiles run as non-root `council` (UID 1000) with proper runtime directory ownership (`chown`).

### Scripts / Config / Requirements

- `scripts/setup.ps1` + `run.ps1` (Windows)
- `scripts/setup.sh` + `run.sh` (Unix)
- `config/.env.example` (53 lines — all env vars documented)
- `config/schema.py` (Pydantic stub — **not wired into settings.py yet**)
- `requirements-server.txt` (7 deps, ~200 MB)
- `requirements-capsule.txt` (14 deps, ~3 GB)
- `requirements.txt` (combines both)

### Data Layout (`data/`)

```
data/
├── brain/       # brain_state.pkl
├── bag/         # bag_export.json
├── workflows/   # workflows.json
├── slots/       # slot_manifest.json
└── config/      # state_meta.json
```

---

## What's Verified ✅

- Python compile pass for all backend modules
- Server boots in proxy mode (`MANAGE_LOCAL_CAPSULE=0`)
- `GET /api/health` → 200 (includes reconnect backoff state)
- `GET /api/activity-log` → 200
- `GET /panel` → 200
- `GET /api/tools` → 503 (correct when MCP unavailable)
- `POST /api/capsule/restart` → 400 guard (correct in proxy mode)
- Full startup with local capsule + MCP session connected (`MANAGE_LOCAL_CAPSULE=1`) in ~98s
- Live tool proxy checks (all 200): `get_status`, `list_slots`, `bag_catalog`, `get_genesis`
- `/panel` contains core tab labels: Overview, Council, Memory, Activity, Tools
- `/mcp/sse` stream reachable and endpoint rewrite confirmed (`/mcp/messages?...`)
- MCP SDK client test through proxy succeeded (`initialize` + `list_tools` + `heartbeat`)
- Persistence cycle passes in local mode:
  - `POST /api/persist/save` → `{"status":"saved"}`
  - `POST /api/persist/restore` → `{"status":"restored"}`
  - expected files written under `data/` (`brain`, `bag`, `workflows`, `slots`, `config`)

## What's NOT Verified Yet ❌

- Forced-error path test proving `get_genesis` fallback patch triggers under failure conditions
- Docker `docker compose up --build` full end-to-end runtime validation (blocked in this session: Docker daemon unavailable)

---

## Known Gaps / Remaining Work

### Low-Priority Cleanup (Phase 1 polish)

| Item | Effort | Risk |
|------|--------|------|
| `parse_mcp_result` lives in `activity.py`, imported by `postprocessing.py` — circular dep risk | Move to `utils.py` | Low |
| `config/schema.py` is a stub not wired into `settings.py` | Unify or delete | Low |
| `host.docker.internal` needs `--add-host` on Linux Docker | Add README note | Low |
| Capsule healthcheck in `docker-compose.split.yml` is multiline Python in YAML | Extract to script | Low |

### Phase 2 — Secrets & Provider Integration

- Runtime secrets resolver (env > file > session)
- Provider health checks (HF, Vast, Brave, Serper, Google, OpenAI, Anthropic, Pinata, Nostr)
- `/api/integrations/status` endpoint (redacted secrets)
- UI panel for integration health

### Phase 3 — Feature Parity

- Cascade/relay/signal APIs for diagnostics tab
- Evaluation harness parity with extension flow
- Live Dreamer/Vast tab verification

### Phase 4 — Packaging

- Backup/export command set (`/api/snapshot/*`)
- `< 10 min` new machine setup validation
- Docker image publishing (GHCR)

### Phase 5 — Wrapper Unification

- Shared `champion_core/` package (API contracts, constants, version)
- Canonical `main.js` build pipeline (reconcile 160-line divergence)
- Regression checklist for Space + Extension + Standalone

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────┐
│                 Docker Container                  │
│                                                  │
│  ┌─────────────────┐    ┌──────────────────────┐ │
│  │  FastAPI :7860   │───▸│ champion_gen8.py     │ │
│  │  (server.py)     │    │ MCP/SSE :8765        │ │
│  │                  │    │ (147 tools, Gen 8)   │ │
│  │  Routes:         │    └──────────────────────┘ │
│  │  /api/*          │                             │
│  │  /mcp/sse        │    ┌──────────────────────┐ │
│  │  /panel          │    │ data/                │ │
│  │  /static/*       │    │ brain/ bag/ slots/   │ │
│  └─────────────────┘    │ workflows/ config/   │ │
│                          └──────────────────────┘ │
└──────────────────────────────────────────────────┘
        ▲                          ▲
        │ HTTP/SSE                 │ Volume mount
   ┌────┴────┐              ┌─────┴─────┐
   │ Browser │              │ ./data/   │
   │ IDE MCP │              │ ./capsule │
   └─────────┘              └───────────┘
```

---

## Where Codex Can Help

1. **Docker build test** — run `docker compose up --build` end-to-end once Docker daemon is available
2. **Low-priority cleanup** — `utils.py` extraction, schema unification, compose version removal
3. **Phase 2 kickoff** — provider health check system, `/api/integrations/status`
4. **Frontend reconciliation** — diff the 160 diverged lines between `media/main.js` and `static/main.js`, produce a canonical standalone variant
