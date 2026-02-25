# Phase 1 Progress — 2026-02-25

## Implemented

### Backend
- `backend/server.py`
  - `/api/health`
  - `/api/tools`
  - `/api/tool/{tool_name}`
  - `/api/activity-stream`
  - `/api/activity-log`
  - `/api/capsule-log`
  - `/api/capsule/restart`
  - `/api/persist/save|restore|status`
  - `/mcp/sse`, `/mcp/message`, `/mcp/messages`
- `backend/capsule_manager.py`
  - local capsule start/stop/restart
  - gzip fallback (`capsule.gz` -> `champion_gen8.py`)
  - Windows-aware process shutdown behavior
- `backend/mcp_client.py`
  - MCP session lifecycle + reconnect behavior
  - exponential reconnect backoff state (`attempts`, `retry_in_seconds`)
- `backend/postprocessing.py`
  - workflow normalization
  - get_genesis fallback patch
  - compare/debate retry patch
  - orchestra consensus patch
- `backend/persistence.py`
  - dual-mode persistence (`local|hf|both`)
  - local-first layout under `data/`
  - optional HF dataset sync
  - autosave task
- `backend/activity.py`
  - SSE activity hub and log
- `backend/dreamer_routes.py`
  - dreamer state aggregation + config CRUD
- `backend/vast_routes.py`
  - vast fleet aggregation
- `backend/mcp_proxy.py`
  - pending JSON-RPC call registry + workflow normalization for proxy payloads

### Frontend
- copied Space frontend baseline into `frontend/`:
  - `index.html`, `panel.html`, `main.js`, `vscode-shim.js`
  - `peerjs.min.js`, `svg-pan-zoom.min.js`, `logo.png`

### Runtime + packaging
- split requirements:
  - `requirements-server.txt`
  - `requirements-capsule.txt`
  - `requirements.txt` (combined)
- scripts:
  - `scripts/setup.ps1`, `scripts/run.ps1`
  - `scripts/setup.sh`, `scripts/run.sh`
- config:
  - extended `config/.env.example` with persistence + capsule lifecycle controls
  - added `config/schema.py` scaffold
- dockerization:
  - `Dockerfile` (single-container full stack)
  - `Dockerfile.proxy` (proxy-only)
  - `Dockerfile.capsule` (capsule-only)
  - `docker-compose.yml` (single container)
  - `docker-compose.split.yml` (proxy + capsule)
  - `docker-compose.remote.yml` (proxy + remote capsule)
  - `.dockerignore`

## Verified

- Python compile pass for backend modules (`python -m compileall ...`)
- Server boot verification with `MANAGE_LOCAL_CAPSULE=0`
- `GET /api/health` returns valid JSON on localhost (includes reconnect backoff state)
- `POST /api/capsule/restart` returns expected guard error in remote/proxy mode
- `GET /api/tools` and `POST /api/tool/get_genesis` return expected 503 when MCP is unavailable

## Pending to complete Phase 1 acceptance

- Full startup with local capsule active and MCP session connected
- Live tool proxy verification (`get_status`, `list_slots`, `bag_catalog`)
- Confirm frontend tabs render correctly end-to-end at `/panel`
- Verify external MCP client connects through `/mcp/sse`
