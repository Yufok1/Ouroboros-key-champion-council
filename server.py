"""
Champion Council — HuggingFace Space Server
Runs the capsule MCP backend + web control panel.

Architecture:
  1. Capsule (champion_gen8.py) runs as MCP/SSE server on port 8765
  2. FastAPI serves the web control panel on port 7860
  3. FastAPI proxies tool calls from the browser to the capsule MCP server
     using a persistent SSE session with proper JSON-RPC initialize handshake
"""
import os
import sys
import json
import time
import signal
import asyncio
import subprocess
import threading
from pathlib import Path
from datetime import datetime

import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# --- Configuration ---
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
WEB_PORT = 7860
CAPSULE_PATH = Path("capsule/champion_gen8.py")
MCP_BASE = f"http://127.0.0.1:{MCP_PORT}"

app = FastAPI(title="Champion Council", version="0.8.9")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

capsule_process = None
capsule_log_lines = []

# --- Persistent MCP Session ---
# Instead of creating a new SSE connection per tool call, we maintain ONE
# persistent SSE session. We send `initialize` + `initialized` on connect,
# then reuse the session's message endpoint for all subsequent JSON-RPC calls.
# Responses come back on the SSE stream keyed by JSON-RPC id.

_mcp_session_url = None       # POST endpoint for this session
_mcp_client = None            # persistent httpx.AsyncClient
_mcp_sse_task = None          # background task reading SSE events
_mcp_pending = {}             # id -> asyncio.Future for pending requests
_mcp_ready = asyncio.Event()  # set once initialize handshake completes
_mcp_lock = asyncio.Lock()    # serialize session setup
_mcp_jsonrpc_id = 0
_mcp_id_lock = threading.Lock()

def _next_id():
    global _mcp_jsonrpc_id
    with _mcp_id_lock:
        _mcp_jsonrpc_id += 1
        return _mcp_jsonrpc_id


# --- Capsule Process Management ---

def start_capsule():
    """Start the champion capsule as a subprocess running MCP/SSE server."""
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

    def _read_capsule_output():
        for line in iter(capsule_process.stdout.readline, b''):
            decoded = line.decode('utf-8', errors='replace').rstrip()
            capsule_log_lines.append(decoded)
            if len(capsule_log_lines) > 200:
                capsule_log_lines.pop(0)
            print(f"[CAPSULE] {decoded}")
        print("[CAPSULE] Process output stream ended")

    t = threading.Thread(target=_read_capsule_output, daemon=True)
    t.start()
    return True


def stop_capsule():
    """Stop the capsule subprocess."""
    global capsule_process
    if capsule_process:
        capsule_process.terminate()
        capsule_process.wait(timeout=10)
        capsule_process = None


# --- Persistent SSE Session Management ---

async def _ensure_mcp_session():
    """
    Establish a persistent SSE connection to the capsule MCP server,
    discover the session message URL, and perform the initialize handshake.
    This is called once at startup and again if the session drops.
    """
    global _mcp_session_url, _mcp_client, _mcp_sse_task

    async with _mcp_lock:
        # Already ready?
        if _mcp_ready.is_set() and _mcp_session_url:
            return True

        # Clean up any previous session
        await _teardown_mcp_session()

        _mcp_ready.clear()

        try:
            _mcp_client_new = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10))

            # Open persistent SSE stream
            sse_response = await _mcp_client_new.send(
                _mcp_client_new.build_request("GET", f"{MCP_BASE}/sse"),
                stream=True
            )

            # We need to read lines from the SSE stream to get the endpoint event
            # Do this in a background task, but first get the session URL
            session_url = None
            buffer = ""
            async for chunk in sse_response.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if "/messages" in data:
                            if data.startswith("/"):
                                session_url = f"{MCP_BASE}{data}"
                            elif data.startswith("http"):
                                session_url = data
                            else:
                                session_url = f"{MCP_BASE}/{data}"
                            break
                if session_url:
                    break

            if not session_url:
                print("[ERR] Could not discover MCP session endpoint from SSE")
                await sse_response.aclose()
                await _mcp_client_new.aclose()
                return False

            print(f"[OK] MCP session endpoint: {session_url}")
            _mcp_session_url = session_url

            # Store client globally so background reader can use it
            globals()['_mcp_client'] = _mcp_client_new
            globals()['_mcp_sse_response'] = sse_response
            globals()['_mcp_sse_buffer'] = buffer

            # Start background SSE reader task
            _mcp_sse_task = asyncio.create_task(_sse_reader(sse_response, buffer))

            # Send initialize handshake
            init_id = _next_id()
            init_payload = {
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "champion-council-web", "version": "0.8.9"}
                }
            }

            # Create a future for the initialize response
            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            _mcp_pending[init_id] = fut

            # POST the initialize request
            r = await _mcp_client_new.post(session_url, json=init_payload)
            if r.status_code not in (200, 202):
                print(f"[ERR] Initialize POST returned {r.status_code}: {r.text}")
                return False

            # Wait for initialize response (with timeout)
            try:
                init_result = await asyncio.wait_for(fut, timeout=30)
                print(f"[OK] MCP initialize response received")
            except asyncio.TimeoutError:
                print("[WARN] Initialize response timed out, proceeding anyway")

            # Send initialized notification (no id, no response expected)
            notif_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await _mcp_client_new.post(session_url, json=notif_payload)
            print("[OK] MCP session initialized — ready for tool calls")

            _mcp_ready.set()
            return True

        except Exception as e:
            print(f"[ERR] Failed to establish MCP session: {e}")
            return False


