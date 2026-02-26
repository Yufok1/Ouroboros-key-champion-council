"""
Champion Council Self-Deploy — Local Standalone Backend

Architecture:
  1) (Optional) local capsule process: champion_gen8.py serving MCP/SSE on MCP_PORT
  2) FastAPI proxy on APP_PORT for web panel + MCP reverse proxy
  3) Activity feed and persistence management (local-first, optional HF sync)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if __package__ in (None, ""):
    import sys

    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.activity import ActivityHub
    from backend.capsule_manager import CapsuleManager
    from backend.dreamer_routes import create_dreamer_router
    from backend.mcp_client import MCPClient
    from backend.mcp_proxy import (
        PendingCallRegistry,
        normalize_rpc_payload,
        normalize_rpc_workflow,
        parse_rpc_tool_calls,
    )
    from backend.persistence import PersistenceManager
    from backend.postprocessing import normalize_workflow_nodes, postprocess_tool_result
    from backend.settings import load_settings
    from backend.vast_routes import create_vast_router
else:
    from .activity import ActivityHub
    from .capsule_manager import CapsuleManager
    from .dreamer_routes import create_dreamer_router
    from .mcp_client import MCPClient
    from .mcp_proxy import (
        PendingCallRegistry,
        normalize_rpc_payload,
        normalize_rpc_workflow,
        parse_rpc_tool_calls,
    )
    from .persistence import PersistenceManager
    from .postprocessing import normalize_workflow_nodes, postprocess_tool_result
    from .settings import load_settings
    from .vast_routes import create_vast_router


settings = load_settings()

_manage_local_capsule = os.environ.get("MANAGE_LOCAL_CAPSULE", "1").lower() not in ("0", "false", "no")
_local_default_mcp = f"http://127.0.0.1:{settings.mcp_port}"

capsule_manager = CapsuleManager(
    capsule_path=settings.capsule_path,
    capsule_gz_path=settings.capsule_gz_path,
    capsule_bootstrap_gz_path=settings.capsule_bootstrap_gz_path,
    mcp_port=settings.mcp_port,
    capsule_download_url=settings.capsule_download_url,
)
mcp_client = MCPClient(settings.mcp_base_url)
activity_hub = ActivityHub(max_entries=settings.activity_log_max)
pending_calls = PendingCallRegistry()

persistence = PersistenceManager(
    mode=settings.persistence_mode,
    data_dir=settings.data_dir,
    hf_token=settings.hf_token,
    space_author_name=settings.space_author_name,
    space_id=settings.space_id,
    save_cooldown=settings.save_cooldown,
)


def _normalize_activity_source(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().lower()
    if v in ("external", "webui", "hydration", "extension", "action", "api"):
        return v
    return None


def _infer_activity_source(request: Request, fallback: str = "webui") -> str:
    explicit = _normalize_activity_source(
        request.headers.get("x-source") or request.query_params.get("source")
    )
    if explicit:
        return explicit

    ua = (request.headers.get("user-agent") or "").lower()
    if "chatgpt" in ua or "openai" in ua:
        return "external"

    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    if not origin and not referer:
        return "external"

    return fallback


async def _call_tool(name: str, arguments: dict) -> dict:
    return await mcp_client.call_tool(name, arguments)


async def _list_tools() -> dict:
    return await mcp_client.list_tools()


@asynccontextmanager
async def lifespan(_: FastAPI):
    started_capsule = False

    # Startup
    if _manage_local_capsule and settings.mcp_base_url == _local_default_mcp:
        if capsule_manager.start():
            started_capsule = True
            await capsule_manager.wait_for_sse(timeout=90)

    await mcp_client.connect()

    if persistence.is_available():
        restored = await persistence.restore_state(_call_tool)
        print(f"[INIT] persistence restore {'applied' if restored else 'skipped/empty'}")
        persistence.start_autosave(_call_tool, interval=settings.autosave_interval)
    else:
        print("[INIT] persistence disabled by configuration")

    try:
        yield
    finally:
        # Shutdown
        if persistence.is_available():
            saved = await persistence.save_state(_call_tool, force=True)
            print(f"[SHUTDOWN] persistence save {'completed' if saved else 'skipped/failed'}")
            persistence.stop_autosave()

        await mcp_client.disconnect()

        if started_capsule:
            capsule_manager.stop()


app = FastAPI(title="Champion Council Self-Deploy", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") and not request.url.path.endswith(".min.js"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheStaticMiddleware)


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        body["definition"] = normalize_workflow_nodes(body["definition"])

    body_source = _normalize_activity_source(body.pop("__source", None) if isinstance(body, dict) else None)
    source = body_source or _infer_activity_source(request, fallback="webui")
    start = time.time()

    result = await _call_tool(tool_name, body)
    result = await postprocess_tool_result(tool_name, body, result, _call_tool)

    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    activity_hub.add_entry(
        tool=tool_name,
        args=body,
        result=result.get("result"),
        duration_ms=duration_ms,
        error=error_str,
        source=source,
    )

    if error_str:
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/tools")
async def list_tools_route(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    start = time.time()
    result = await _list_tools()
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    activity_hub.add_entry(
        tool="list_tools",
        args={},
        result=result.get("result"),
        duration_ms=duration_ms,
        error=error_str,
        source=source,
    )
    if "error" in result and isinstance(result.get("error"), str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/health")
async def health():
    latest_event_id = activity_hub.log[-1].get("eventId") if activity_hub.log else None
    return {
        "status": "ok",
        "version": "0.1.0",
        "env": settings.app_env,
        "timestamp": datetime.utcnow().isoformat(),
        "app_port": settings.app_port,
        "mcp_port": settings.mcp_port,
        "capsule_running": capsule_manager.is_running,
        "capsule_pid": capsule_manager.pid,
        "mcp_base_url": settings.mcp_base_url,
        "mcp_session": mcp_client.connected,
        "mcp_reconnect": mcp_client.reconnect_state,
        "persistence": persistence.status(),
        "activity_session_id": activity_hub.session_id,
        "activity_latest_event_id": latest_event_id,
    }


@app.get("/api/capsule-log")
async def capsule_log():
    return {"lines": capsule_manager.tail(100)}


@app.post("/api/capsule/restart")
async def capsule_restart():
    if not _manage_local_capsule or settings.mcp_base_url != _local_default_mcp:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Capsule restart only available when MANAGE_LOCAL_CAPSULE=1 and MCP_BASE_URL is local",
                "manage_local_capsule": _manage_local_capsule,
                "mcp_base_url": settings.mcp_base_url,
            },
        )

    restarted = capsule_manager.restart()
    if not restarted:
        return JSONResponse(status_code=500, content={"error": "Failed to restart capsule process"})

    await mcp_client.disconnect()
    ready = await capsule_manager.wait_for_sse(timeout=90)
    connected = await mcp_client.connect(force=True) if ready else False

    return {
        "status": "ok" if (restarted and ready and connected) else "degraded",
        "capsule_running": capsule_manager.is_running,
        "capsule_pid": capsule_manager.pid,
        "mcp_ready": connected,
    }


# ---------------------------------------------------------------------------
# Persistence routes
# ---------------------------------------------------------------------------


@app.post("/api/persist/save")
async def persist_save():
    if not persistence.is_available():
        return JSONResponse(status_code=503, content={"error": "Persistence not configured"})

    ok = await persistence.save_state(_call_tool, force=True)
    return {"status": "saved" if ok else "failed"}


@app.post("/api/persist/restore")
async def persist_restore():
    if not persistence.is_available():
        return JSONResponse(status_code=503, content={"error": "Persistence not configured"})

    ok = await persistence.restore_state(_call_tool)
    return {"status": "restored" if ok else "failed"}


@app.get("/api/persist/status")
async def persist_status():
    return persistence.status()


# ---------------------------------------------------------------------------
# Activity routes
# ---------------------------------------------------------------------------


@app.get("/api/activity-stream")
async def activity_stream(request: Request, since: str | None = None):
    def _coerce_event_id(value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None

    def _encode_activity_entry(entry: dict) -> str:
        try:
            payload = json.dumps(entry)
        except (TypeError, ValueError) as exc:
            entry_safe = {k: v for k, v in entry.items() if k != "result"}
            entry_safe["result"] = {"_serialization_error": str(exc)}
            payload = json.dumps(entry_safe)

        event_id = entry.get("eventId")
        if event_id is not None:
            return f"id: {event_id}\ndata: {payload}\n\n"
        return f"data: {payload}\n\n"

    last_event_id = request.headers.get("last-event-id")
    resume_after = _coerce_event_id(since if since is not None else last_event_id)
    latest_known_id = (
        _coerce_event_id(activity_hub.log[-1].get("eventId"))
        if activity_hub.log
        else None
    )

    # If the client asks to resume beyond our newest event ID, this backend
    # likely restarted and reset event IDs. Fall back to fresh streaming so
    # new events are not permanently filtered out.
    stale_resume = resume_after is not None and (
        latest_known_id is None or resume_after > latest_known_id
    )

    if stale_resume:
        replay = activity_hub.recent(limit=500)
        replay_tail_id = _coerce_event_id(replay[-1].get("eventId")) if replay else None
    else:
        replay = activity_hub.recent_since(resume_after, limit=1000) if resume_after is not None else []
        replay_tail_id = _coerce_event_id(replay[-1].get("eventId")) if replay else resume_after
    q = activity_hub.subscribe(maxsize=500)

    async def _stream():
        try:
            for entry in replay:
                if await request.is_disconnected():
                    break
                yield _encode_activity_entry(entry)

            async for chunk in activity_hub.stream(q, after_event_id=replay_tail_id):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            activity_hub.unsubscribe(q)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Activity-Session-Id": activity_hub.session_id,
        },
    )


@app.get("/api/activity-log")
async def activity_log_route(limit: int = 100):
    limit = min(max(limit, 1), 1000)
    entries = activity_hub.recent(limit)
    latest_event_id = entries[-1].get("eventId") if entries else None
    return {
        "entries": entries,
        "sessionId": activity_hub.session_id,
        "latestEventId": latest_event_id,
    }


# ---------------------------------------------------------------------------
# Web panel routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def landing():
    return (settings.frontend_dir / "index.html").read_text(encoding="utf-8")


@app.get("/panel", response_class=HTMLResponse)
async def panel():
    content = (settings.frontend_dir / "panel.html").read_text(encoding="utf-8")
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ---------------------------------------------------------------------------
# MCP SSE reverse proxy routes
# ---------------------------------------------------------------------------


@app.get("/mcp/sse")
async def mcp_sse_proxy(request: Request):
    """Expose capsule MCP/SSE to external clients (IDEs) via local backend."""

    # Build public base URL from incoming request headers.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", request.url.netloc)
    public_base = f"{proto}://{host}"

    async def _stream():
        endpoint_rewritten = False
        upstream_session_id: str | None = None
        event_data_lines: list[str] = []

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", f"{settings.mcp_base_url}/sse", timeout=None) as resp:
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.rstrip("\r")

                            if (not endpoint_rewritten) and line.startswith("data:") and "/messages" in line:
                                raw = line.split("data:", 1)[1].strip()

                                if raw.startswith("http://") or raw.startswith("https://"):
                                    parsed = urlparse(raw)
                                    path_and_query = parsed.path
                                    if parsed.query:
                                        path_and_query += "?" + parsed.query
                                    upstream_session_id = parse_qs(parsed.query).get("session_id", [None])[0]
                                else:
                                    path_and_query = raw
                                    parsed_local = urlparse(path_and_query)
                                    upstream_session_id = parse_qs(parsed_local.query).get("session_id", [None])[0]

                                if not path_and_query.startswith("/"):
                                    path_and_query = "/" + path_and_query

                                rewritten = f"data: {public_base}/mcp{path_and_query}"
                                endpoint_rewritten = True
                                yield rewritten + "\n"
                                continue

                            if line.startswith("data:"):
                                event_data_lines.append(line.split("data:", 1)[1].lstrip())
                            elif line == "":
                                # Intercept completed SSE event payload (supports multi-line data: blocks)
                                if event_data_lines and pending_calls.has_pending(upstream_session_id):
                                    raw_data = "\n".join(event_data_lines).strip()
                                    try:
                                        payload = json.loads(raw_data)
                                        payload_items = payload if isinstance(payload, list) else [payload]

                                        for item in payload_items:
                                            if not isinstance(item, dict):
                                                continue

                                            rpc_id = item.get("id")
                                            pending = pending_calls.pop(upstream_session_id, rpc_id)
                                            if not pending:
                                                continue

                                            duration_ms = int((time.time() - pending.start) * 1000)
                                            rpc_result = item.get("result")
                                            rpc_error = item.get("error")
                                            error_str = None
                                            if rpc_error:
                                                error_str = (
                                                    rpc_error.get("message", str(rpc_error))
                                                    if isinstance(rpc_error, dict)
                                                    else str(rpc_error)
                                                )

                                            activity_hub.add_entry(
                                                tool=pending.tool,
                                                args=pending.args,
                                                result=rpc_result,
                                                duration_ms=duration_ms,
                                                error=error_str,
                                                source="external",
                                            )
                                    except (json.JSONDecodeError, AttributeError, TypeError):
                                        pass
                                event_data_lines = []

                            yield line + "\n"
        except httpx.RemoteProtocolError:
            pass
        except Exception as exc:
            yield f"event: error\ndata: {exc}\n\n"
        finally:
            pending_calls.cleanup(stale_after_seconds=300)

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
@app.post("/mcp/messages")
@app.post("/mcp/messages/")
async def mcp_message_proxy(request: Request):
    session_id = request.query_params.get("session_id", "")
    body = await request.body()
    body = normalize_rpc_payload(body)
    content_type = request.headers.get("content-type", "application/json")

    _, rpc_calls_raw = parse_rpc_tool_calls(body)
    rpc_calls = [
        {"tool": tool, "args": args, "rpc_id": rpc_id}
        for tool, args, rpc_id in rpc_calls_raw
    ]
    body = normalize_rpc_workflow(body, normalize_workflow_nodes)

    start = time.time()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.mcp_base_url}/messages/",
                params={"session_id": session_id},
                content=body,
                headers={"Content-Type": content_type},
                timeout=120,
            )

        duration_ms = int((time.time() - start) * 1000)

        if rpc_calls:
            if resp.status_code in (202, 204):
                for call in rpc_calls:
                    rpc_id = call["rpc_id"]
                    if rpc_id is not None:
                        pending_calls.store(session_id, rpc_id, call["tool"], call["args"], start)
                    else:
                        # Notifications (no JSON-RPC id) cannot be matched on SSE response.
                        activity_hub.add_entry(
                            call["tool"],
                            call["args"],
                            None,
                            duration_ms,
                            None,
                            source="external",
                        )
            elif resp.status_code == 200:
                response_items: list[dict] = []
                try:
                    resp_json = resp.json()
                    if isinstance(resp_json, dict):
                        response_items = [resp_json]
                    elif isinstance(resp_json, list):
                        response_items = [item for item in resp_json if isinstance(item, dict)]
                except Exception:
                    response_items = []

                unmatched_calls = list(rpc_calls)

                def _pop_call_for_id(rpc_id: str | int | None) -> dict | None:
                    if rpc_id is None:
                        return None

                    for i, call in enumerate(unmatched_calls):
                        cid = call.get("rpc_id")
                        if cid == rpc_id or str(cid) == str(rpc_id):
                            return unmatched_calls.pop(i)
                    return None

                for item in response_items:
                    call = _pop_call_for_id(item.get("id"))
                    if call is None and len(unmatched_calls) == 1:
                        # Some capsules omit JSON-RPC id on single-call responses.
                        call = unmatched_calls.pop(0)
                    if call is None:
                        continue

                    rpc_error = item.get("error")
                    error_str = None
                    if rpc_error is not None:
                        if isinstance(rpc_error, dict):
                            error_str = rpc_error.get("message", str(rpc_error))
                        else:
                            error_str = str(rpc_error)

                    activity_hub.add_entry(
                        call["tool"],
                        call["args"],
                        item.get("result"),
                        duration_ms,
                        error_str,
                        source="external",
                    )

                for call in unmatched_calls:
                    error_str = "Missing JSON-RPC result"
                    if call.get("rpc_id") is None:
                        error_str = None
                    activity_hub.add_entry(
                        call["tool"],
                        call["args"],
                        None,
                        duration_ms,
                        error_str,
                        source="external",
                    )
            else:
                for call in rpc_calls:
                    activity_hub.add_entry(
                        call["tool"],
                        call["args"],
                        None,
                        duration_ms,
                        f"HTTP {resp.status_code}",
                        source="external",
                    )

        if resp.status_code in (202, 204):
            return Response(status_code=resp.status_code)

        if resp.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

        return JSONResponse(content={"raw": resp.text} if resp.text else {}, status_code=resp.status_code)

    except httpx.ReadTimeout:
        duration_ms = int((time.time() - start) * 1000)
        for call in rpc_calls:
            activity_hub.add_entry(
                call["tool"],
                call["args"],
                None,
                duration_ms,
                "Capsule timeout",
                source="external",
            )
        return JSONResponse(status_code=504, content={"error": "Capsule timeout"})
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        for call in rpc_calls:
            activity_hub.add_entry(
                call["tool"],
                call["args"],
                None,
                duration_ms,
                str(exc),
                source="external",
            )
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.post("/mcp/sse")
async def mcp_sse_post_fallback(_: Request):
    return JSONResponse(
        status_code=405,
        content={"error": "Use GET for SSE transport"},
        headers={"Allow": "GET"},
    )


# Mount after explicit routes.
app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")

# Compatibility alias for resources some clients may request.
app.mount("/media", StaticFiles(directory=str(settings.frontend_dir)), name="media")

# Register route groups.
app.include_router(create_dreamer_router(_call_tool))
app.include_router(create_vast_router(_call_tool, activity_hub))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.app_port)
