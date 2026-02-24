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

# --- Configuration ---
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
WEB_PORT = 7860
CAPSULE_PATH = Path("capsule/champion_gen8.py")
MCP_BASE = f"http://127.0.0.1:{MCP_PORT}"

capsule_process = None
capsule_log_lines = []

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
    result = await _call_tool(tool_name, body)
    if "error" in result and isinstance(result["error"], str):
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

    The capsule sends an 'endpoint' event with a local URL like
    http://127.0.0.1:8765/message?session_id=xxx — we rewrite it
    to point at our public /mcp/message route instead.
    """
    import re

    # Build the public base URL from the incoming request
    # Prefer X-Forwarded headers (set by HF Space reverse proxy)
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", request.url.netloc)
    public_base = f"{proto}://{host}"
    print(f"[MCP-PROXY] SSE connect — public_base={public_base}")

    async def _stream():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{MCP_BASE}/sse", timeout=None) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data:") and "/message" in line:
                            # Rewrite internal URL to full public proxy URL
                            # e.g. "data: http://127.0.0.1:8765/message?session_id=abc"
                            # becomes "data: https://tostido-champion-council.hf.space/mcp/message?session_id=abc"
                            rewritten = re.sub(
                                r'data:\s*http://[^/]+(/message\S*)',
                                f'data: {public_base}/mcp\\1',
                                line,
                            )
                            print(f"[MCP-PROXY] Rewrote endpoint: {line.strip()} -> {rewritten.strip()}")
                            yield rewritten + "\n"
                        else:
                            yield line + "\n"
        except httpx.RemoteProtocolError:
            # Client disconnected — normal for SSE
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
async def mcp_message_proxy(request: Request):
    """Proxy JSON-RPC messages from external client to capsule MCP server."""
    session_id = request.query_params.get("session_id", "")
    body = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    print(f"[MCP-PROXY] POST /mcp/message session_id={session_id} len={len(body)}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MCP_BASE}/message",
                params={"session_id": session_id},
                content=body,
                headers={"Content-Type": content_type},
                timeout=120,
            )
            print(f"[MCP-PROXY] Capsule responded {resp.status_code}")
            # Forward the response as-is
            if resp.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
            else:
                # Some MCP responses are empty (202 Accepted)
                return JSONResponse(
                    content={"raw": resp.text} if resp.text else {},
                    status_code=resp.status_code,
                )
    except httpx.ReadTimeout:
        return JSONResponse(status_code=504, content={"error": "Capsule timeout"})
    except Exception as e:
        print(f"[MCP-PROXY] POST error: {e}")
        return JSONResponse(status_code=502, content={"error": str(e)})


# --- Streamable HTTP MCP Endpoint ---
# Kiro and modern MCP clients use Streamable HTTP: they POST JSON-RPC to a
# single URL and expect either a JSON response or an SSE stream back.
# This handler sits at the same /mcp/sse path so the existing config URL works.

# Persistent httpx client for SSE session management (Streamable HTTP needs
# to hold an SSE connection open per logical session for server-initiated msgs)
_streamable_sessions: dict[str, dict] = {}  # session_id -> {sse_task, queue, ...}


@app.post("/mcp/sse")
async def mcp_streamable_http(request: Request):
    """Streamable HTTP MCP endpoint.

    Modern MCP clients (Kiro, VS Code) POST JSON-RPC here.
    We forward to the capsule's internal SSE MCP server and return the result.

    Flow:
      1. If no SSE session exists, open one to the capsule (GET /sse)
      2. Parse the endpoint event to get the capsule's /message?session_id=...
      3. Forward the JSON-RPC POST to that endpoint
      4. Return the capsule's response (JSON or SSE stream)
    """
    body = await request.body()
    content_type = request.headers.get("content-type", "application/json")

    # Parse the JSON-RPC request to log it
    try:
        rpc = json.loads(body)
        method = rpc.get("method", "?")
        rpc_id = rpc.get("id", "?")
    except Exception:
        method, rpc_id = "?", "?"
    print(f"[MCP-STREAM] POST /mcp/sse method={method} id={rpc_id} len={len(body)}")

    # We need a session with the capsule's SSE server.
    # The capsule's SSE endpoint sends an "endpoint" event with the POST URL.
    # We cache this per-process since there's only one capsule.
    session_key = "_default"

    if session_key not in _streamable_sessions or not _streamable_sessions[session_key].get("message_url"):
        # Open SSE connection to capsule and grab the message endpoint
        print("[MCP-STREAM] Opening new SSE session to capsule...")
        try:
            message_url = await _discover_capsule_message_url(timeout=15)
            if message_url:
                _streamable_sessions[session_key] = {"message_url": message_url}
                print(f"[MCP-STREAM] Capsule message URL: {message_url}")
            else:
                print("[MCP-STREAM] Failed to discover capsule message URL")
                return JSONResponse(
                    status_code=502,
                    content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": "Capsule SSE not available"}},
                )
        except Exception as e:
            print(f"[MCP-STREAM] SSE discovery error: {e}")
            return JSONResponse(
                status_code=502,
                content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": f"Capsule connect failed: {e}"}},
            )

    message_url = _streamable_sessions[session_key]["message_url"]

    # Forward the JSON-RPC request to the capsule
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                message_url,
                content=body,
                headers={"Content-Type": content_type},
                timeout=120,
            )
        print(f"[MCP-STREAM] Capsule responded {resp.status_code} ct={resp.headers.get('content-type', '?')}")

        resp_ct = resp.headers.get("content-type", "")

        if "text/event-stream" in resp_ct:
            # Capsule wants to stream back — relay as SSE
            async def _relay():
                for line in resp.text.splitlines(keepends=True):
                    yield line
            return StreamingResponse(
                _relay(),
                media_type="text/event-stream",
                status_code=resp.status_code,
                headers={"Cache-Control": "no-cache"},
            )
        elif resp.status_code == 202 or resp.status_code == 204:
            # Accepted / No Content — notification acknowledged
            from fastapi.responses import Response
            return Response(status_code=202)
        else:
            # JSON response — return as-is
            try:
                return JSONResponse(content=resp.json(), status_code=resp.status_code)
            except Exception:
                return JSONResponse(
                    content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": resp.text[:500]}},
                    status_code=resp.status_code,
                )
    except httpx.ReadTimeout:
        return JSONResponse(status_code=504, content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": "Capsule timeout"}})
    except Exception as e:
        # Session might be stale — clear it so next request rediscovers
        _streamable_sessions.pop(session_key, None)
        print(f"[MCP-STREAM] Forward error: {e}")
        return JSONResponse(
            status_code=502,
            content={"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(e)}},
        )


async def _discover_capsule_message_url(timeout: int = 15) -> str | None:
    """Connect to capsule SSE, read the 'endpoint' event, return the message URL."""
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", f"{MCP_BASE}/sse", timeout=timeout) as resp:
                async for line in resp.aiter_lines():
                    # The MCP SSE server sends: event: endpoint\ndata: /message?session_id=xxx
                    # or: data: http://127.0.0.1:8765/message?session_id=xxx
                    if line.startswith("data:") and "message" in line:
                        url = line.split("data:", 1)[1].strip()
                        # Handle relative URLs — prepend capsule base
                        if url.startswith("/"):
                            url = f"{MCP_BASE}{url}"
                        elif not url.startswith("http"):
                            url = f"{MCP_BASE}/{url}"
                        print(f"[MCP-STREAM] Discovered message URL: {url}")
                        return url
    except Exception as e:
        print(f"[MCP-STREAM] Discovery error: {e}")
    return None


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="."), name="media")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
