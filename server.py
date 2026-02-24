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
from fastapi.responses import HTMLResponse, JSONResponse
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
    """Wait for capsule SSE endpoint to be reachable."""
    for i in range(timeout):
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{MCP_BASE}/sse", timeout=2)
                if r.status_code == 200:
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
            print(f"[OK] MCP session initialized — server: {result.server_info.name if result.server_info else 'unknown'}")
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
                "isError": result.isError if hasattr(result, 'isError') else False,
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
                        "inputSchema": t.inputSchema if hasattr(t, 'inputSchema') else {},
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


app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