async def _sse_reader(sse_response, initial_buffer=""):
    """Background task that reads the persistent SSE stream and resolves pending futures."""
    buffer = initial_buffer
    try:
        async for chunk in sse_response.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line.startswith("data:"):
                    data = line[5:].strip()
                    # Skip endpoint events (already handled)
                    if "/messages" in data and "session_id" in data:
                        continue
                    # Try to parse as JSON-RPC response
                    try:
                        msg = json.loads(data)
                        if isinstance(msg, dict) and "id" in msg:
                            req_id = msg["id"]
                            fut = _mcp_pending.pop(req_id, None)
                            if fut and not fut.done():
                                fut.set_result(msg)
                    except (json.JSONDecodeError, ValueError):
                        pass
    except httpx.ReadError:
        print("[WARN] MCP SSE stream closed (ReadError)")
    except Exception as e:
        print(f"[WARN] MCP SSE reader error: {e}")
    finally:
        _mcp_ready.clear()
        print("[WARN] MCP SSE session ended — will reconnect on next call")


async def _teardown_mcp_session():
    """Clean up the persistent MCP session."""
    global _mcp_session_url, _mcp_client, _mcp_sse_task
    _mcp_ready.clear()
    _mcp_session_url = None

    if _mcp_sse_task and not _mcp_sse_task.done():
        _mcp_sse_task.cancel()
        try:
            await _mcp_sse_task
        except (asyncio.CancelledError, Exception):
            pass
    _mcp_sse_task = None

    sse_resp = globals().pop('_mcp_sse_response', None)
    if sse_resp:
        try:
            await sse_resp.aclose()
        except Exception:
            pass

    if _mcp_client:
        try:
            await _mcp_client.aclose()
        except Exception:
            pass
        _mcp_client = None

    # Cancel all pending futures
    for fut in _mcp_pending.values():
        if not fut.done():
            fut.cancel()
    _mcp_pending.clear()


# --- MCP Tool Call (uses persistent session) ---

async def _mcp_call(method: str, params: dict) -> dict:
    """Send a JSON-RPC call via the persistent MCP session."""
    # Ensure session is up
    if not _mcp_ready.is_set():
        ok = await _ensure_mcp_session()
        if not ok:
            return {"error": "MCP session not established"}

    if not _mcp_session_url or not _mcp_client:
        return {"error": "MCP session not available"}

    req_id = _next_id()
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params
    }

    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _mcp_pending[req_id] = fut

    try:
        r = await _mcp_client.post(_mcp_session_url, json=payload)
        if r.status_code not in (200, 202):
            _mcp_pending.pop(req_id, None)
            return {"error": f"MCP returned {r.status_code}: {r.text}"}
    except httpx.ConnectError:
        _mcp_pending.pop(req_id, None)
        # Session died — reset so next call reconnects
        _mcp_ready.clear()
        _mcp_session_url = None
        return {"error": "Capsule MCP server not reachable"}
    except Exception as e:
        _mcp_pending.pop(req_id, None)
        return {"error": str(e)}

    # Wait for response on the SSE stream
    try:
        result = await asyncio.wait_for(fut, timeout=120)
        return result
    except asyncio.TimeoutError:
        _mcp_pending.pop(req_id, None)
        return {"error": "MCP call timed out (120s)"}


# --- Startup / Shutdown ---

@app.on_event("startup")
async def on_startup():
    # Decompress capsule if needed
    gz_path = Path("capsule/capsule.gz")
    if gz_path.exists() and not CAPSULE_PATH.exists():
        import gzip
        print("[INIT] Decompressing capsule.gz...")
        CAPSULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(gz_path, "rb") as f_in:
            CAPSULE_PATH.write_bytes(f_in.read())
        print(f"[OK] Capsule decompressed ({CAPSULE_PATH.stat().st_size:,} bytes)")

    # Start capsule
    if CAPSULE_PATH.exists():
        start_capsule()
        # Wait for capsule SSE to be listening
        print("[INIT] Waiting for capsule MCP server...")
        for i in range(60):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{MCP_BASE}/sse", timeout=2)
                    if r.status_code == 200:
                        print(f"[OK] Capsule SSE responding after {i+1}s")
                        break
            except Exception:
                await asyncio.sleep(1)
        else:
            print("[WARN] Capsule SSE not responding after 60s")
            return

        # Establish persistent MCP session with initialize handshake
        ok = await _ensure_mcp_session()
        if ok:
            print("[OK] MCP proxy ready — persistent session established")
        else:
            print("[WARN] Could not establish MCP session (will retry on first call)")


@app.on_event("shutdown")
async def on_shutdown():
    await _teardown_mcp_session()
    stop_capsule()


# --- API Routes ---

@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    """Proxy a tool call to the capsule MCP server."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    result = await _mcp_call("tools/call", {"name": tool_name, "arguments": body})

    if "error" in result and isinstance(result["error"], str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/tools")
async def list_tools():
    """List all available MCP tools from the capsule."""
    result = await _mcp_call("tools/list", {})
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
        "capsule_exit_code": capsule_process.poll() if capsule_process else None,
        "mcp_port": MCP_PORT,
        "mcp_session": _mcp_ready.is_set(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/capsule-log")
async def capsule_log():
    """Return recent capsule output for debugging."""
    return {"lines": capsule_log_lines[-100:]}


# --- Landing Page ---

@app.get("/", response_class=HTMLResponse)
async def landing():
    return Path("static/index.html").read_text()


# --- Control Panel ---

@app.get("/panel", response_class=HTMLResponse)
async def control_panel():
    return Path("static/panel.html").read_text()


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Entry Point ---

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
