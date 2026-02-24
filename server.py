"""
Champion Council — HuggingFace Space Server
Runs the capsule MCP backend + web control panel + publish webhook.

Architecture:
  1. Capsule (champion_gen8.py) runs as MCP/SSE server on port 8765
  2. FastAPI serves the web control panel on port 7860
  3. FastAPI proxies tool calls from the browser to the capsule MCP server
  4. Webhook endpoint triggers vsix build + marketplace publish
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
            # Keep last 200 lines
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
        # Wait for MCP server to be ready
        for i in range(30):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(f"{MCP_BASE}/sse", timeout=2)
                    if r.status_code in (200, 307):
                        print(f"[OK] MCP server ready after {i+1}s")
                        break
            except Exception:
                await asyncio.sleep(1)
        else:
            print("[WARN] MCP server did not respond within 30s")


@app.on_event("shutdown")
async def on_shutdown():
    stop_capsule()


# --- MCP Tool Proxy ---
# The browser calls our API, we forward to the capsule's MCP server

@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    """Proxy a tool call to the capsule MCP server."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # MCP tool call via JSON-RPC
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": body
                }
            }
            r = await client.post(f"{MCP_BASE}/mcp", json=payload)
            return r.json()
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"error": "Capsule MCP server not running"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/tools")
async def list_tools():
    """List all available MCP tools from the capsule."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            r = await client.post(f"{MCP_BASE}/mcp", json=payload)
            return r.json()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


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
