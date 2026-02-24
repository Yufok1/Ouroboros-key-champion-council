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

# Tools that are internal plumbing — don't broadcast to activity feed
_SILENT_TOOLS = frozenset([
    'get_status', 'list_slots', 'bag_catalog', 'workflow_list',
    'verify_integrity', 'get_cached', 'get_identity', 'feed',
    'get_capabilities', 'get_help', 'get_onboarding', 'get_quickstart',
    'hub_tasks', 'list_tools', 'heartbeat',
])


def _parse_mcp_result(result: dict | None) -> dict | None:
    """Extract the actual JSON data from an MCP tool result envelope."""
    if not result:
        return None
    # MCP envelope: { content: [{ type: "text", text: "..." }] }
    content = result.get("content")
    if isinstance(content, list) and len(content) > 0:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
    return result


def _broadcast_activity(tool: str, args: dict, result: dict | None, duration_ms: int, error: str | None, source: str = "external"):
    """Record and broadcast a tool call to all SSE activity subscribers."""
    # Suppress hydration calls entirely
    if source == "hydration":
        return
    # Only suppress silent tools for internal/webui calls — external MCP
    # clients (Kiro, Claude, etc.) should always see their results.
    if tool in _SILENT_TOOLS and source != "external":
        return

    cat = tool.split("_")[0] if tool else "other"
    # Parse the MCP envelope so the frontend gets real data
    parsed_result = _parse_mcp_result(result)
    # Debug: log what we're broadcasting so we can trace blank-data issues
    result_preview = str(parsed_result)[:200] if parsed_result else "None"
    print(f"[ACTIVITY] Broadcasting: tool={tool} source={source} has_result={parsed_result is not None} result_type={type(parsed_result).__name__} subs={len(_activity_subscribers)} preview={result_preview}")
    entry = {
        "tool": tool,
        "category": cat,
        "args": args or {},
        "result": parsed_result,
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

# Pending external tool calls — maps JSON-RPC id → {tool, args, start}
# Populated by mcp_message_proxy, resolved by mcp_sse_proxy when the
# capsule sends the result back on the SSE stream.
_pending_external_calls: dict[str | int, dict] = {}

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

# Prevent HF Spaces CDN from caching static JS/HTML files
from starlette.middleware.base import BaseHTTPMiddleware
class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") and not request.url.path.endswith(".min.js"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
app.add_middleware(NoCacheStaticMiddleware)


# --- API Routes ---

def _normalize_workflow_nodes(definition: str) -> str:
    """Ensure workflow node definitions have both 'tool' and 'tool_name' fields.

    The capsule executor expects 'tool_name' on tool nodes, but the capsule's
    storage layer normalises 'tool_name' → 'tool'.  By injecting both fields
    before the definition reaches the capsule we guarantee the executor can
    find what it needs regardless of which field survives storage.

    Also normalises node type 'tool_call' → 'tool' (the executor only knows 'tool').
    """
    try:
        defn = json.loads(definition) if isinstance(definition, str) else definition
        nodes = defn.get("nodes", [])
        changed = False
        for node in nodes:
            # Normalise type
            if node.get("type") == "tool_call":
                node["type"] = "tool"
                changed = True
            # Ensure both tool and tool_name exist
            t = node.get("tool_name") or node.get("tool")
            if t:
                if "tool_name" not in node:
                    node["tool_name"] = t
                    changed = True
                if "tool" not in node:
                    node["tool"] = t
                    changed = True
        if changed:
            return json.dumps(defn)
        return definition if isinstance(definition, str) else json.dumps(definition)
    except Exception:
        return definition if isinstance(definition, str) else json.dumps(definition)


@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Normalise workflow definitions before they reach the capsule
    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        body["definition"] = _normalize_workflow_nodes(body["definition"])

    source = request.headers.get("x-source", "webui")
    start = time.time()
    result = await _call_tool(tool_name, body)
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    # Tag hydration calls so the frontend SSE listener can filter them
    _broadcast_activity(tool_name, body, result.get("result"), duration_ms, error_str, source=source)
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
    """SSE stream of tool call activity for the web UI Activity tab.
    Only streams LIVE events — no history replay to avoid spam on connect."""
    q = asyncio.Queue(maxsize=100)
    _activity_subscribers.append(q)

    async def _stream():
        try:
            while True:
                entry = await q.get()
                try:
                    payload = json.dumps(entry)
                except (TypeError, ValueError) as e:
                    # Fallback: strip non-serializable result and log
                    print(f"[ACTIVITY-SSE] JSON serialize error for {entry.get('tool', '?')}: {e}")
                    entry_safe = {k: v for k, v in entry.items() if k != 'result'}
                    entry_safe['result'] = {'_serialization_error': str(e)}
                    payload = json.dumps(entry_safe)
                yield f"data: {payload}\n\n"
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
    content = Path("static/panel.html").read_text()
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })


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
                    _current_event_type = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        # Process complete lines
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)

                            # Track SSE event type for parsing
                            if line.startswith("event:"):
                                _current_event_type = line.split(":", 1)[1].strip()

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
                                # ── Intercept JSON-RPC responses to capture tool results ──
                                # MCP SSE transport sends bare data: lines (no event: prefix),
                                # so we check ANY data line when we have pending calls.
                                if line.startswith("data:") and _pending_external_calls:
                                    raw_data = line.split("data:", 1)[1].strip()
                                    print(f"[MCP-PROXY] SSE data line, event_type='{_current_event_type}', pending={len(_pending_external_calls)}, data={raw_data[:120]}")
                                    try:
                                        payload = json.loads(raw_data)
                                        rpc_id = payload.get("id")
                                        # Try exact match first, then coerced match (int vs str)
                                        matched_key = None
                                        if rpc_id is not None:
                                            if rpc_id in _pending_external_calls:
                                                matched_key = rpc_id
                                            elif str(rpc_id) in _pending_external_calls:
                                                matched_key = str(rpc_id)
                                            elif isinstance(rpc_id, str) and rpc_id.isdigit() and int(rpc_id) in _pending_external_calls:
                                                matched_key = int(rpc_id)
                                        if matched_key is not None:
                                            pending = _pending_external_calls.pop(matched_key)
                                            duration_ms = int((time.time() - pending["start"]) * 1000)
                                            rpc_result = payload.get("result")
                                            rpc_error = payload.get("error")
                                            error_str = None
                                            if rpc_error:
                                                error_str = rpc_error.get("message", str(rpc_error)) if isinstance(rpc_error, dict) else str(rpc_error)
                                            print(f"[MCP-PROXY] ✓ Matched pending call id={rpc_id} tool={pending['tool']} duration={duration_ms}ms has_result={rpc_result is not None}")
                                            _broadcast_activity(
                                                pending["tool"], pending["args"],
                                                rpc_result, duration_ms, error_str,
                                                source="external"
                                            )
                                        elif rpc_id is not None:
                                            print(f"[MCP-PROXY] SSE response id={rpc_id} (type={type(rpc_id).__name__}) not in pending keys={list(_pending_external_calls.keys())}")
                                    except (json.JSONDecodeError, AttributeError):
                                        pass

                                yield line + "\n"
        except httpx.RemoteProtocolError:
            pass
        except Exception as e:
            print(f"[MCP-PROXY] SSE stream error: {e}")
            yield f"event: error\ndata: {e}\n\n"
        finally:
            # Clean up any pending calls for this SSE session (stale after disconnect)
            stale_ids = [k for k, v in _pending_external_calls.items()
                         if time.time() - v["start"] > 300]
            for k in stale_ids:
                _pending_external_calls.pop(k, None)

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
        # Normalise workflow definitions in MCP JSON-RPC calls before forwarding
        if rpc_tool in ("workflow_create", "workflow_update"):
            try:
                rpc_body = json.loads(body)
                params = rpc_body.get("params", {})
                args = params.get("arguments", {})
                if "definition" in args:
                    args["definition"] = _normalize_workflow_nodes(args["definition"])
                    rpc_body["params"]["arguments"] = args
                    body = json.dumps(rpc_body).encode()
            except Exception as e:
                print(f"[MCP-PROXY] workflow normalisation skipped: {e}")

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
                if resp.status_code in (202, 204):
                    # SSE protocol: result comes on the SSE stream, not here.
                    # Store as pending — mcp_sse_proxy will resolve it with real data.
                    rpc_id = None
                    try:
                        rpc_id = json.loads(body).get("id")
                    except Exception:
                        pass
                    if rpc_id is not None:
                        _pending_external_calls[rpc_id] = {
                            "tool": rpc_tool,
                            "args": rpc_args,
                            "start": start,
                        }
                        print(f"[MCP-PROXY] Stored pending call id={rpc_id} (type={type(rpc_id).__name__}) tool={rpc_tool}")
                    else:
                        # No id to match — broadcast now with null result
                        _broadcast_activity(rpc_tool, rpc_args, None, duration_ms, None, source="external")
                elif resp.status_code == 200:
                    # Got inline JSON response — broadcast with result
                    resp_result = None
                    try:
                        resp_json = resp.json()
                        resp_result = resp_json.get("result")
                    except Exception:
                        pass
                    _broadcast_activity(rpc_tool, rpc_args, resp_result, duration_ms, None, source="external")
                else:
                    _broadcast_activity(rpc_tool, rpc_args, None, duration_ms, f"HTTP {resp.status_code}", source="external")

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
