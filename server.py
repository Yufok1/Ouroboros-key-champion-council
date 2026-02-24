"""
Champion Council — HuggingFace Space Server
Runs the capsule MCP backend + web control panel.

Architecture:
  1. Capsule (champion_gen8.py) runs as MCP/SSE server on port 8765
  2. FastAPI serves the web control panel on port 7860
  3. FastAPI proxies tool calls from the browser to the capsule via mcp SDK client
"""
import os
import sys
import json
import asyncio
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from mcp import ClientSession
from mcp.client.sse import sse_client

import time


def _broadcast_activity(tool: str, args: dict, result: dict | None, duration_ms: int, error: str | None, source: str = "external"):
    """Record and broadcast a tool call to all SSE activity subscribers."""
    cat = tool.split("_")[0] if tool else "other"
    entry = {
        "tool": tool,
        "category": cat,
        "args": args or {},
        "result": result,
        "error": error,
        "durationMs": duration_ms,
        "timestamp": int(time.time() * 1000),
        "source": source,
    }
    _activity_log.append(entry)
    if len(_activity_log) > 500:
        _activity_log.pop(0)
    # Push to all SSE subscribers
    dead = []
    for q in _activity_subscribers:
        try:
            q.put_nowait(entry)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            _activity_subscribers.remove(q)
        except ValueError:
            pass

# --- Configuration ---
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
WEB_PORT = 7860
CAPSULE_PATH = Path("capsule/champion_gen8.py")
MCP_BASE = f"http://127.0.0.1:{MCP_PORT}"

capsule_process = None
capsule_log_lines = []

# Activity tracking for SSE broadcast to web UI
_activity_log = []       # list of activity event dicts
_activity_subscribers = []  # list of asyncio.Queue for SSE clients

# MCP client session (managed by lifespan)
_mcp_session: ClientSession | None = None
_mcp_lock = asyncio.Lock()


# --- Capsule Process Management ---

def start_capsule():
    global capsule_process
    if not CAPSULE_PATH.exists():
        print(f"[WARN] Capsule not found at {CAPSULE_PATH}")
        return False

    env = {**os.environ, "MCP_PORT": str(MCP_PORT)}
    capsule_process = subprocess.Popen(
        [sys.executable, "-u", str(CAPSULE_PATH), "--mcp-remote", "--port", str(MCP_PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"[OK] Capsule started (PID {capsule_process.pid}) on port {MCP_PORT}")

    def _read_output():
        for line in iter(capsule_process.stdout.readline, b''):
            decoded = line.decode('utf-8', errors='replace').rstrip()
            capsule_log_lines.append(decoded)
            if len(capsule_log_lines) > 200:
                capsule_log_lines.pop(0)
            print(f"[CAPSULE] {decoded}")
        print("[CAPSULE] Process output stream ended")

    threading.Thread(target=_read_output, daemon=True).start()
    return True


def stop_capsule():
    global capsule_process
    if capsule_process:
        capsule_process.terminate()
        capsule_process.wait(timeout=10)
        capsule_process = None


async def _wait_for_capsule_sse(timeout=90):
    """Wait for capsule SSE endpoint to be reachable (HEAD to avoid orphaned SSE streams)."""
    for i in range(timeout):
        try:
            async with httpx.AsyncClient() as c:
                r = await c.head(f"{MCP_BASE}/sse", timeout=2)
                if r.status_code in (200, 405):
                    # 200 = HEAD supported, 405 = method not allowed but server is up
                    print(f"[OK] Capsule SSE responding after {i+1}s")
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    print(f"[WARN] Capsule SSE not responding after {timeout}s")
    return False


# --- MCP Client Session via SDK ---
# The mcp SDK's sse_client + ClientSession handles:
#   - SSE connection management
#   - Session endpoint discovery
#   - initialize/initialized handshake
#   - JSON-RPC request/response matching
# We just need to keep the context managers alive.

_sse_cm = None       # sse_client context manager
_session_cm = None   # ClientSession context manager
_read_stream = None
_write_stream = None


async def _connect_mcp():
    """Connect to capsule MCP server using the SDK client."""
    global _mcp_session, _sse_cm, _session_cm, _read_stream, _write_stream

    async with _mcp_lock:
        if _mcp_session is not None:
            return True

        try:
            # sse_client is an async context manager that returns (read, write) streams
            _sse_cm = sse_client(f"{MCP_BASE}/sse")
            _read_stream, _write_stream = await _sse_cm.__aenter__()

            # ClientSession wraps the streams with JSON-RPC protocol
            _session_cm = ClientSession(_read_stream, _write_stream)
            _mcp_session = await _session_cm.__aenter__()

            # Initialize the session (sends initialize + notifications/initialized)
            result = await _mcp_session.initialize()
            # Extract server name safely — attribute varies across mcp SDK versions
            # (server_info, serverInfo, or nested in capabilities)
            _sinfo = getattr(result, 'server_info', None) or getattr(result, 'serverInfo', None)
            _sname = getattr(_sinfo, 'name', None) if _sinfo else None
            if _sname is None and hasattr(result, '__dict__'):
                # Last resort: dig through the raw result dict
                for _k in ('server_info', 'serverInfo'):
                    _v = result.__dict__.get(_k) or (result.model_dump() if hasattr(result, 'model_dump') else {}).get(_k)
                    if isinstance(_v, dict):
                        _sname = _v.get('name')
                    elif _v and hasattr(_v, 'name'):
                        _sname = _v.name
                    if _sname:
                        break
            print(f"[OK] MCP session initialized — server: {_sname or 'unknown'}")
            return True

        except Exception as e:
            print(f"[ERR] MCP connect failed: {e}")
            await _disconnect_mcp_inner()
            return False


async def _disconnect_mcp_inner():
    """Tear down MCP session (call under lock or from lifespan)."""
    global _mcp_session, _sse_cm, _session_cm
    if _session_cm:
        try:
            await _session_cm.__aexit__(None, None, None)
        except Exception:
            pass
        _session_cm = None
    if _sse_cm:
        try:
            await _sse_cm.__aexit__(None, None, None)
        except Exception:
            pass
        _sse_cm = None
    _mcp_session = None


async def _disconnect_mcp():
    async with _mcp_lock:
        await _disconnect_mcp_inner()


async def _ensure_session() -> ClientSession | None:
    """Get the MCP session, reconnecting if needed."""
    if _mcp_session is not None:
        return _mcp_session
    ok = await _connect_mcp()
    return _mcp_session if ok else None


async def _call_tool(name: str, arguments: dict) -> dict:
    """Call an MCP tool via the SDK session."""
    session = await _ensure_session()
    if not session:
        return {"error": "MCP session not available"}
    try:
        result = await session.call_tool(name, arguments)
        # Convert to JSON-serializable dict
        return {
            "result": {
                "content": [
                    {"type": c.type, "text": c.text if hasattr(c, 'text') else str(c)}
                    for c in (result.content or [])
                ],
                "isError": getattr(result, 'isError', None) or getattr(result, 'is_error', False),
            }
        }
    except Exception as e:
        # Session might be dead — tear down so next call reconnects
        await _disconnect_mcp()
        return {"error": str(e)}


async def _list_tools() -> dict:
    """List MCP tools via the SDK session."""
    session = await _ensure_session()
    if not session:
        return {"error": "MCP session not available"}
    try:
        result = await session.list_tools()
        return {
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": getattr(t, 'inputSchema', None) or getattr(t, 'input_schema', {}),
                    }
                    for t in (result.tools or [])
                ]
            }
        }
    except Exception as e:
        await _disconnect_mcp()
        return {"error": str(e)}


