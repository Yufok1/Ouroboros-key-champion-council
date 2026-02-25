# Phase 1 Acceptance Test — 2026-02-25

## Environment
- Working dir: `Champion_Council/self_deploy`
- Mode: `MANAGE_LOCAL_CAPSULE=1`
- Ports: `APP_PORT=7876`, `MCP_PORT=8765`
- Persistence: `PERSISTENCE_MODE=local`

## Results

### 1) Boot local capsule + backend
- ✅ PASS
- Time to healthy MCP session: ~98s
- `/api/health` showed:
  - `capsule_running: true`
  - `mcp_session: true`
  - `mcp_reconnect.attempts: 0`

### 2) Tool proxy checks
- ✅ `POST /api/tool/get_status` → 200
- ✅ `POST /api/tool/get_genesis` → 200
  - Returned valid genesis payload directly (fallback patch not needed in this run)
- ✅ `POST /api/tool/list_slots` → 200 (~0.04s)
- ✅ `POST /api/tool/bag_catalog` → 200 (~0.03s)

### 3) Panel check
- ✅ `GET /panel` → 200
- ✅ Tab labels present in served HTML: Overview, Council, Memory, Activity, Tools

### 4) MCP reverse proxy check
- ✅ `GET /mcp/sse` → 200
- ✅ SSE endpoint rewrite observed:
  - `data: http://127.0.0.1:<APP_PORT>/mcp/messages/?session_id=...`
- ✅ MCP SDK client handshake through proxy succeeded:
  - `initialize` OK
  - `list_tools` returned tool set (143 in this local runtime)
  - `call_tool("heartbeat")` returned valid payload

### 5) Persistence check
- ✅ `POST /api/persist/save` → 200 `{ "status": "saved" }` (~6.56s)
- ✅ `POST /api/persist/restore` → 200 `{ "status": "restored" }`
- ✅ Local files written:
  - `data/bag/bag_export.json`
  - `data/brain/brain_state.pkl`
  - `data/config/state_meta.json`
  - `data/slots/slot_manifest.json`
  - `data/workflows/workflows.json`

## Notes
- Initial quick run used short HTTP timeouts and produced false negatives for `bag_catalog`/`persist_save`; rerun with proper timeout confirmed both pass.
- `get_genesis` patch path remains implemented; runtime did not trigger the fallback because the capsule returned valid genesis data.

## Verdict
- **Phase 1 acceptance: PASS** (local capsule mode validated end-to-end).
