"""
Champion Council — HuggingFace Space Server
Runs the capsule MCP backend + web control panel.

Architecture:
  1. Capsule (champion_gen8.py) runs as MCP/SSE server on port 8765
  2. FastAPI serves the web control panel on port 7860
  3. FastAPI proxies tool calls from the browser to the capsule MCP server
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
# MCP SSE session endpoint — discovered at startup
_mcp_message_url = None
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

    # Background thread to read capsule output
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


async def _discover_mcp_session():
    """Connect to capsule SSE, read the endpoint event to get the message URL."""
    global _mcp_message_url
    for attempt in range(60):
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{MCP_BASE}/sse", timeout=5) as r:
                    async for line in r.aiter_lines():
                        line = line.strip()
                        if line.startswith("data: "):
                            data = line[6:]
                            # The endpoint event sends the message URL
                            if "/messages" in data or "message" in data.lower():
                                # Could be relative or absolute
                                if data.startswith("/"):
                                    _mcp_message_url = f"{MCP_BASE}{data}"
                                elif data.startswith("http"):
                                    _mcp_message_url = data
                                else:
                                    _mcp_message_url = f"{MCP_BASE}/{data}"
                                print(f"[OK] MCP session endpoint: {_mcp_message_url}")
                                return True
        except Exception:
            await asyncio.sleep(1)
    return False


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
        # Wait for capsule uvicorn to be listening, then discover session
        print("[INIT] Waiting for capsule MCP server...")
        for i in range(45):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{MCP_BASE}/sse", timeout=2)
                    if r.status_code == 200:
                        print(f"[OK] Capsule SSE responding after {i+1}s")
                        break
            except Exception:
                await asyncio.sleep(1)
        else:
            print("[WARN] Capsule SSE not responding after 45s")
            return

        # Discover the MCP message endpoint
        found = await _discover_mcp_session()
        if found:
            print(f"[OK] MCP proxy ready")
        else:
            print("[WARN] Could not discover MCP session endpoint")


@app.on_event("shutdown")
async def on_shutdown():
    stop_capsule()


# --- MCP Tool Proxy ---

async def _mcp_call(method: str, params: dict) -> dict:
    """Send a JSON-RPC call to the capsule MCP server via its session endpoint."""
    global _mcp_message_url

    if not _mcp_message_url:
        # Try to discover on the fly
        await _discover_mcp_session()

    if not _mcp_message_url:
        return {"error": "MCP session not established"}

    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": method,
        "params": params
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(_mcp_message_url, json=payload)
            if r.status_code == 202:
                # 202 Accepted — SSE transport acknowledges but result comes via SSE
                # For tool calls we need to read the result from SSE stream
                # Use a fresh SSE connection to get the response
                return await _mcp_call_with_sse(payload)
            elif r.status_code == 200:
                return r.json()
            else:
                return {"error": f"MCP returned {r.status_code}: {r.text}"}
    except httpx.ConnectError:
        _mcp_message_url = None  # Reset so next call re-discovers
        return {"error": "Capsule MCP server not reachable"}
    except Exception as e:
        return {"error": str(e)}


async def _mcp_call_with_sse(payload: dict) -> dict:
    """Full SSE-based MCP call: connect, get session, send request, read response."""
    request_id = payload["id"]
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Open SSE stream
            async with client.stream("GET", f"{MCP_BASE}/sse", timeout=120) as sse:
                session_url = None
                async for line in sse.aiter_lines():
                    line = line.strip()
                    # Parse SSE events
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        if session_url is None and "/messages" in data:
                            # Got the endpoint event
                            if data.startswith("/"):
                                session_url = f"{MCP_BASE}{data}"
                            elif data.startswith("http"):
                                session_url = data
                            else:
                                session_url = f"{MCP_BASE}/{data}"
                            # Now send our request
                            r = await client.post(session_url, json=payload)
                            # Continue reading SSE for the response
                        else:
                            # Try to parse as JSON-RPC response
                            try:
                                msg = json.loads(data)
                                if isinstance(msg, dict) and msg.get("id") == request_id:
                                    return msg
                            except (json.JSONDecodeError, ValueError):
                                pass
    except Exception as e:
        return {"error": f"SSE call failed: {str(e)}"}
    return {"error": "No response received from MCP"}


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
        "mcp_session": _mcp_message_url is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/capsule-log")
async def capsule_log():
    """Return recent capsule output for debugging."""
    return {"lines": capsule_log_lines[-100:]}


# --- SSE Proxy (pass through capsule's SSE stream) ---

@app.get("/api/sse")
async def proxy_sse(request: Request):
    """Proxy the capsule's SSE stream to the browser."""
    from starlette.responses import StreamingResponse

    async def event_stream():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{MCP_BASE}/sse") as r:
                    async for line in r.aiter_lines():
                        if await request.is_disconnected():
                            break
                        yield f"{line}\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Landing Page ---

@app.get("/", response_class=HTMLResponse)
async def landing():
    return Path("static/index.html").read_text()


# --- Serve the control panel ---

@app.get("/panel", response_class=HTMLResponse)
async def control_panel():
    return Path("static/panel.html").read_text()


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Entry Point ---

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