# --- App Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    gz_path = Path("capsule/capsule.gz")
    if gz_path.exists() and not CAPSULE_PATH.exists():
        import gzip
        print("[INIT] Decompressing capsule.gz...")
        CAPSULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(gz_path, "rb") as f_in:
            CAPSULE_PATH.write_bytes(f_in.read())
        print(f"[OK] Capsule decompressed ({CAPSULE_PATH.stat().st_size:,} bytes)")

    if CAPSULE_PATH.exists():
        start_capsule()
        print("[INIT] Waiting for capsule MCP server...")
        if await _wait_for_capsule_sse(timeout=90):
            ok = await _connect_mcp()
            if ok:
                print("[OK] MCP proxy ready")
            else:
                print("[WARN] MCP connect failed (will retry on first request)")

    yield

    # Shutdown
    await _disconnect_mcp()
    stop_capsule()


app = FastAPI(title="Champion Council", version="0.8.9", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Routes ---

@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    start = time.time()
    result = await _call_tool(tool_name, body)
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    _broadcast_activity(tool_name, body, result.get("result"), duration_ms, error_str, source="proxy")
    if error_str:
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/tools")
async def list_tools_route():
    result = await _list_tools()
    if "error" in result and isinstance(result["error"], str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/health")
async def health():
    capsule_alive = capsule_process is not None and capsule_process.poll() is None
    return {
        "status": "ok",
        "version": "0.8.9",
        "capsule_running": capsule_alive,
        "capsule_pid": capsule_process.pid if capsule_alive else None,
        "mcp_port": MCP_PORT,
        "mcp_session": _mcp_session is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/capsule-log")
async def capsule_log():
    return {"lines": capsule_log_lines[-100:]}


@app.get("/api/activity-stream")
async def activity_stream():
    """SSE stream of tool call activity for the web UI Activity tab."""
    q = asyncio.Queue(maxsize=100)
    _activity_subscribers.append(q)

    async def _stream():
        try:
            # Send recent history first so the UI hydrates immediately
            for entry in _activity_log[-50:]:
                yield f"data: {json.dumps(entry)}\n\n"
            # Then stream live events
            while True:
                entry = await q.get()
                yield f"data: {json.dumps(entry)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                _activity_subscribers.remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/activity-log")
async def activity_log_route():
    """Return recent activity log as JSON (for initial hydration)."""
    return {"entries": _activity_log[-100:]}


@app.get("/", response_class=HTMLResponse)
async def landing():
    return Path("static/index.html").read_text()


@app.get("/panel", response_class=HTMLResponse)
async def control_panel():
    return Path("static/panel.html").read_text()


# --- MCP SSE Reverse Proxy ---
# Exposes the internal capsule MCP server (port 8765) to external MCP clients.
# External clients connect to /mcp/sse and POST to /mcp/message, which get
# proxied to the capsule's /sse and /message endpoints inside the container.
# This lets Kiro / VS Code / Claude Desktop connect directly to the Space.

@app.get("/mcp/sse")
async def mcp_sse_proxy(request: Request):
    """Proxy SSE stream from capsule MCP server to external client.

    The capsule sends an 'endpoint' event with a URL like:
      - Relative: /messages/?session_id=xxx
      - Absolute: http://127.0.0.1:8765/messages/?session_id=xxx
    We rewrite it to our public /mcp/messages/ route so the external
    client POSTs back through us.
    """
    import re

    # Build the public base URL from the incoming request
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", request.url.netloc)
    public_base = f"{proto}://{host}"
    print(f"[MCP-PROXY] SSE connect — public_base={public_base}")

    async def _stream():
        endpoint_rewritten = False
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{MCP_BASE}/sse", timeout=None) as resp:
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        # Process complete lines
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if not endpoint_rewritten and line.startswith("data:") and "/messages" in line:
                                raw = line.split("data:", 1)[1].strip()
                                if raw.startswith("http://") or raw.startswith("https://"):
                                    from urllib.parse import urlparse
                                    parsed = urlparse(raw)
                                    path_and_query = parsed.path
                                    if parsed.query:
                                        path_and_query += "?" + parsed.query
                                else:
                                    path_and_query = raw
                                if not path_and_query.startswith("/"):
                                    path_and_query = "/" + path_and_query
                                rewritten = f"data: {public_base}/mcp{path_and_query}"
                                print(f"[MCP-PROXY] Rewrote endpoint: {line.strip()} -> {rewritten.strip()}")
                                endpoint_rewritten = True
                                yield rewritten + "\n"
                            else:
                                # Log non-empty lines to debug SSE event flow
                                if line.strip():
                                    print(f"[MCP-PROXY] SSE>> {line[:120]}")
                                yield line + "\n"
        except httpx.RemoteProtocolError:
            pass
        except Exception as e:
            print(f"[MCP-PROXY] SSE stream error: {e}")
            yield f"event: error\ndata: {e}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/mcp/message")
@app.post("/mcp/messages/")
@app.post("/mcp/messages")
async def mcp_message_proxy(request: Request):
    """Proxy JSON-RPC messages from external client to capsule MCP server."""
    session_id = request.query_params.get("session_id", "")
    body = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    print(f"[MCP-PROXY] POST /mcp/message(s) session_id={session_id} len={len(body)}")

    # Try to extract tool name from JSON-RPC body for activity tracking
    rpc_method = None
    rpc_tool = None
    rpc_args = {}
    try:
        rpc_body = json.loads(body)
        rpc_method = rpc_body.get("method", "")
        if rpc_method == "tools/call":
            params = rpc_body.get("params", {})
            rpc_tool = params.get("name", "unknown")
            rpc_args = params.get("arguments", {})
    except Exception:
        pass

    start = time.time()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MCP_BASE}/messages/",
                params={"session_id": session_id},
                content=body,
                headers={"Content-Type": content_type},
                timeout=120,
            )
            duration_ms = int((time.time() - start) * 1000)
            print(f"[MCP-PROXY] Capsule responded {resp.status_code}")

            # Track tool calls in activity feed
            if rpc_tool:
                _broadcast_activity(rpc_tool, rpc_args, None, duration_ms, None, source="external")

            # Forward the response as-is
            if resp.status_code in (202, 204):
                # MCP SSE protocol: POST returns bare 202, response comes on SSE stream
                from starlette.responses import Response
                return Response(status_code=resp.status_code)
            elif resp.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
            else:
                return JSONResponse(
                    content={"raw": resp.text} if resp.text else {},
                    status_code=resp.status_code,
                )
    except httpx.ReadTimeout:
        duration_ms = int((time.time() - start) * 1000)
        if rpc_tool:
            _broadcast_activity(rpc_tool, rpc_args, None, duration_ms, "Capsule timeout", source="external")
        return JSONResponse(status_code=504, content={"error": "Capsule timeout"})
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        if rpc_tool:
            _broadcast_activity(rpc_tool, rpc_args, None, duration_ms, str(e), source="external")
        print(f"[MCP-PROXY] POST error: {e}")
        return JSONResponse(status_code=502, content={"error": str(e)})


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="."), name="media")


# Kiro tries Streamable HTTP (POST) first before falling back to SSE.
# Return 405 to signal that SSE transport should be used instead.
@app.post("/mcp/sse")
async def mcp_sse_post_fallback(request: Request):
    """Return 405 so MCP clients fall back to SSE transport."""
    return JSONResponse(
        status_code=405,
        content={"error": "Use GET for SSE transport"},
        headers={"Allow": "GET"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
