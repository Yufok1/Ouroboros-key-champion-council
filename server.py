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
import shutil
import threading
import mimetypes
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from mcp import ClientSession
from mcp.client.sse import sse_client

import time
import persistence

# Ensure Starlette static serving emits correct MIME for audio container files.
mimetypes.add_type("audio/mp4", ".m4a")

# Tools that are internal plumbing — don't broadcast to activity feed
_SILENT_TOOLS = frozenset([
    'get_status', 'list_slots', 'bag_catalog', 'workflow_list',
    'verify_integrity', 'get_cached', 'get_identity', 'feed',
    'get_capabilities', 'get_help', 'get_onboarding', 'get_quickstart',
    'hub_tasks', 'list_tools', 'heartbeat', 'api_health',
])


def _normalize_activity_source(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip().lower()
    if v in ("external", "webui", "hydration", "extension", "action", "api"):
        return v
    return None


def _is_same_origin_request(url_value: str, request: Request) -> bool:
    try:
        parsed = urlparse(url_value)
        if not parsed.netloc:
            return False
        req_host = (request.headers.get("host") or "").strip().lower()
        url_host = parsed.netloc.strip().lower()
        return bool(req_host) and req_host == url_host
    except Exception:
        return False


def _infer_activity_source(request: Request, fallback: str = "webui") -> str:
    # Explicit override from header/query wins.
    explicit = _normalize_activity_source(
        request.headers.get("x-source") or request.query_params.get("source")
    )
    if explicit:
        return explicit

    ua = (request.headers.get("user-agent") or "").lower()
    if "chatgpt" in ua or "openai" in ua:
        return "external"

    # Cross-origin traffic (e.g., ChatGPT Actions) should be external.
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    if origin and not _is_same_origin_request(origin, request):
        return "external"
    if referer and not _is_same_origin_request(referer, request):
        return "external"
    if not origin and not referer:
        return "external"

    return fallback


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


def _normalize_vast_instances(payload) -> list[dict]:
    """Normalize vast_instances payloads to a list of instance dicts."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("instances", "data", "results", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        if any(k in payload for k in ("id", "instance_id", "ssh_host", "ssh_port", "gpu", "gpu_name", "public_ip")):
            return [payload]
    return []


def _ssh_key_paths() -> tuple[Path, Path, Path]:
    ssh_dir = Path.home() / ".ssh"
    return ssh_dir, ssh_dir / "id_rsa", ssh_dir / "id_rsa.pub"


def _ssh_bootstrap_status() -> dict:
    ssh_dir, private_key, public_key = _ssh_key_paths()
    return {
        "dir": str(ssh_dir),
        "private_key": private_key.exists(),
        "public_key": public_key.exists(),
    }


def _write_ssh_file(path: Path, value: str, mode: int) -> bool:
    content = (value or "").strip()
    if not content:
        return False
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    return True


def _ensure_vast_ssh_keys() -> None:
    """Ensure ~/.ssh/id_rsa exists for Vast tools that require SSH identity."""
    ssh_dir, private_key, public_key = _ssh_key_paths()
    try:
        ssh_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[WARN] Failed to create SSH directory {ssh_dir}: {e}")
        return
    try:
        os.chmod(ssh_dir, 0o700)
    except OSError:
        pass

    private_secret = os.environ.get("SSH_PRIVATE_KEY", "")
    public_secret = os.environ.get("SSH_PUBLIC_KEY", "")

    secret_loaded = False
    if private_secret:
        secret_loaded = _write_ssh_file(private_key, private_secret, 0o600)
        if public_secret:
            _write_ssh_file(public_key, public_secret, 0o644)
        if secret_loaded:
            print("[INIT] Loaded SSH private key from SSH_PRIVATE_KEY")

    if not private_key.exists():
        ssh_keygen = shutil.which("ssh-keygen")
        if ssh_keygen:
            try:
                subprocess.run(
                    [ssh_keygen, "-t", "rsa", "-b", "4096", "-N", "", "-f", str(private_key)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                print("[INIT] Generated ~/.ssh/id_rsa for Vast remote tools")
            except Exception as e:
                print(f"[WARN] Failed to generate ~/.ssh/id_rsa: {e}")
        elif not secret_loaded:
            print("[WARN] ssh-keygen not found and SSH_PRIVATE_KEY is not set; Vast SSH tools may fail")

    if private_key.exists():
        try:
            os.chmod(private_key, 0o600)
        except OSError:
            pass

    # Derive public key from private key when possible.
    if private_key.exists() and not public_key.exists():
        ssh_keygen = shutil.which("ssh-keygen")
        if ssh_keygen:
            try:
                derived = subprocess.run(
                    [ssh_keygen, "-y", "-f", str(private_key)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                _write_ssh_file(public_key, derived.stdout, 0o644)
            except Exception:
                pass
    if public_key.exists():
        try:
            os.chmod(public_key, 0o644)
        except OSError:
            pass


_capacity_cache = {"data": None, "ts": 0.0}
_CAPACITY_CACHE_TTL_SECONDS = 3.0
_CAPACITY_GUARD_TOOLS = frozenset({"plug_model", "hub_plug"})
_CAPACITY_GUARD_ENABLED = os.environ.get("CAPACITY_GUARD_ENABLED", "1").strip().lower() not in ("0", "false", "no")
_CAPACITY_GUARD_MODE = os.environ.get("CAPACITY_GUARD_MODE", "enforce").strip().lower()  # enforce|warn
_CAPACITY_RAM_BLOCK_PCT = float(os.environ.get("CAPACITY_RAM_BLOCK_PCT", "92"))
_CAPACITY_GPU_FREE_MIN_GB = float(os.environ.get("CAPACITY_GPU_FREE_MIN_GB", "2"))


def _bytes_to_gb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024.0 ** 3), 3)


def _read_int_file(path: str) -> int | None:
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not raw or raw == "max":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _host_memory_snapshot() -> dict:
    total_bytes = None
    avail_bytes = None
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        total_bytes = int(page_size * phys_pages)
        avail_bytes = int(page_size * avail_pages)
    except Exception:
        meminfo = {}
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                key, rest = parts[0].strip(), parts[1].strip().split()
                if not rest:
                    continue
                meminfo[key] = int(rest[0]) * 1024
        except Exception:
            meminfo = {}
        total_bytes = meminfo.get("MemTotal")
        avail_bytes = meminfo.get("MemAvailable") or meminfo.get("MemFree")

    cgroup_limit = _read_int_file("/sys/fs/cgroup/memory.max") or _read_int_file("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    cgroup_used = _read_int_file("/sys/fs/cgroup/memory.current") or _read_int_file("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if cgroup_limit and cgroup_limit >= (1 << 60):
        cgroup_limit = None

    effective_total = total_bytes
    if cgroup_limit and cgroup_limit > 0:
        effective_total = min(total_bytes, cgroup_limit) if total_bytes else cgroup_limit

    if effective_total is None:
        return {
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "used_percent": None,
            "cgroup_limit_bytes": cgroup_limit,
        }

    if cgroup_used is not None:
        used_bytes = max(0, min(int(cgroup_used), int(effective_total)))
        free_bytes = max(int(effective_total) - used_bytes, 0)
    elif total_bytes and avail_bytes is not None:
        host_used = max(int(total_bytes) - int(avail_bytes), 0)
        used_bytes = max(0, min(host_used, int(effective_total)))
        free_bytes = max(int(effective_total) - used_bytes, 0)
    else:
        used_bytes = None
        free_bytes = None

    used_pct = round((used_bytes / effective_total) * 100.0, 2) if used_bytes is not None and effective_total else None
    return {
        "total_bytes": int(effective_total),
        "used_bytes": int(used_bytes) if used_bytes is not None else None,
        "free_bytes": int(free_bytes) if free_bytes is not None else None,
        "used_percent": used_pct,
        "cgroup_limit_bytes": cgroup_limit,
    }


def _gpu_snapshot() -> dict:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {
            "available": False,
            "provider": "none",
            "count": 0,
            "total_gb": None,
            "used_gb": None,
            "free_gb": None,
            "utilization_pct": None,
        }
    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
    except Exception:
        return {
            "available": False,
            "provider": "nvidia-smi",
            "count": 0,
            "total_gb": None,
            "used_gb": None,
            "free_gb": None,
            "utilization_pct": None,
        }

    total_mb = 0.0
    used_mb = 0.0
    free_mb = 0.0
    util_values = []
    gpu_names = []
    for line in (proc.stdout or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpu_names.append(parts[0])
        try:
            total_mb += float(parts[1])
            used_mb += float(parts[2])
            free_mb += float(parts[3])
            util_values.append(float(parts[4]))
        except (TypeError, ValueError):
            continue

    if total_mb <= 0:
        return {
            "available": False,
            "provider": "nvidia-smi",
            "count": 0,
            "total_gb": None,
            "used_gb": None,
            "free_gb": None,
            "utilization_pct": None,
        }

    util_avg = round(sum(util_values) / len(util_values), 2) if util_values else None
    return {
        "available": True,
        "provider": "nvidia-smi",
        "count": len(gpu_names),
        "names": gpu_names,
        "total_gb": round(total_mb / 1024.0, 3),
        "used_gb": round(used_mb / 1024.0, 3),
        "free_gb": round(free_mb / 1024.0, 3),
        "utilization_pct": util_avg,
    }


def _runtime_capacity_snapshot(force: bool = False) -> dict:
    now = time.time()
    if not force and _capacity_cache["data"] and (now - _capacity_cache["ts"]) < _CAPACITY_CACHE_TTL_SECONDS:
        return _capacity_cache["data"]

    mem = _host_memory_snapshot()
    gpu = _gpu_snapshot()
    disk = shutil.disk_usage("/")
    try:
        load1 = round(os.getloadavg()[0], 3)
    except Exception:
        load1 = None

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "runtime": "huggingface_space",
        "space": {
            "space_id": os.environ.get("SPACE_ID", ""),
            "space_author_name": os.environ.get("SPACE_AUTHOR_NAME", ""),
            "memory_env": os.environ.get("MEMORY", ""),
            "cpu_cores_env": os.environ.get("CPU_CORES", ""),
            "hardware_env": os.environ.get("HARDWARE", ""),
        },
        "memory": {
            **mem,
            "total_gb": _bytes_to_gb(mem.get("total_bytes")),
            "used_gb": _bytes_to_gb(mem.get("used_bytes")),
            "free_gb": _bytes_to_gb(mem.get("free_bytes")),
        },
        "gpu": gpu,
        "cpu": {
            "cores": os.cpu_count(),
            "load1": load1,
        },
        "disk": {
            "total_gb": _bytes_to_gb(disk.total),
            "used_gb": _bytes_to_gb(disk.used),
            "free_gb": _bytes_to_gb(disk.free),
        },
        "guard": {
            "enabled": _CAPACITY_GUARD_ENABLED,
            "mode": _CAPACITY_GUARD_MODE,
            "tools": sorted(_CAPACITY_GUARD_TOOLS),
            "ram_block_pct": _CAPACITY_RAM_BLOCK_PCT,
            "gpu_free_min_gb": _CAPACITY_GPU_FREE_MIN_GB,
        },
    }

    _capacity_cache["data"] = payload
    _capacity_cache["ts"] = now
    return payload


def _capacity_guard_decision(tool_name: str, args: dict, snapshot: dict) -> dict:
    decision = {
        "tool": tool_name,
        "enabled": _CAPACITY_GUARD_ENABLED,
        "mode": _CAPACITY_GUARD_MODE,
        "action": "allow",
        "reasons": [],
        "bypassed": False,
    }
    if tool_name not in _CAPACITY_GUARD_TOOLS or not _CAPACITY_GUARD_ENABLED:
        return decision
    if isinstance(args, dict) and bool(args.get("allow_oom_risk")):
        decision["bypassed"] = True
        return decision

    mem = snapshot.get("memory", {}) if isinstance(snapshot, dict) else {}
    gpu = snapshot.get("gpu", {}) if isinstance(snapshot, dict) else {}

    used_pct = mem.get("used_percent")
    if isinstance(used_pct, (int, float)) and used_pct >= _CAPACITY_RAM_BLOCK_PCT:
        decision["reasons"].append(
            f"RAM pressure {used_pct:.2f}% >= {_CAPACITY_RAM_BLOCK_PCT:.2f}%"
        )

    gpu_available = bool(gpu.get("available"))
    gpu_free_gb = gpu.get("free_gb")
    if gpu_available and isinstance(gpu_free_gb, (int, float)) and gpu_free_gb < _CAPACITY_GPU_FREE_MIN_GB:
        decision["reasons"].append(
            f"GPU free VRAM {gpu_free_gb:.3f}GB < {_CAPACITY_GPU_FREE_MIN_GB:.3f}GB"
        )

    if decision["reasons"]:
        decision["action"] = "block" if _CAPACITY_GUARD_MODE == "enforce" else "warn"
    return decision


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
    _ensure_vast_ssh_keys()

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

                # Restore persisted state from HF dataset repo
                if persistence.is_available():
                    print("[INIT] Restoring persisted state...")
                    await persistence.restore_state(_call_tool)
                    persistence.start_autosave(_call_tool, interval=300)
                else:
                    print("[INIT] Persistence not available (no HF_TOKEN or username)")
            else:
                print("[WARN] MCP connect failed (will retry on first request)")

    yield

    # Shutdown — save state before stopping
    if persistence.is_available():
        print("[SHUTDOWN] Saving state...")
        await persistence.save_state(_call_tool)
        persistence.stop_autosave()

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


def _coerce_tool_arguments(args) -> dict:
    """Coerce MCP tools/call arguments into a JSON object."""
    if isinstance(args, dict):
        return args
    if args is None:
        return {}
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    if isinstance(args, list):
        # Accept [["k","v"], ...] form and convert to an object.
        out = {}
        for item in args:
            if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str):
                out[item[0]] = item[1]
            else:
                return {}
        return out
    return {}


def _normalize_rpc_tool_call_obj(obj: dict) -> bool:
    """Normalize one JSON-RPC tools/call object in-place."""
    if not isinstance(obj, dict) or obj.get("method") != "tools/call":
        return False

    changed = False
    params = obj.get("params", {})
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            params = parsed if isinstance(parsed, dict) else {}
        except Exception:
            params = {}
        changed = True
    elif not isinstance(params, dict):
        params = {}
        changed = True

    if not params.get("name"):
        alias = params.get("tool") or params.get("tool_name")
        if isinstance(alias, str) and alias:
            params["name"] = alias
            changed = True

    if "arguments" not in params:
        if isinstance(params.get("input"), dict):
            params["arguments"] = params.pop("input")
            changed = True
        elif isinstance(params.get("args"), dict):
            params["arguments"] = params.pop("args")
            changed = True
        else:
            params["arguments"] = {}
            changed = True
    else:
        coerced = _coerce_tool_arguments(params.get("arguments"))
        if coerced != params.get("arguments"):
            params["arguments"] = coerced
            changed = True

    tool = params.get("name")
    args = params.get("arguments", {})
    if tool in ("workflow_create", "workflow_update") and isinstance(args, dict) and "definition" in args:
        normalized = _normalize_workflow_nodes(args["definition"])
        if normalized != args["definition"]:
            args = dict(args)
            args["definition"] = normalized
            params["arguments"] = args
            changed = True

    obj["params"] = params
    return changed


def _normalize_mcp_jsonrpc_payload(payload_bytes: bytes) -> bytes:
    """Normalize incoming JSON-RPC payloads for compatibility across clients."""
    try:
        payload = json.loads(payload_bytes)
    except Exception:
        return payload_bytes

    changed = False
    if isinstance(payload, dict):
        changed = _normalize_rpc_tool_call_obj(payload)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and _normalize_rpc_tool_call_obj(item):
                changed = True
    else:
        return payload_bytes

    if not changed:
        return payload_bytes
    return json.dumps(payload).encode("utf-8")


def _parse_rpc_tool_calls(payload_bytes: bytes) -> list[tuple[str, dict, str | int | None]]:
    """Extract tools/call tuples for activity tracking.

    Supports single JSON-RPC objects and batch arrays.
    """
    try:
        payload = json.loads(payload_bytes)
    except Exception:
        return []

    objs = payload if isinstance(payload, list) else [payload]
    calls: list[tuple[str, dict, str | int | None]] = []
    for obj in objs:
        if not isinstance(obj, dict) or obj.get("method") != "tools/call":
            continue
        params = obj.get("params", {})
        if not isinstance(params, dict):
            continue
        tool = params.get("name", "unknown")
        if not isinstance(tool, str) or not tool:
            tool = "unknown"
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            args = {}
        calls.append((tool, args, obj.get("id")))

    return calls


def _is_default_slot_name(name: str) -> bool:
    v = str(name or "").strip().lower()
    if v in ("empty", "vacant"):
        return True
    if v.startswith("slot_") and v[5:].isdigit():
        return True
    if v.startswith("slot-") and v[5:].isdigit():
        return True
    if v.startswith("slot ") and v[5:].isdigit():
        return True
    return False


async def _postprocess_tool_result(tool_name: str, args: dict, result: dict) -> dict:
    """Intercept and fix known capsule issues at the proxy layer.

    This lets us patch bugs without modifying the capsule backend.
    """
    parsed = _parse_mcp_result(result.get("result"))

    # --- Fix get_genesis NoneType crash ---
    if tool_name == "get_genesis":
        error_str = result.get("error", "") or ""
        parsed_str = str(parsed) if parsed else ""
        if "NoneType" in error_str or "NoneType" in parsed_str:
            safe = {"genesis_hash": None, "lineage": [], "note": "Genesis data not initialized for this capsule instance"}
            return {"result": {"content": [{"type": "text", "text": json.dumps(safe)}]}}

    # --- Normalize compact slot summaries into explicit per-slot status ---
    if tool_name in ("list_slots", "council_status") and isinstance(parsed, dict):
        slots = parsed.get("slots")
        all_ids = parsed.get("all_ids")
        total = parsed.get("total")
        if (not isinstance(slots, list) or len(slots) == 0) and isinstance(all_ids, list) and isinstance(total, int) and total > 0:
            enriched_slots = []
            for i in range(total):
                name = all_ids[i] if i < len(all_ids) else f"slot_{i}"
                enriched_slots.append({
                    "index": i,
                    "name": name,
                    "plugged": False,
                    "model_source": None,
                })

            plugged_sum = None
            try:
                plugged_sum = int((((parsed.get("stats") or {}).get("plugged") or {}).get("sum")))
            except Exception:
                plugged_sum = None

            candidate_indices = [i for i, s in enumerate(enriched_slots) if not _is_default_slot_name(s.get("name", ""))]
            if plugged_sum is not None:
                if plugged_sum <= 0:
                    parsed["slots"] = enriched_slots
                    return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
                if plugged_sum > len(candidate_indices):
                    candidate_indices = list(range(total))
            elif len(candidate_indices) == 0:
                candidate_indices = list(range(total))

            if candidate_indices:
                async def _fetch_slot_info(idx: int):
                    info_raw = await _call_tool("slot_info", {"slot": idx})
                    info = _parse_mcp_result(info_raw.get("result")) if isinstance(info_raw, dict) else None
                    return idx, info

                seen = set()
                calls = []
                for idx in candidate_indices:
                    if idx in seen or idx < 0 or idx >= total:
                        continue
                    seen.add(idx)
                    calls.append(_fetch_slot_info(idx))

                infos = await asyncio.gather(*calls, return_exceptions=True) if calls else []
                for item in infos:
                    if isinstance(item, Exception):
                        continue
                    idx, info = item
                    if not isinstance(info, dict):
                        continue

                    slot = enriched_slots[idx]
                    if info.get("name"):
                        slot["name"] = info["name"]
                    is_plugged = bool(info.get("plugged"))
                    slot["plugged"] = is_plugged
                    src = info.get("source") or info.get("model_source")
                    if not src and is_plugged and not _is_default_slot_name(slot.get("name", "")):
                        src = slot.get("name")
                    slot["model_source"] = src if is_plugged else None
                    if info.get("model_type"):
                        slot["model_type"] = info["model_type"]

            parsed["slots"] = enriched_slots
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix compare/debate: retry slots that fail with "System role not supported" ---
    if tool_name in ("compare", "debate") and isinstance(parsed, dict):
        comparisons = parsed.get("comparisons", [])  # compare
        transcript = parsed.get("transcript", [])     # debate
        patched = False

        # Patch compare results
        for entry in comparisons:
            if entry.get("error") == "System role not supported" or (entry.get("status") == "error" and "System role" in str(entry.get("error", ""))):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    retry = await _call_tool("invoke_slot", {
                        "slot": slot_idx,
                        "text": args.get("input_text", ""),
                        "mode": "forward",
                        "max_tokens": 200,
                    })
                    retry_parsed = _parse_mcp_result(retry.get("result"))
                    if retry_parsed and isinstance(retry_parsed, dict) and "output" in retry_parsed:
                        entry["type"] = "generation"
                        entry["output"] = retry_parsed["output"]
                        entry.pop("error", None)
                        entry.pop("status", None)
                        entry["note"] = "retried via forward mode (no system role)"
                        patched = True

        # Patch debate transcript rounds
        for rnd in transcript:
            for entry in rnd.get("entries", []):
                if entry.get("error") == "System role not supported":
                    # For debate, we can't easily retry per-round, so annotate
                    entry["response"] = "[Skipped: model does not support system role in chat template]"
                    entry["type"] = "skipped"
                    entry.pop("error", None)
                    patched = True

        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix orchestra: clean up when consensus averaging fails ---
    if tool_name == "orchestra" and isinstance(parsed, dict):
        outputs = parsed.get("outputs", [])
        if any(o.get("status") == "error" and "unsupported operand" in str(o.get("error", "")) for o in outputs):
            parsed["consensus_mean"] = None
            parsed["divergence"] = None
            parsed["note"] = "Consensus averaging failed — clone outputs are structured dicts, not numeric. Individual clone outputs preserved above."
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    return result


@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Normalise workflow definitions before they reach the capsule
    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        body["definition"] = _normalize_workflow_nodes(body["definition"])

    # Optional reserved body key for callers that can't set headers/query.
    body_source = _normalize_activity_source(body.pop("__source", None) if isinstance(body, dict) else None)
    source = body_source or _infer_activity_source(request, fallback="webui")

    runtime_capacity = None
    capacity_guard = None
    if tool_name in _CAPACITY_GUARD_TOOLS:
        runtime_capacity = _runtime_capacity_snapshot()
        capacity_guard = _capacity_guard_decision(tool_name, body if isinstance(body, dict) else {}, runtime_capacity)
        if capacity_guard.get("action") == "block":
            error_msg = f"Capacity guard blocked {tool_name}"
            payload = {
                "error": error_msg,
                "capacity_guard": capacity_guard,
                "runtime_capacity": runtime_capacity,
            }
            _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, error_msg, source=source)
            return JSONResponse(status_code=429, content=payload)

    start = time.time()
    result = await _call_tool(tool_name, body)
    # Post-process to fix known capsule bugs at proxy layer
    result = await _postprocess_tool_result(tool_name, body, result)
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    # Tag hydration calls so the frontend SSE listener can filter them
    _broadcast_activity(tool_name, body, result.get("result"), duration_ms, error_str, source=source)
    if error_str:
        return JSONResponse(status_code=503, content=result)
    if capacity_guard and isinstance(result, dict):
        result["capacity_guard"] = capacity_guard
    return result


@app.get("/api/tools")
async def list_tools_route(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    start = time.time()
    result = await _list_tools()
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    _broadcast_activity("list_tools", {}, result.get("result"), duration_ms, error_str, source=source)
    if "error" in result and isinstance(result["error"], str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/health")
async def health(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    start = time.time()
    capsule_alive = capsule_process is not None and capsule_process.poll() is None
    payload = {
        "status": "ok",
        "version": "0.8.9",
        "capsule_running": capsule_alive,
        "capsule_pid": capsule_process.pid if capsule_alive else None,
        "mcp_port": MCP_PORT,
        "mcp_session": _mcp_session is not None,
        "persistence": persistence.is_available(),
        "timestamp": datetime.utcnow().isoformat(),
    }
    cap = _runtime_capacity_snapshot()
    payload["runtime_capacity"] = {
        "memory_used_percent": ((cap.get("memory") or {}).get("used_percent")),
        "memory_free_gb": ((cap.get("memory") or {}).get("free_gb")),
        "gpu_available": ((cap.get("gpu") or {}).get("available")),
        "gpu_free_gb": ((cap.get("gpu") or {}).get("free_gb")),
    }
    duration_ms = int((time.time() - start) * 1000)
    _broadcast_activity("api_health", {}, {"content": [{"type": "text", "text": json.dumps(payload)}]}, duration_ms, None, source=source)
    return payload


@app.get("/api/runtime/capacity")
async def runtime_capacity(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    start = time.time()
    payload = _runtime_capacity_snapshot(force=True)
    duration_ms = int((time.time() - start) * 1000)
    _broadcast_activity(
        "api_runtime_capacity",
        {},
        {"content": [{"type": "text", "text": json.dumps(payload)}]},
        duration_ms,
        None,
        source=source,
    )
    return payload


@app.post("/api/persist/save")
async def persist_save():
    """Manually trigger a state save to the HF dataset repo."""
    if not persistence.is_available():
        return JSONResponse(status_code=503, content={"error": "Persistence not available — set HF_TOKEN as a Space secret"})
    ok = await persistence.save_state(_call_tool)
    return {"status": "saved" if ok else "failed"}


@app.post("/api/persist/restore")
async def persist_restore():
    """Manually trigger a state restore from the HF dataset repo."""
    if not persistence.is_available():
        return JSONResponse(status_code=503, content={"error": "Persistence not available — set HF_TOKEN as a Space secret"})
    ok = await persistence.restore_state(_call_tool)
    return {"status": "restored" if ok else "failed"}


@app.get("/api/persist/status")
async def persist_status():
    """Check persistence configuration status."""
    return {
        "available": persistence.is_available(),
        "repo_id": persistence._get_repo_id(),
        "has_token": bool(os.environ.get("HF_TOKEN", "")),
        "has_username": bool(os.environ.get("SPACE_AUTHOR_NAME", "") or os.environ.get("SPACE_ID", "")),
    }


@app.get("/api/capsule-log")
async def capsule_log():
    return {"lines": capsule_log_lines[-100:]}


# --- Dreamer & Vast Fleet Aggregation Routes ---
# These aggregate multiple MCP tool calls into single API responses
# for the Dreamer and GPU Fleet dashboard tabs.

# Dreamer state cache (avoid hammering capsule)
_dreamer_cache = {"data": None, "ts": 0}
_dreamer_config_defaults = {
    "rewards": {
        "hold_accept": 1.0, "hold_override": -0.5, "bag_induct": 0.8,
        "bag_forget": -0.3, "workflow_save": 1.0, "workflow_success": 0.5,
        "workflow_failure": -0.5, "tool_success": 0.1, "tool_error": -0.2,
        "mutation_kept": 0.3, "mutation_reverted": -0.1, "normalize": True
    },
    "training": {
        "enabled": True, "auto_train": True, "world_model_frequency": 32,
        "critic_frequency": 32, "full_cycle_frequency": 64, "batch_size": 32,
        "noise_scale": 0.005, "gamma": 0.99, "lambda": 0.95,
        "critic_target_tau": 0.02, "timeout_budget_seconds": 30
    },
    "imagination": {"horizon": 15, "n_actions": 8, "auto_imagine_on_train": True},
    "buffers": {
        "reward_buffer_max": 5000, "obs_buffer_max": 1000,
        "value_history_max": 200, "reward_rate_window": 100
    },
    "architecture": {
        "critic_hidden_dim": 256, "reward_head_hidden_dim": 128,
        "continue_head_hidden_dim": 64, "latent_dim": 5120
    }
}

# Dreamer training history (kept server-side for charting)
_dreamer_history = {
    "critic_loss": [],      # list of {ts, baseline, perturbed, accepted}
    "reward_counts": [],    # list of {ts, count}
    "fitness": [],          # list of {ts, value}
}
_dreamer_last_cycle = 0


@app.get("/api/dreamer/state")
async def dreamer_state():
    """Aggregated dreamer state: get_status + show_rssm + show_weights in one call.
    Caches for 3 seconds to avoid hammering the capsule on rapid polls."""
    global _dreamer_last_cycle
    now = time.time()

    # Return cache if fresh (< 3s)
    if _dreamer_cache["data"] and now - _dreamer_cache["ts"] < 3:
        return _dreamer_cache["data"]

    # Fetch all three in parallel-ish (sequential but fast internal calls)
    status_raw = await _call_tool("get_status", {})
    rssm_raw = await _call_tool("show_rssm", {})
    weights_raw = await _call_tool("show_weights", {})
    lora_raw = await _call_tool("show_lora", {})

    status = _parse_mcp_result(status_raw.get("result")) or {}
    rssm = _parse_mcp_result(rssm_raw.get("result")) or {}
    weights = _parse_mcp_result(weights_raw.get("result")) or {}
    lora = _parse_mcp_result(lora_raw.get("result")) or {}

    dreamer = status.get("dreamer", {}) if isinstance(status, dict) else {}

    # Track training history for charts
    cycles = dreamer.get("training_cycles", 0)
    if cycles > _dreamer_last_cycle and dreamer.get("last_train"):
        lt = dreamer["last_train"]
        _dreamer_history["critic_loss"].append({
            "ts": now, "cycle": cycles,
            "baseline": lt.get("critic_baseline_loss"),
            "perturbed": lt.get("critic_perturbed_loss"),
            "accepted": lt.get("accepted"),
        })
        # Cap history at 200 entries
        if len(_dreamer_history["critic_loss"]) > 200:
            _dreamer_history["critic_loss"] = _dreamer_history["critic_loss"][-200:]
        _dreamer_last_cycle = cycles

    _dreamer_history["reward_counts"].append({"ts": now, "count": dreamer.get("reward_count", 0)})
    _dreamer_history["fitness"].append({"ts": now, "value": dreamer.get("fitness", 0)})
    # Cap
    for k in ("reward_counts", "fitness"):
        if len(_dreamer_history[k]) > 200:
            _dreamer_history[k] = _dreamer_history[k][-200:]

    if isinstance(rssm, dict):
        # New champion show_rssm returns RSSM dims at top-level; keep legacy fallback.
        rssm_view = rssm.get("metrics", {}).get("other", rssm)
    else:
        rssm_view = {}

    result = {
        "dreamer": dreamer,
        "rssm": rssm_view,
        "weights": weights,
        "lora": lora,
        "history": _dreamer_history,
        "generation": status.get("generation") if isinstance(status, dict) else None,
        "fitness": status.get("fitness") if isinstance(status, dict) else None,
    }
    _dreamer_cache["data"] = result
    _dreamer_cache["ts"] = now
    return result


@app.get("/api/dreamer/config")
async def dreamer_config_get():
    """Load dreamer config from FelixBag, falling back to defaults."""
    result = await _call_tool("bag_get", {"key": "dreamer_config"})
    parsed = _parse_mcp_result(result.get("result"))
    if parsed and isinstance(parsed, dict) and "value" in parsed:
        try:
            return {"config": json.loads(parsed["value"]), "source": "bag"}
        except (json.JSONDecodeError, TypeError):
            pass
    return {"config": _dreamer_config_defaults, "source": "defaults"}


@app.post("/api/dreamer/config")
async def dreamer_config_save(request: Request):
    """Save dreamer config to FelixBag."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    config = body.get("config", body)
    result = await _call_tool("bag_induct", {
        "key": "dreamer_config",
        "content": json.dumps(config),
        "item_type": "config"
    })
    parsed = _parse_mcp_result(result.get("result"))
    return {"status": "saved", "result": parsed}


@app.post("/api/dreamer/config/reset")
async def dreamer_config_reset():
    """Reset dreamer config to defaults (remove from bag, return defaults)."""
    await _call_tool("bag_forget", {"key": "dreamer_config"})
    return {"status": "reset", "config": _dreamer_config_defaults}


# Vast fleet state cache
_vast_fleet_cache = {"data": None, "ts": 0}


@app.get("/api/vast/state")
async def vast_fleet_state():
    """Aggregated vast fleet state from vast_instances.
    Caches for 5 seconds to avoid hammering the capsule."""
    now = time.time()
    if _vast_fleet_cache["data"] and now - _vast_fleet_cache["ts"] < 5:
        return _vast_fleet_cache["data"]

    result = await _call_tool("vast_instances", {})
    parsed = _parse_mcp_result(result.get("result"))
    instances = _normalize_vast_instances(parsed)

    # Also get capsule status for vast-related state
    status_raw = await _call_tool("get_status", {})
    status = _parse_mcp_result(status_raw.get("result")) or {}

    # Extract vast activity from recent activity log
    vast_activity = [
        {
            "tool": e.get("tool", ""),
            "status": "error" if e.get("error") else "ok",
            "duration": e.get("durationMs", 0),
            "timestamp": e.get("timestamp", 0),
            "error": e.get("error"),
        }
        for e in _activity_log
        if e.get("tool", "").startswith("vast_")
    ][-10:]

    fleet = {
        "instances": instances,
        "activity": vast_activity,
        "slots_filled": status.get("slots_filled", 0) if isinstance(status, dict) else 0,
        "ssh": _ssh_bootstrap_status(),
    }
    _vast_fleet_cache["data"] = fleet
    _vast_fleet_cache["ts"] = now
    return fleet


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


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy():
    return Path("static/privacy.html").read_text()


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

                                            if pending["tool"] == "get_genesis" and error_str and "NoneType" in error_str:
                                                safe = {
                                                    "genesis_hash": None,
                                                    "lineage": [],
                                                    "note": "Genesis data not initialized for this capsule instance",
                                                }
                                                rpc_result = {
                                                    "content": [{"type": "text", "text": json.dumps(safe)}]
                                                }
                                                rpc_error = None
                                                error_str = None
                                                payload.pop("error", None)
                                                payload["result"] = rpc_result
                                                line = "data: " + json.dumps(payload)

                                            print(f"[MCP-PROXY] Matched pending call id={rpc_id} tool={pending['tool']} duration={duration_ms}ms has_result={rpc_result is not None}")
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
    body = _normalize_mcp_jsonrpc_payload(body)
    content_type = request.headers.get("content-type", "application/json")
    print(f"[MCP-PROXY] POST /mcp/message(s) session_id={session_id} len={len(body)}")

    # Extract tools/call payload(s) for activity tracking (single or batch).
    rpc_calls = [
        {"tool": tool, "args": args, "rpc_id": rpc_id}
        for tool, args, rpc_id in _parse_rpc_tool_calls(body)
    ]

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
            if rpc_calls:
                if resp.status_code in (202, 204):
                    # SSE protocol: result comes on the SSE stream, not here.
                    # Store as pending - mcp_sse_proxy will resolve it with real data.
                    for call in rpc_calls:
                        rpc_id = call["rpc_id"]
                        if rpc_id is not None:
                            _pending_external_calls[rpc_id] = {
                                "tool": call["tool"],
                                "args": call["args"],
                                "start": start,
                            }
                            print(
                                f"[MCP-PROXY] Stored pending call id={rpc_id} "
                                f"(type={type(rpc_id).__name__}) tool={call['tool']}"
                            )
                        else:
                            # Notifications (no id) cannot be matched on SSE response.
                            _broadcast_activity(call["tool"], call["args"], None, duration_ms, None, source="external")
                elif resp.status_code == 200:
                    # Got inline JSON response(s) - map by id when present.
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

                    def _pop_call_for_id(rpc_id):
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
                            # Some servers omit JSON-RPC id on single-call inline responses.
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

                        _broadcast_activity(
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
                        _broadcast_activity(
                            call["tool"],
                            call["args"],
                            None,
                            duration_ms,
                            error_str,
                            source="external",
                        )
                else:
                    for call in rpc_calls:
                        _broadcast_activity(
                            call["tool"],
                            call["args"],
                            None,
                            duration_ms,
                            f"HTTP {resp.status_code}",
                            source="external",
                        )

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
        for call in rpc_calls:
            _broadcast_activity(call["tool"], call["args"], None, duration_ms, "Capsule timeout", source="external")
        return JSONResponse(status_code=504, content={"error": "Capsule timeout"})
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        for call in rpc_calls:
            _broadcast_activity(call["tool"], call["args"], None, duration_ms, str(e), source="external")
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
