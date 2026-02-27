# Champion Council Self-Deploy (Local Standalone)

This folder is a local standalone runtime for Champion Council/Ouroboros that mirrors the Hugging Face Space behavior while running on your own machine.

Default capsule paths are local to this folder (`./capsule`). If capsule files are missing, self_deploy first tries `../capsule/capsule.gz` as a local fallback, then auto-downloads `capsule.gz`.

## What is implemented now

- Local FastAPI backend (`backend/server.py`)
- Capsule process manager with Windows-aware shutdown behavior
- MCP SDK session manager with reconnect backoff
- Tool proxy routes (`/api/tool/{name}`, `/api/tools`, `/api/health`)
- Capsule utility routes (`/api/capsule-log`, `/api/capsule/restart`)
- MCP reverse proxy for IDE clients (`/mcp/sse`, `/mcp/messages`)
- Activity SSE stream (`/api/activity-stream`) + activity log
- Postprocessing compatibility patches (`get_genesis`, `compare`, `debate`, `orchestra`)
- Workflow normalization middleware (`tool_call` + `tool_name` compatibility)
- Dual-mode persistence manager (`local`, `hf`, `both`)
- Dreamer + Vast aggregation routes
- Vast instance normalization (`/api/vast/state`) with SSH bootstrap status in state payload
- GPU Fleet parity UI behavior (instance-aware rent/connect/stop actions and direct Vast Console links)
- Frontend baseline copied from Space (`frontend/`)

## Folder layout

- `frontend/` — panel UI assets (`panel.html`, `main.js`, `vscode-shim.js`, libs)
- `backend/` — API/proxy server + lifecycle managers
- `config/` — `.env` template + config schema scaffold
- `scripts/` — setup/run scripts for Windows + Unix
- `docs/` — sitrep, architecture, implementation notes
- `data/` — runtime persistence output (created automatically)

## Quickstart (Windows)

```powershell
cd Champion_Council/self_deploy
./scripts/setup.ps1          # server deps only
./scripts/run.ps1
```

## One-Click Docker (Windows)

- Double-click `START_DOCKER.bat`
- It builds/starts the stack and opens the panel automatically.
- First run may take longer while images build and capsule artifact downloads.

Open:
- Panel: `http://localhost:7866/panel`
- Health: `http://localhost:7866/api/health`
- MCP SSE: `http://localhost:7866/mcp/sse`

## Quickstart (Linux/Mac)

```bash
cd Champion_Council/self_deploy
./scripts/setup.sh           # server deps only
./scripts/run.sh
```

## Dependency modes

- `requirements-server.txt` — lightweight proxy/backend only
- `requirements-capsule.txt` — heavy ML stack for local capsule runtime
- `requirements.txt` — both combined

To install full stack in setup scripts:
- Windows: `./scripts/setup.ps1 -Full`
- Unix: `./scripts/setup.sh --full`

## Environment

Copy and edit:
- `config/.env.example` -> `config/.env`

Important settings:
- `PERSISTENCE_MODE=local|hf|both`
- `MANAGE_LOCAL_CAPSULE=1|0`
- `MCP_BASE_URL` (optional, for remote capsule)
- `VAST_API_KEY` (required for Vast tools)
- `SSH_PRIVATE_KEY` / `SSH_PUBLIC_KEY` (optional; if unset, runtime attempts to auto-generate `~/.ssh/id_rsa`)

---

## Docker

Three deployment modes are included:

1. **Single container (recommended v1)**
   - `docker-compose.yml`
   - Runs proxy + capsule deps in one service

2. **Split proxy/capsule containers**
   - `docker-compose.split.yml`
   - Runs lightweight proxy container + separate capsule container

3. **Proxy-only + remote capsule**
   - `docker-compose.remote.yml`
   - Connects to existing MCP capsule endpoint

### 1) Single container

```bash
docker compose up --build
```

### 2) Split containers

```bash
docker compose -f docker-compose.split.yml up --build
```

### 3) Proxy + remote capsule

```bash
MCP_BASE_URL=http://your-remote-capsule:8766 docker compose -f docker-compose.remote.yml up --build
```

### Capsule artifact mounting

By default, self_deploy compose files mount `./capsule` to `/app/capsule`.
This keeps the package self-contained and capsule updates independent from image rebuilds.
Compose also mounts `../capsule` read-only as `/app/bootstrap` so fresh clones can bootstrap without network access.

---

## Notes

- Quine source is **not modified** by this wrapper.
- Provider diagnostics UI and deeper wrapper unification are next phases.
- See `PLAN.md` for phase tracking.
