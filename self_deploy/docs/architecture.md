# Standalone Architecture (Target)

## Components

1. **Capsule Runtime**
   - `champion_gen8.py`
   - Runs MCP over SSE/HTTP on configurable port

2. **Local Control Backend**
   - FastAPI service
   - Proxies tool calls to capsule via MCP SDK
   - Exposes REST + SSE for web UI
   - Exposes MCP reverse-proxy endpoint for IDEs

3. **Web UI**
   - Space-style panel (tabs + activity stream)
   - Talks only to local backend
   - No direct capsule process coupling

4. **Secrets/Integrations Layer**
   - Validates configured providers
   - Redacted status outputs only
   - Zero plaintext secret echo in UI logs

5. **Persistence Layer**
   - Local files for bag/workflows/state
   - Optional HF dataset sync when token exists

## Request Flow

Browser UI -> Local Backend -> MCP Client Session -> Capsule MCP Server -> Tool Result -> UI

## Design Rules

- Do not modify quine source during wrapper integration unless explicitly approved.
- Keep API envelopes normalized once at backend boundary.
- Keep long-running operations async and observable (activity + status).
- Keep extension and space wrappers aligned through shared contracts.
