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
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlsplit, urlunsplit, unquote

import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from mcp import ClientSession
from mcp.client.sse import sse_client

import time
import persistence

# Ensure Starlette static serving emits correct MIME for audio container files.
mimetypes.add_type("audio/mp4", ".m4a")

# Track last chat slot — auto-reset capsule chat session on slot change
_last_chat_slot: int | None = None

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
    if v in ("external", "webui", "hydration", "extension", "action", "api", "agent-inner"):
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


def _extract_client_id(request: Request) -> str | None:
    """Extract a granular client identifier from request headers.
    Prefers explicit client headers, then UA signatures, then auth fallback.
    """
    # Explicit client-id header (preferred — callers self-identify)
    client_id = request.headers.get("x-client-id") or request.headers.get("x-mcp-client")
    if client_id:
        return client_id.strip()[:64]

    ua = (request.headers.get("user-agent") or "").strip()
    ua_lower = ua.lower()

    # Known client signatures
    if "pi-mcp" in ua_lower or "pi-coding-agent" in ua_lower:
        return "pi-agent"
    if "claude" in ua_lower:
        return "claude-code"
    if "kiro" in ua_lower:
        return "kiro"
    if "cursor" in ua_lower:
        return "cursor"
    if "windsurf" in ua_lower:
        return "windsurf"
    if "copilot" in ua_lower:
        return "copilot"
    if "chatgpt" in ua_lower or "openai" in ua_lower:
        return "chatgpt-action"

    # Generic MCP SDK signatures
    if "modelcontextprotocol" in ua_lower or "mcp" in ua_lower:
        return "mcp-client"

    # Generic user-agent extraction (first segment)
    if ua and "/" in ua:
        agent_name = ua.split("/")[0].strip().lower()[:24]
        if agent_name and agent_name not in ("mozilla", "python-requests", "python"):
            return agent_name

    # Python clients (requests, httpx, aiohttp)
    if "python" in ua_lower or "httpx" in ua_lower or "aiohttp" in ua_lower:
        return "python-client"

    # Auth fallback (can't identify exact client from token alone)
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and len(auth) > 20:
        return "hf-authenticated"

    return None


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


async def _slot_ready_guard(tool_name: str, args: dict | None) -> dict | None:
    """Block slot-targeted generation/chat calls when slot is not plugged yet."""
    if tool_name not in _SLOT_READY_TOOLS:
        return None
    if not isinstance(args, dict) or args.get("slot") is None:
        return None

    try:
        slot_idx = int(args.get("slot"))
    except Exception:
        return {
            "guard": "slot_ready",
            "tool": tool_name,
            "error": f"Invalid slot index for {tool_name}",
        }

    info_raw = await _call_tool("slot_info", {"slot": slot_idx})
    info = _parse_mcp_result((info_raw or {}).get("result") if isinstance(info_raw, dict) else None) or {}
    if not isinstance(info, dict):
        info = {}

    plugged = bool(info.get("plugged"))
    if not plugged:
        src = info.get("source") or info.get("model_source") or info.get("model")
        if src:
            plugged = True

    if plugged:
        return None

    return {
        "guard": "slot_ready",
        "tool": tool_name,
        "slot": slot_idx,
        "error": f"Slot {slot_idx} is not plugged yet. Wait for plug_model/hub_plug to complete before calling {tool_name}.",
    }


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

# Guard slot-targeted generation/chat tools so they don't run before plug completes.
_SLOT_READY_TOOLS = frozenset({"invoke_slot", "chat", "agent_chat", "generate", "classify"})

# Serialize heavy slot-bound generation/chat calls to prevent overlap storms
# when external clients time out locally and retry while the first call is
# still running on the backend.
_SLOT_SERIAL_TOOLS = frozenset({"invoke_slot", "chat", "agent_chat", "generate", "classify"})

# Emit immediate activity "start" entries for long-running calls so UI isn't blank.
_LIVE_START_TOOLS = frozenset({"agent_chat", "invoke_slot", "chat", "generate", "classify", "plug_model", "hub_plug"})

_slot_exec_gate = asyncio.Lock()
_slot_exec_locks: dict[int, asyncio.Lock] = {}
_slot_exec_active: dict[int, dict] = {}


def _slot_serial_index(tool_name: str, args: dict | None) -> int | None:
    if tool_name not in _SLOT_SERIAL_TOOLS:
        return None
    if not isinstance(args, dict):
        return None
    if args.get("slot") is None:
        return None
    try:
        return int(args.get("slot"))
    except Exception:
        return None


async def _claim_slot_execution(tool_name: str, args: dict | None, source: str, client_id: str | None) -> tuple[dict | None, dict | None]:
    """Try to claim exclusive execution for slot-bound heavy tools.

    Returns: (claim, busy_payload)
      - claim: internal token to release in finally
      - busy_payload: guard payload when slot already running another call
    """
    slot_idx = _slot_serial_index(tool_name, args)
    if slot_idx is None:
        return None, None

    now_ms = int(time.time() * 1000)
    async with _slot_exec_gate:
        lock = _slot_exec_locks.get(slot_idx)
        if lock is None:
            lock = asyncio.Lock()
            _slot_exec_locks[slot_idx] = lock

        active = _slot_exec_active.get(slot_idx)
        if lock.locked() or active:
            active = active or {}
            started_ms = active.get("started_ms")
            running_for_ms = None
            try:
                if started_ms is not None:
                    running_for_ms = max(0, now_ms - int(started_ms))
            except Exception:
                running_for_ms = None
            active_tool = active.get("tool") or "unknown"
            busy = {
                "guard": "slot_busy",
                "tool": tool_name,
                "slot": slot_idx,
                "active": {
                    "tool": active_tool,
                    "source": active.get("source"),
                    "client_id": active.get("client_id"),
                    "session_id": active.get("session_id"),
                    "started_ms": started_ms,
                    "running_for_ms": running_for_ms,
                },
                "error": f"Slot {slot_idx} is busy running {active_tool}. Wait for completion before calling {tool_name}."
            }
            return None, busy

        await lock.acquire()
        _sid = ""
        if tool_name == "agent_chat" and isinstance(args, dict):
            _sid = str(args.get("session_id", "") or "").strip()
        _slot_exec_active[slot_idx] = {
            "tool": tool_name,
            "source": source,
            "client_id": client_id,
            "session_id": _sid or None,
            "started_ms": now_ms,
        }
        return {"slot": slot_idx, "lock": lock}, None


async def _release_slot_execution(claim: dict | None) -> None:
    if not isinstance(claim, dict):
        return
    slot_idx = claim.get("slot")
    lock = claim.get("lock")
    if slot_idx is None or lock is None:
        return

    async with _slot_exec_gate:
        _slot_exec_active.pop(int(slot_idx), None)
        try:
            if lock.locked():
                lock.release()
        except Exception:
            pass


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


def _broadcast_activity(tool: str, args: dict, result: dict | None, duration_ms: int, error: str | None, source: str = "external", client_id: str | None = None):
    """Record and broadcast a tool call to all SSE activity subscribers."""
    # Suppress hydration calls entirely
    if source == "hydration":
        return
    # Only suppress silent tools for internal/webui calls — external MCP
    # clients (Kiro, Claude, etc.) should always see their results.
    if tool in _SILENT_TOOLS and source not in ("external", "agent-inner"):
        return

    cat = tool.split("_")[0] if tool else "other"
    # Parse the MCP envelope so the frontend gets real data
    parsed_result = _parse_mcp_result(result)
    # Debug: log what we're broadcasting so we can trace blank-data issues
    result_preview = str(parsed_result)[:200] if parsed_result else "None"
    print(f"[ACTIVITY] Broadcasting: tool={tool} source={source} client={client_id} has_result={parsed_result is not None} result_type={type(parsed_result).__name__} subs={len(_activity_subscribers)} preview={result_preview}")
    entry = {
        "tool": tool,
        "category": cat,
        "args": args or {},
        "result": parsed_result,
        "error": error,
        "durationMs": duration_ms,
        "timestamp": int(time.time() * 1000),
        "source": source,
        "clientId": client_id,  # granular client identification
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

def _broadcast_agent_inner_calls(tool_name: str, result, duration_ms: int, source: str = "external", client_id: str | None = None):
    """Extract inner tool_calls from agent_chat results and broadcast each as a separate activity entry."""
    if tool_name != "agent_chat":
        return
    parsed = _parse_mcp_result(result)
    if not isinstance(parsed, dict):
        print(f"[AGENT-INNER] Skip: parsed is {type(parsed).__name__}, not dict")
        return
    inner_result = parsed.get("result") if "result" in parsed else parsed
    tool_calls = inner_result.get("tool_calls") if isinstance(inner_result, dict) else None
    if not isinstance(tool_calls, list) or len(tool_calls) == 0:
        print(f"[AGENT-INNER] Skip: tool_calls={type(tool_calls).__name__} len={len(tool_calls) if isinstance(tool_calls, list) else 'N/A'} keys={list(inner_result.keys()) if isinstance(inner_result, dict) else 'N/A'}")
        return
    slot_idx = inner_result.get("slot")
    slot_name = inner_result.get("name", "")
    print(f"[AGENT-INNER] Extracting {len(tool_calls)} inner tool calls from agent_chat (slot={slot_idx}/{slot_name})")
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        tc_tool = tc.get("tool", "unknown")
        tc_args = tc.get("args", {})
        tc_result_str = tc.get("result", "")
        tc_error = tc.get("error")
        tc_iteration = tc.get("iteration", i)
        tc_result_content = {"content": [{"type": "text", "text": tc_result_str if isinstance(tc_result_str, str) else json.dumps(tc_result_str)}]}
        _broadcast_activity(
            tc_tool,
            tc_args,
            tc_result_content,
            duration_ms,
            str(tc_error) if tc_error else None,
            source="agent-inner",
            client_id=client_id,
        )
        print(f"[AGENT-INNER] Broadcast {i+1}/{len(tool_calls)}: {tc_tool} (iter={tc_iteration}, slot={slot_idx}/{slot_name})")


# --- Configuration ---
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
WEB_PORT = 7860
CAPSULE_PATH = Path("capsule/champion_gen8.py")
MCP_BASE = f"http://127.0.0.1:{MCP_PORT}"
HF_ROUTER_BASE = os.environ.get("HF_ROUTER_BASE", "https://router.huggingface.co").rstrip("/")


def _hf_router_token(explicit: str | None = None) -> str | None:
    token = (explicit or "").strip()
    if token:
        return token
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


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
_capsule_instructions: str | None = None  # Rich instructions from capsule handshake


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
    global _mcp_session, _sse_cm, _session_cm, _read_stream, _write_stream, _capsule_instructions

    async with _mcp_lock:
        if _mcp_session is not None:
            return True

        try:
            # sse_client is an async context manager that returns (read, write) streams
            _sse_cm = sse_client(f"{MCP_BASE}/sse")
            _read_stream, _write_stream = await _sse_cm.__aenter__()

            # ClientSession wraps the streams with JSON-RPC protocol
            _session_cm = ClientSession(_read_stream, _write_stream, read_timeout_seconds=timedelta(seconds=180))
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

            # Cache the capsule's rich MCP instructions for the proxy initialize response.
            # The capsule builds these via _build_mcp_instructions() — they contain the full
            # onboarding orientation (tool groups, workflow engine, FelixBag, CASCADE, etc.).
            _instr = getattr(result, 'instructions', None)
            if _instr is None and hasattr(result, 'model_dump'):
                _instr = result.model_dump().get('instructions')
            if _instr and isinstance(_instr, str) and len(_instr) > 100:
                _capsule_instructions = _instr
                print(f"[OK] Cached capsule instructions ({len(_instr)} chars)")

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
    """List MCP tools via the SDK session, including local orchestrator virtual tools."""
    session = await _ensure_session()
    if not session:
        return {"error": "MCP session not available"}
    try:
        result = await session.list_tools()
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": getattr(t, 'inputSchema', None) or getattr(t, 'input_schema', {}),
            }
            for t in (result.tools or [])
        ]
        return {
            "result": {
                "tools": _agent_augment_tools_list(tools)
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


def _normalize_remote_provider_model_id(model_id: str) -> tuple[str, bool]:
    """Normalize remote provider URLs for capsule compatibility.

    Capsule-side URL parsing is intentionally simple. To keep provider plug flows
    interoperable across web UI and MCP clients, normalize here at the proxy:
      - decode percent-encoded model/key query values
      - strip trailing /v1 so capsule appends /v1/* exactly once
    """
    if not isinstance(model_id, str):
        return model_id, False

    raw = model_id.strip()
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return model_id, False

    try:
        parts = urlsplit(raw)
    except Exception:
        return model_id, False

    changed = False
    path = parts.path or ""
    path_no_slash = path.rstrip("/")
    if path_no_slash.endswith("/v1"):
        path = path_no_slash[:-3]
        changed = True
    elif path_no_slash != path:
        path = path_no_slash
        changed = True

    query = parts.query or ""
    if query:
        normalized_tokens = []
        for token in query.split("&"):
            if not token:
                continue
            if "=" in token:
                key, value = token.split("=", 1)
            else:
                key, value = token, ""

            if key in ("model", "key"):
                decoded = unquote(value)
                if decoded != value:
                    changed = True
                # Keep query structure safe for the capsule's naive split parser.
                decoded = decoded.replace("&", "%26").replace("=", "%3D")
                token = f"{key}={decoded}"

            normalized_tokens.append(token)

        new_query = "&".join(normalized_tokens)
        if new_query != query:
            changed = True
    else:
        new_query = query

    rebuilt = urlunsplit((parts.scheme, parts.netloc, path, new_query, parts.fragment))
    if rebuilt != raw:
        changed = True

    return rebuilt, changed


_DOC_KEY_PREFIX = "__docv2__"
_DOC_KEY_SUFFIX = "__k"


def _doc_escape_key(value: str) -> str:
    return str(value).replace("~", "~~").replace("/", "~s")


def _doc_unescape_key(value: str) -> str:
    s = str(value)
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "~" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "~":
                out.append("~")
                i += 2
                continue
            if nxt == "s":
                out.append("/")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _doc_is_encoded_key(key: str) -> bool:
    return isinstance(key, str) and key.startswith(_DOC_KEY_PREFIX)


def _doc_should_virtualize_key(key: str) -> bool:
    if not isinstance(key, str) or not key:
        return False
    if key.startswith("bag_checkpoint:"):
        return False
    if _doc_is_encoded_key(key):
        return True
    return "/" in key


def _doc_encode_exact_key(key: str) -> str:
    if _doc_is_encoded_key(key):
        return key
    return f"{_DOC_KEY_PREFIX}{_doc_escape_key(key)}{_DOC_KEY_SUFFIX}"


def _doc_encode_prefix(prefix: str) -> str:
    if _doc_is_encoded_key(prefix):
        return prefix
    return f"{_DOC_KEY_PREFIX}{_doc_escape_key(prefix)}"


def _doc_decode_key(key: str) -> str:
    if not _doc_is_encoded_key(key):
        return key
    body = key[len(_DOC_KEY_PREFIX):]
    if body.endswith(_DOC_KEY_SUFFIX):
        body = body[:-len(_DOC_KEY_SUFFIX)]
    return _doc_unescape_key(body)


def _doc_decode_result_text(text: str) -> str:
    """Decode all encoded __docv2__ keys in a result string for human display."""
    import re as _dre
    def _replacer(m):
        try:
            return _doc_decode_key(m.group(0))
        except Exception:
            return m.group(0)
    return _dre.sub(r'__docv2__[^"}\s,\]]+', _replacer, text)


def _doc_encode_checkpoint_key(checkpoint_key: str) -> str:
    if not isinstance(checkpoint_key, str) or not checkpoint_key.startswith("bag_checkpoint:"):
        return checkpoint_key
    try:
        left, ts = checkpoint_key.rsplit(":", 1)
        src = left[len("bag_checkpoint:"):]
        if _doc_should_virtualize_key(src):
            src = _doc_encode_exact_key(_doc_decode_key(src) if _doc_is_encoded_key(src) else src)
        return f"bag_checkpoint:{src}:{ts}"
    except Exception:
        return checkpoint_key


def _doc_decode_checkpoint_key(checkpoint_key: str) -> str:
    if not isinstance(checkpoint_key, str) or not checkpoint_key.startswith("bag_checkpoint:"):
        return checkpoint_key
    try:
        left, ts = checkpoint_key.rsplit(":", 1)
        src = left[len("bag_checkpoint:"):]
        return f"bag_checkpoint:{_doc_decode_key(src)}:{ts}"
    except Exception:
        return checkpoint_key


def _ensure_parent_dir_for_path(path_value: str | None) -> None:
    if not isinstance(path_value, str) or not path_value.strip():
        return
    try:
        p = Path(path_value.strip())
        parent = p.parent
        if str(parent) and str(parent) != ".":
            parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _normalize_proxy_tool_args(tool_name: str, args: dict | None) -> dict:
    if not isinstance(args, dict):
        return args or {}

    patched = dict(args)

    if isinstance(tool_name, str) and tool_name.startswith("file_"):
        if "path" not in patched and isinstance(patched.get("key"), str):
            patched["path"] = patched.get("key")
        if "source_path" not in patched and isinstance(patched.get("source"), str):
            patched["source_path"] = patched.get("source")
        if "dest_path" not in patched and isinstance(patched.get("destination"), str):
            patched["dest_path"] = patched.get("destination")
        if tool_name == "file_write" and "content" not in patched and "value" in patched:
            patched["content"] = patched.get("value")

    # C4 fix: bag_catalog(filter_type="all") — capsule treats "all" as literal type match.
    # Strip it so the call returns unfiltered results as the caller intended.
    if tool_name == "bag_catalog":
        ft = patched.get("filter_type")
        if isinstance(ft, str) and ft.strip().lower() in ("all", "*", "any", ""):
            patched.pop("filter_type", None)

    if tool_name == "plug_model" and isinstance(patched.get("model_id"), str):
        normalized, changed = _normalize_remote_provider_model_id(patched.get("model_id"))
        if changed:
            patched["model_id"] = normalized

    # Virtualized document keys for slash-path keys (FelixBag compatibility shim)
    if tool_name in ("bag_get", "bag_put", "bag_read_doc", "bag_checkpoint", "bag_versions", "bag_restore", "bag_diff", "bag_induct"):
        k = patched.get("key")
        if _doc_should_virtualize_key(k):
            patched["key"] = _doc_encode_exact_key(_doc_decode_key(k) if _doc_is_encoded_key(k) else k)

    if tool_name in ("bag_list_docs", "bag_search_docs", "bag_tree"):
        pfx = patched.get("prefix")
        if isinstance(pfx, str) and pfx and _doc_should_virtualize_key(pfx):
            patched["prefix"] = _doc_encode_prefix(_doc_decode_key(pfx) if _doc_is_encoded_key(pfx) else pfx)

    if tool_name in (
        "file_read", "file_write", "file_edit", "file_append", "file_prepend", "file_delete",
        "file_rename", "file_copy", "file_info", "file_checkpoint", "file_versions", "file_diff", "file_restore"
    ):
        for kf in ("key", "path", "old_path", "new_path", "source_path", "dest_path", "source", "destination"):
            kv = patched.get(kf)
            if isinstance(kv, str) and kv and _doc_should_virtualize_key(kv):
                patched[kf] = _doc_encode_exact_key(_doc_decode_key(kv) if _doc_is_encoded_key(kv) else kv)

    if tool_name in ("file_list", "file_tree", "file_search"):
        pfx = patched.get("path")
        if not isinstance(pfx, str) or not pfx:
            pfx = patched.get("prefix")
        if isinstance(pfx, str) and pfx and _doc_should_virtualize_key(pfx):
            patched["path"] = _doc_encode_prefix(_doc_decode_key(pfx) if _doc_is_encoded_key(pfx) else pfx)

    if tool_name == "bag_forget":
        k = patched.get("key")
        pat = patched.get("pattern")
        if isinstance(k, str) and k and not pat and _doc_should_virtualize_key(k):
            patched["key"] = _doc_encode_exact_key(_doc_decode_key(k) if _doc_is_encoded_key(k) else k)
        if isinstance(pat, str) and pat and _doc_should_virtualize_key(pat):
            patched["pattern"] = _doc_encode_prefix(_doc_decode_key(pat) if _doc_is_encoded_key(pat) else pat)

    if tool_name == "bag_restore" and isinstance(patched.get("checkpoint_key"), str):
        patched["checkpoint_key"] = _doc_encode_checkpoint_key(patched["checkpoint_key"])

    if tool_name == "file_restore" and isinstance(patched.get("checkpoint_key"), str):
        patched["checkpoint_key"] = _doc_encode_checkpoint_key(patched["checkpoint_key"])

    if tool_name in ("file_diff",):
        if isinstance(patched.get("from_checkpoint"), str) and patched.get("from_checkpoint"):
            patched["from_checkpoint"] = _doc_encode_checkpoint_key(patched["from_checkpoint"])
        if isinstance(patched.get("to_checkpoint"), str) and patched.get("to_checkpoint") not in ("", "current"):
            patched["to_checkpoint"] = _doc_encode_checkpoint_key(patched["to_checkpoint"])

    # Ensure target dirs exist for filesystem-exporting tools
    if tool_name == "materialize":
        _ensure_parent_dir_for_path(patched.get("output_path"))
    elif tool_name == "save_bag":
        _ensure_parent_dir_for_path(patched.get("file_path"))
    elif tool_name == "bag_export":
        _ensure_parent_dir_for_path(patched.get("output_path"))

    return patched


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
        raw_args = params.get("arguments")
        coerced = _coerce_tool_arguments(raw_args)
        if coerced != raw_args:
            params["arguments"] = coerced
            changed = True

    # For strict no-arg tools, omit empty arguments object.
    if "arguments" in params and isinstance(params.get("arguments"), dict) and not params.get("arguments"):
        params.pop("arguments", None)
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

    normalized_args = _normalize_proxy_tool_args(tool, args if isinstance(args, dict) else {})
    if normalized_args != args:
        params["arguments"] = normalized_args
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


# ═══════════════════════════════════════════════════════════════════════
# SERVER-SIDE AGENT ORCHESTRATOR
# Runs the agent tool-call loop at the proxy layer so every step is
# individually visible, timeout-resilient, and streamed via SSE.
# The capsule's monolithic agent_chat is bypassed entirely.
# ═══════════════════════════════════════════════════════════════════════

_AGENT_BLOCKED_TOOLS = frozenset({
    "workflow_execute", "start_api_server", "implode", "defrost",
    "spawn_quine", "spawn_swarm", "replicate", "export_quine",
    "agent_chat",  # prevent direct self-recursive nesting (use agent_delegate)
})

_AGENT_DEFAULT_GRANTED = [
    "get_status", "list_slots", "slot_info", "get_capabilities", "embed_text",
    "invoke_slot", "call", "agent_delegate", "agent_chat_inject", "agent_chat_sessions",
    "bag_get", "bag_put", "bag_search", "bag_catalog", "bag_induct",
    "bag_read_doc", "bag_list_docs", "bag_search_docs", "bag_tree",
    "bag_versions", "bag_diff", "bag_checkpoint", "bag_restore",
    "file_read", "file_write", "file_edit", "file_append", "file_prepend",
    "file_delete", "file_rename", "file_copy", "file_list", "file_tree",
    "file_search", "file_info", "file_checkpoint", "file_versions",
    "file_diff", "file_restore",
    "web_search", "generate", "classify", "rerank",
    "plug_model", "hub_plug", "unplug_slot",
    "cascade_graph", "cascade_chain", "cascade_data", "cascade_system",
    "cascade_record", "diagnose_file", "diagnose_directory",
    "symbiotic_interpret", "trace_root_causes", "forensics_analyze",
    "metrics_analyze", "workflow_list", "workflow_get", "workflow_status",
]

_AGENT_MAX_DELEGATION_DEPTH = max(1, int(os.environ.get("AGENT_MAX_DELEGATION_DEPTH", "3")))
_AGENT_INJECT_QUEUE_LIMIT = max(5, int(os.environ.get("AGENT_INJECT_QUEUE_LIMIT", "64")))

_AGENT_LOCAL_TOOL_SPECS = {
    "agent_delegate": {
        "description": "Delegate a sub-task to another slot's autonomous agent loop and return its result envelope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer", "description": "Target slot index to delegate to"},
                "message": {"type": "string", "description": "Sub-task message for the delegated agent"},
                "max_iterations": {"type": "integer", "description": "Optional delegated max iterations"},
                "max_tokens": {"type": "integer", "description": "Optional delegated max tokens"},
                "session_id": {"type": "string", "description": "Optional delegated session id"},
                "granted_tools": {"type": "array", "description": "Optional delegated granted tools"}
            },
            "required": ["slot", "message"]
        }
    },
    "agent_chat_inject": {
        "description": "Queue a live operator/agent update into a running agent_chat session inbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Target agent_chat session id"},
                "slot": {"type": "integer", "description": "Target slot (used when session_id omitted)"},
                "message": {"type": "string", "description": "Injected instruction/update text"},
                "sender": {"type": "string", "description": "Sender label (operator/system/agent)"},
                "priority": {"type": "string", "description": "Optional priority label"}
            },
            "required": ["message"]
        }
    },
    "agent_chat_sessions": {
        "description": "List active/recent agent_chat sessions with queue depth and state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer", "description": "Optional slot filter"},
                "active_only": {"type": "boolean", "description": "Show only active sessions"},
                "limit": {"type": "integer", "description": "Max sessions to return"}
            }
        }
    }
}


def _agent_local_tools_manifest() -> list[dict]:
    return [
        {
            "name": name,
            "description": spec.get("description", ""),
            "inputSchema": spec.get("inputSchema", {}),
        }
        for name, spec in _AGENT_LOCAL_TOOL_SPECS.items()
    ]


def _agent_augment_tools_list(tools: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for t in (tools or []):
        if not isinstance(t, dict):
            continue
        name = str(t.get("name", "") or "").strip()
        if not name:
            continue
        seen.add(name)
        merged.append(t)
    for t in _agent_local_tools_manifest():
        name = t.get("name")
        if name not in seen:
            merged.append(t)
    return merged


def _agent_session_snapshot(args: dict | None = None) -> dict:
    args = args or {}
    slot_filter = args.get("slot", None)
    active_only = bool(args.get("active_only", False))
    try:
        slot_filter = int(slot_filter) if slot_filter is not None else None
    except Exception:
        slot_filter = None
    limit = int(args.get("limit", 50) or 50)
    limit = max(1, min(limit, 500))

    rows = []
    for sid, sess in _agent_sessions.items():
        if not isinstance(sess, dict):
            continue
        slot = sess.get("slot")
        try:
            slot = int(slot)
        except Exception:
            slot = None
        if slot_filter is not None and slot != slot_filter:
            continue
        active = bool(sess.get("active", False))
        if active_only and not active:
            continue
        inbox = sess.get("inbox") if isinstance(sess.get("inbox"), list) else []
        rows.append({
            "session_id": sid,
            "slot": slot,
            "active": active,
            "turn_count": len(sess.get("turns") or []),
            "pending_messages": len(inbox),
            "updated_ts": int(sess.get("updated_ts") or sess.get("last_active_ts") or 0),
            "parent_session_id": str(sess.get("parent_session_id") or ""),
            "delegation_depth": int(sess.get("delegation_depth") or 0),
            "source": sess.get("source"),
            "client_id": sess.get("client_id"),
        })

    rows.sort(key=lambda r: int(r.get("updated_ts") or 0), reverse=True)
    if len(rows) > limit:
        rows = rows[:limit]

    return {
        "sessions": rows,
        "count": len(rows),
        "active_count": sum(1 for r in rows if r.get("active")),
    }


def _agent_select_session(session_id: str = "", slot: int | None = None, active_preferred: bool = True, strict_id: bool = False) -> tuple[str | None, dict | None]:
    """Find a matching agent session.

    Args:
        session_id: Explicit session id to look up.
        slot: Slot filter (only when session_id not given or not found).
        active_preferred: Prefer active sessions in ranking.
        strict_id: If True and session_id is given but not found, do NOT
                   fall back to slot-based search.  Return (None, None).
    """
    sid = str(session_id or "").strip()
    if sid and sid in _agent_sessions and isinstance(_agent_sessions.get(sid), dict):
        return sid, _agent_sessions.get(sid)

    # C2 fix: when caller provided an explicit session_id that doesn't exist,
    # fail closed instead of falling through to slot-based best-guess.
    if sid and strict_id:
        return None, None

    candidates = []
    for _sid, sess in _agent_sessions.items():
        if not isinstance(sess, dict):
            continue
        try:
            _slot = int(sess.get("slot"))
        except Exception:
            _slot = None
        if slot is not None and _slot != slot:
            continue
        candidates.append((_sid, sess))

    if not candidates:
        return None, None

    def _rank(item):
        _sid, sess = item
        active = 1 if bool(sess.get("active", False)) else 0
        ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or 0)
        return (active, ts)

    candidates.sort(key=_rank, reverse=True)
    if active_preferred:
        for _sid, sess in candidates:
            if bool(sess.get("active", False)):
                return _sid, sess
    return candidates[0]


def _agent_inject_message(args: dict, source: str = "webui", client_id: str | None = None, caller_session_id: str = "", caller_slot: int | None = None) -> dict:
    args = args or {}
    message = str(args.get("message", "") or "").strip()
    if not message:
        return {"error": "message is required"}

    req_session_id = str(args.get("session_id", "") or "").strip()
    slot_arg = args.get("slot", None)
    target_slot = None
    if slot_arg is not None:
        try:
            target_slot = int(slot_arg)
        except Exception:
            target_slot = None

    # C2 fix: if caller provided an explicit session_id, use strict lookup —
    # do not fall back to a different session if the id is not found.
    has_explicit_id = bool(req_session_id)
    sid, session = _agent_select_session(
        req_session_id, target_slot, active_preferred=True,
        strict_id=has_explicit_id,
    )
    if not sid or not isinstance(session, dict):
        if has_explicit_id:
            return {
                "error": f"Session not found: {req_session_id}",
                "session_id": req_session_id,
                "slot": target_slot,
            }
        return {
            "error": "No matching agent_chat session found",
            "session_id": req_session_id or None,
            "slot": target_slot,
        }

    # C3 fix: if caller used slot-only targeting (no explicit session_id) and
    # the matched session is not active, reject rather than silently queueing.
    if not has_explicit_id and target_slot is not None and not bool(session.get("active", False)):
        return {
            "error": f"No active session for slot {target_slot}",
            "session_id": sid,
            "slot": target_slot,
            "active": False,
        }

    inbox = session.get("inbox")
    if not isinstance(inbox, list):
        inbox = []
        session["inbox"] = inbox

    sender = str(args.get("sender", "operator") or "operator").strip() or "operator"
    priority = str(args.get("priority", "normal") or "normal").strip() or "normal"
    now_ms = int(time.time() * 1000)

    inbox.append({
        "message": message,
        "sender": sender,
        "priority": priority,
        "source": source,
        "client_id": client_id,
        "caller_session_id": str(caller_session_id or ""),
        "caller_slot": caller_slot,
        "ts": now_ms,
    })
    if len(inbox) > _AGENT_INJECT_QUEUE_LIMIT:
        del inbox[:-_AGENT_INJECT_QUEUE_LIMIT]

    session["updated_ts"] = now_ms
    _agent_sessions[sid] = session

    return {
        "status": "queued",
        "session_id": sid,
        "slot": session.get("slot"),
        "active": bool(session.get("active", False)),
        "pending_messages": len(inbox),
        "message": message,
        "sender": sender,
        "priority": priority,
    }


# Server-side session store (survives across HTTP requests)
_agent_sessions: dict[str, dict] = {}


async def _get_tool_descriptions(granted_tools: list[str]) -> str:
    """Build tool description block from capsule's tool list."""
    tools_raw = await _list_tools()
    all_tools = (tools_raw.get("result", {}).get("tools") or []) if isinstance(tools_raw, dict) else []
    granted_set = set(granted_tools)
    lines = []
    for t in all_tools:
        name = t.get("name", "")
        if name not in granted_set:
            continue
        desc = (t.get("description") or "").strip().split("\n")[0][:120]
        schema = t.get("inputSchema", {})
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        params = []
        for pname, pinfo in props.items():
            ptype = pinfo.get("type", "any") if isinstance(pinfo, dict) else "any"
            marker = " (required)" if pname in required else ""
            params.append(f"{pname}: {ptype}{marker}")
        sig = ", ".join(params)
        lines.append(f"- {name}({sig}): {desc}")
    return "\n".join(lines) if lines else "(no tool descriptions available)"


async def _agent_delegate_call(caller_slot: int, caller_session_id: str, caller_depth: int, called_args: dict, source: str, client_id: str | None) -> tuple[dict | None, str | None]:
    """Delegate to another slot's agent loop (safe nested orchestration)."""
    import uuid as _uuid

    try:
        target_slot = int(called_args.get("slot", -1))
    except Exception:
        target_slot = -1
    if target_slot < 0:
        return None, "agent_delegate requires a valid target slot"
    if target_slot == caller_slot:
        return None, f"agent_delegate blocked: target slot {target_slot} equals caller slot {caller_slot}"
    if caller_depth >= _AGENT_MAX_DELEGATION_DEPTH:
        return None, f"agent_delegate blocked: max delegation depth {_AGENT_MAX_DELEGATION_DEPTH} reached"

    delegate_message = str(called_args.get("message", "") or "").strip()
    if not delegate_message:
        return None, "agent_delegate requires message"

    try:
        delegate_max_iterations = int(called_args.get("max_iterations", 3) or 3)
    except Exception:
        delegate_max_iterations = 3
    delegate_max_iterations = max(1, min(delegate_max_iterations, 20))

    try:
        delegate_max_tokens = int(called_args.get("max_tokens", 0) or 0)
    except Exception:
        delegate_max_tokens = 0

    delegate_session_id = str(called_args.get("session_id", "") or "").strip()
    if not delegate_session_id:
        delegate_session_id = f"agent_chat:{target_slot}:{_uuid.uuid4().hex[:10]}"
    else:
        # C6 fix: if the session_id already exists but belongs to a DIFFERENT slot,
        # scope it to prevent cross-slot history leakage / context collision.
        existing = _agent_sessions.get(delegate_session_id)
        if isinstance(existing, dict):
            existing_slot = existing.get("slot")
            try:
                existing_slot = int(existing_slot)
            except Exception:
                existing_slot = None
            if existing_slot is not None and existing_slot != target_slot:
                delegate_session_id = f"{delegate_session_id}:slot{target_slot}"

    delegate_args = {
        "slot": target_slot,
        "message": delegate_message,
        "max_iterations": delegate_max_iterations,
        "session_id": delegate_session_id,
        "_agent_depth": caller_depth + 1,
        "_parent_session_id": caller_session_id,
    }
    if delegate_max_tokens > 0:
        delegate_args["max_tokens"] = delegate_max_tokens
    # C7 fix: only propagate granted_tools if the caller provided a non-empty list.
    # An empty list would starve the child agent of all tools. When omitted or empty,
    # the child inherits the server default grant set instead.
    caller_grants = called_args.get("granted_tools")
    if isinstance(caller_grants, list) and len(caller_grants) > 0:
        delegate_args["granted_tools"] = [str(t) for t in caller_grants if str(t).strip()]

    claim, busy = await _claim_slot_execution("agent_chat", {"slot": target_slot, "session_id": delegate_session_id}, source="agent-inner", client_id=client_id)
    if busy:
        return {"slot_busy": busy}, busy.get("error") or "delegate target busy"

    try:
        delegated = await _server_side_agent_chat(delegate_args, source="agent-inner", client_id=client_id)
    finally:
        await _release_slot_execution(claim)

    if isinstance(delegated, dict) and delegated.get("error"):
        return delegated, str(delegated.get("error"))

    payload = None
    if isinstance(delegated, dict):
        payload = _parse_mcp_result(delegated.get("result"))
        if payload is None:
            payload = delegated
    else:
        payload = delegated

    return payload, None


async def _server_side_agent_chat(args: dict, source: str = "webui", client_id: str | None = None) -> dict:
    """Run the agent tool-call loop at the proxy layer.

    Instead of forwarding to the capsule's monolithic agent_chat,
    this function:
    1. Calls invoke_slot with messages to get ONE model response
    2. Parses the tool call JSON
    3. Executes the tool individually (with full activity broadcasting)
    4. Feeds the result back to the model
    5. Repeats until final_answer or max_iterations

    Every step is broadcast to activity-stream SSE in real time.
    """
    import uuid as _uuid

    slot = int(args.get("slot", 0))
    message = str(args.get("message", "")).strip()
    max_iterations = int(args.get("max_iterations", 5))
    max_tokens = int(args.get("max_tokens", 0)) or 2048
    reset = bool(args.get("reset", False))
    session_id = str(args.get("session_id", "")).strip()
    granted_tools = args.get("granted_tools")

    if not message:
        return {"error": "message is required"}

    # ── Session management ──
    if not session_id:
        session_id = f"agent_chat:{slot}:{_uuid.uuid4().hex[:10]}"
    if reset and session_id in _agent_sessions:
        del _agent_sessions[session_id]
    session = _agent_sessions.get(session_id)
    if not session:
        session = {
            "id": session_id,
            "slot": slot,
            "turns": [],
            "granted_tools": list(_AGENT_DEFAULT_GRANTED),
            "chat_messages": [],  # structured messages for the model
            "inbox": [],
        }
        _agent_sessions[session_id] = session

    if isinstance(granted_tools, list) and granted_tools:
        session["granted_tools"] = [str(t) for t in granted_tools if str(t).strip()]

    depth_in = args.get("_agent_depth", session.get("delegation_depth", 0))
    try:
        delegation_depth = int(depth_in)
    except Exception:
        delegation_depth = 0
    if delegation_depth < 0:
        delegation_depth = 0

    session["delegation_depth"] = delegation_depth
    session["parent_session_id"] = str(args.get("_parent_session_id", session.get("parent_session_id", "")) or "")
    session["source"] = source
    session["client_id"] = client_id
    _now_ms = int(time.time() * 1000)
    session["updated_ts"] = _now_ms
    if "last_active_ts" not in session:
        session["last_active_ts"] = _now_ms
    if not isinstance(session.get("inbox"), list):
        session["inbox"] = []
    _agent_sessions[session_id] = session

    granted = [t for t in session["granted_tools"] if t not in _AGENT_BLOCKED_TOOLS]
    if not granted:
        granted = list(_AGENT_DEFAULT_GRANTED)

    # ── Get slot info ──
    slot_info_raw = await _call_tool("slot_info", {"slot": slot})
    slot_info = _parse_mcp_result(slot_info_raw.get("result")) or {}
    slot_name = slot_info.get("name", f"slot_{slot}") if isinstance(slot_info, dict) else f"slot_{slot}"
    plugged = bool(slot_info.get("plugged")) if isinstance(slot_info, dict) else False
    if not plugged:
        return {"error": f"Slot {slot} is not plugged. Plug a model first."}

    session["active"] = True
    session["last_active_ts"] = int(time.time() * 1000)
    session["updated_ts"] = session["last_active_ts"]
    _agent_sessions[session_id] = session

    # ── Build system prompt ──
    tool_descriptions = await _get_tool_descriptions(granted)
    system_prompt = (
        f"You are {slot_name}, an AI agent in council slot {slot} of an Ouroboros capsule.\n"
        "You have access to ONLY the tools listed below.\n"
        "Respond with EXACTLY ONE JSON object per turn.\n\n"
        f"AVAILABLE TOOLS:\n{tool_descriptions}\n\n"
        "To call a tool, respond with:\n"
        '{"tool": "tool_name", "args": {"param": "value"}}\n\n'
        "When you have completed the task, respond with:\n"
        '{"final_answer": "your complete answer here"}\n\n'
        "Rules:\n"
        "- Call ONE tool at a time — never batch multiple calls\n"
        "- After EVERY tool result, evaluate: did it succeed? what did you learn? what should you do next?\n"
        "- If a tool failed, decide whether to retry, skip, or adjust approach\n"
        "- Use ONLY the tools listed above\n"
        "- For cross-slot autonomous work, prefer agent_delegate instead of inventing callback loops\n"
        "- Never invoke your own slot for delegation\n"
        "- You may receive [LIVE UPDATE] messages mid-run; incorporate them immediately\n"
        "- Always end with a final_answer that summarizes outcomes\n"
    )

    # ── Build/extend chat messages ──
    chat_messages = session.get("chat_messages", [])
    if not chat_messages:
        chat_messages = [{"role": "system", "content": system_prompt}]

    # Append user message
    session["turns"].append({"role": "user", "content": message, "ts": int(time.time() * 1000)})
    chat_messages.append({"role": "user", "content": message})

    # ── Agent loop ──
    tool_calls_log = []
    final_answer = None
    iterations_used = 0
    loop_start = time.time()

    _broadcast_activity(
        "agent_chat", args,
        {"_phase": "start", "state": "running", "session_id": session_id,
         "slot": slot, "name": slot_name, "max_iterations": max_iterations,
         "granted_tools_count": len(granted)},
        0, None, source=source, client_id=client_id,
    )

    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        step_start = time.time()

        # Deliver pending injected updates at the earliest safe boundary (between iterations).
        pending_updates = session.get("inbox") if isinstance(session.get("inbox"), list) else []
        if pending_updates:
            delivered = list(pending_updates)
            session["inbox"] = []
            delivered_count = 0
            for upd in delivered:
                if not isinstance(upd, dict):
                    continue
                upd_msg = str(upd.get("message", "") or "").strip()
                if not upd_msg:
                    continue
                upd_sender = str(upd.get("sender", "operator") or "operator").strip() or "operator"
                injected = f"[LIVE UPDATE from {upd_sender}] {upd_msg}"
                chat_messages.append({"role": "user", "content": injected})
                session.setdefault("turns", []).append({
                    "role": "inject",
                    "content": upd_msg,
                    "sender": upd_sender,
                    "ts": int(upd.get("ts") or int(time.time() * 1000)),
                })
                delivered_count += 1
            if delivered_count > 0:
                session["updated_ts"] = int(time.time() * 1000)
                _broadcast_activity(
                    "agent_chat_inject",
                    {
                        "session_id": session_id,
                        "slot": slot,
                        "delivered": delivered_count,
                        "iteration": iterations_used,
                        "_agent_session": session_id,
                        "_agent_caller_slot": slot,
                    },
                    {"_phase": "delivered", "delivered": delivered_count, "session_id": session_id},
                    0,
                    None,
                    source="agent-inner",
                    client_id=client_id,
                )

        # Nudge on last iteration
        if iteration == max_iterations - 1:
            chat_messages.append({
                "role": "user",
                "content": 'This is your LAST iteration. You MUST respond with {"final_answer": "your answer"} now.'
            })

        # ── Step 1: Call model via invoke_slot ──
        invoke_args = {
            "slot": slot,
            "text": message,
            "mode": "generate",
            "messages": chat_messages,
            "max_tokens": max_tokens,
        }
        try:
            model_raw = await _call_tool("invoke_slot", invoke_args)
            model_parsed = _parse_mcp_result(model_raw.get("result"))
        except Exception as e:
            final_answer = f"Model invocation failed at iteration {iterations_used}: {e}"
            break

        if not isinstance(model_parsed, dict):
            final_answer = f"Model returned non-dict at iteration {iterations_used}"
            break
        if model_parsed.get("error"):
            final_answer = f"Model error at iteration {iterations_used}: {model_parsed['error']}"
            break

        model_output = str(model_parsed.get("output", ""))

        # ── Empty response retry: nudge the model if it returned nothing ──
        if not model_output.strip() and iteration < max_iterations - 1:
            chat_messages.append({
                "role": "user",
                "content": (
                    "Your response was empty. You MUST respond with exactly one JSON object.\n"
                    'Either: {"tool": "tool_name", "args": {...}}\n'
                    'Or: {"final_answer": "your answer"}\n'
                    "Try again now."
                ),
            })
            _broadcast_activity(
                "agent_chat",
                {"_phase": "empty_retry", "iteration": iterations_used, "session_id": session_id, "slot": slot},
                {"content": [{"type": "text", "text": "Empty model response — retrying with nudge"}]},
                int((time.time() - step_start) * 1000), None,
                source="agent-inner", client_id=client_id,
            )
            continue

        step_ms = int((time.time() - step_start) * 1000)

        # Broadcast model reasoning step
        _broadcast_activity(
            "agent_chat",
            {
                "_phase": "reasoning",
                "iteration": iterations_used,
                "session_id": session_id,
                "_agent_session": session_id,
                "slot": slot,
                "_agent_caller_slot": slot,
                "_agent_caller_name": slot_name,
            },
            {"content": [{"type": "text", "text": json.dumps({
                "iteration": iterations_used,
                "model_output_preview": _doc_decode_result_text(model_output[:300]) if "__docv2__" in model_output[:300] else model_output[:300],
                "step_ms": step_ms,
            })}]},
            step_ms, None, source="agent-inner", client_id=client_id,
        )

        chat_messages.append({"role": "assistant", "content": model_output})

        # ── Step 2: Parse model output ──
        parsed = None
        if isinstance(model_output, str):
            stripped = model_output.strip()
            # Strip <think>...</think> reasoning blocks
            import re as _re_agent
            if "<think>" in stripped:
                stripped = _re_agent.sub(r"<think>[\s\S]*?</think>\s*", "", stripped).strip()
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                # Scan for first valid JSON object with tool/final_answer key
                decoder = json.JSONDecoder()
                scan = 0
                while scan < len(stripped):
                    pos = stripped.find("{", scan)
                    if pos == -1:
                        break
                    try:
                        obj, _ = decoder.raw_decode(stripped, pos)
                        if isinstance(obj, dict) and ("tool" in obj or "final_answer" in obj):
                            parsed = obj
                            break
                    except (json.JSONDecodeError, ValueError):
                        pass
                    scan = pos + 1

        # No valid JSON → treat raw output as final answer
        if parsed is None:
            final_answer = model_output.strip() if model_output.strip() else "Model returned empty response."
            break

        # ── Check for final_answer ──
        if "final_answer" in parsed:
            final_answer = parsed["final_answer"]
            break

        # ── Step 3: Execute tool call ──
        if "tool" in parsed:
            called_tool = str(parsed["tool"]).strip()
            called_args = parsed.get("args", {})
            if not isinstance(called_args, dict):
                try:
                    called_args = json.loads(str(called_args)) if isinstance(called_args, str) else {}
                except Exception:
                    called_args = {}

            # Optional universal indirection: call(tool_name, args)
            if called_tool == "call":
                _inner_tool = ""
                for _k in ("tool", "tool_name", "name"):
                    _v = called_args.get(_k)
                    if isinstance(_v, str) and _v.strip():
                        _inner_tool = _v.strip()
                        break
                _inner_args = called_args.get("args", called_args.get("arguments", {}))
                if not isinstance(_inner_args, dict):
                    _inner_args = {}
                if _inner_tool:
                    called_tool = _inner_tool
                    called_args = _inner_args

            # Validate tool is granted
            if called_tool not in granted:
                denial = f"Tool '{called_tool}' is NOT in your granted tools. Available: {', '.join(granted[:20])}"
                chat_messages.append({"role": "user", "content": denial})
                tool_calls_log.append({
                    "tool": called_tool, "args": called_args,
                    "result": "DENIED - not in granted_tools",
                    "iteration": iteration,
                })
                continue

            # Self-invocation guard
            if called_tool == "invoke_slot" and int(called_args.get("slot", -1)) == slot:
                guard_msg = f"Self-invocation blocked: invoke_slot(slot={slot}). Choose a different slot or use agent_delegate for structured cross-slot orchestration."
                chat_messages.append({"role": "user", "content": guard_msg})
                tool_calls_log.append({
                    "tool": called_tool, "args": called_args,
                    "result": "DENIED - " + guard_msg, "iteration": iteration,
                })
                continue

            # Normalize args for capsule execution (encoded keys) when needed.
            if called_tool in ("agent_delegate", "agent_chat_inject", "agent_chat_sessions"):
                normalized_args = dict(called_args)
            else:
                normalized_args = _normalize_proxy_tool_args(called_tool, called_args)
            # Keep human-readable args for display in broadcasts
            display_args = dict(called_args)
            display_args["_agent_session"] = session_id
            display_args["_agent_iteration"] = iterations_used
            display_args["_agent_caller_slot"] = slot
            display_args["_agent_caller_name"] = slot_name
            if called_tool in ("invoke_slot", "chat", "agent_chat", "generate", "classify", "agent_delegate", "agent_chat_inject"):
                try:
                    if called_args.get("slot") is not None:
                        display_args["_agent_target_slot"] = int(called_args.get("slot"))
                except Exception:
                    pass

            # ── Broadcast tool-call-start (human-readable args) ──
            _broadcast_activity(
                called_tool, display_args,
                {"_phase": "start", "state": "running",
                 "_agent_session": session_id, "_agent_iteration": iterations_used},
                0, None, source="agent-inner", client_id=client_id,
            )

            # ── Execute the tool (encoded args or local virtual tool) ──
            tool_start = time.time()
            try:
                if called_tool == "agent_chat_inject":
                    inject_payload = _agent_inject_message(
                        normalized_args,
                        source="agent-inner",
                        client_id=client_id,
                        caller_session_id=session_id,
                        caller_slot=slot,
                    )
                    tool_result = inject_payload
                    tool_error = inject_payload.get("error") if isinstance(inject_payload, dict) else None
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result is not None else ""
                elif called_tool == "agent_chat_sessions":
                    sess_payload = _agent_session_snapshot(normalized_args)
                    tool_result = sess_payload
                    tool_error = None
                    tool_result_str = json.dumps(tool_result, indent=2, default=str)
                elif called_tool == "agent_delegate":
                    tool_result, tool_error = await _agent_delegate_call(
                        caller_slot=slot,
                        caller_session_id=session_id,
                        caller_depth=delegation_depth,
                        called_args=normalized_args,
                        source="agent-inner",
                        client_id=client_id,
                    )
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result is not None else ""
                else:
                    tool_raw = await _call_tool(called_tool, normalized_args)
                    tool_result = _parse_mcp_result(tool_raw.get("result"))
                    tool_error = tool_raw.get("error") or (tool_result.get("error") if isinstance(tool_result, dict) else None)
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result else ""
            except Exception as e:
                tool_result = None
                tool_error = str(e)
                tool_result_str = f"ERROR: {e}"
            tool_ms = int((time.time() - tool_start) * 1000)

            # Decode encoded keys in result for display
            _display_result_str = tool_result_str
            if "__docv2__" in _display_result_str:
                _display_result_str = _doc_decode_result_text(_display_result_str)

            # ── Broadcast tool-call-end (decoded result) ──
            _broadcast_activity(
                called_tool, display_args,
                {"content": [{"type": "text", "text": _display_result_str[:2000]}]} if _display_result_str else None,
                tool_ms,
                str(tool_error) if tool_error else None,
                source="agent-inner", client_id=client_id,
            )

            # Log
            tool_calls_log.append({
                "tool": called_tool,
                "args": called_args,
                "result": tool_result_str[:500] if tool_result_str else "",
                "error": str(tool_error) if tool_error else None,
                "duration_ms": tool_ms,
                "iteration": iteration,
            })

            # Feed result back to model
            # Reorientation prompt: force the model to evaluate before proceeding
            _err_flag = f" ⚠ The tool returned an error." if tool_error else ""
            feedback = (
                f"TOOL RESULT [{called_tool}]:{_err_flag}\n"
                f"{tool_result_str}\n\n"
                f"EVALUATE: What did this result tell you? Did it succeed? "
                f"What is the next step toward completing the original task? "
                f"Respond with exactly one JSON: either a tool call or final_answer."
            )
            chat_messages.append({"role": "user", "content": feedback})
        else:
            # JSON but no tool or final_answer key
            final_answer = json.dumps(parsed, default=str)
            break

    if final_answer is None:
        final_answer = f"Agent reached max iterations ({max_iterations}) without final answer."

    total_ms = int((time.time() - loop_start) * 1000)

    # ── Save session state ──
    session["turns"].append({
        "role": "assistant",
        "content": str(final_answer) if isinstance(final_answer, str) else json.dumps(final_answer, default=str),
        "ts": int(time.time() * 1000),
    })
    session["chat_messages"] = chat_messages
    session["active"] = False
    session["updated_ts"] = int(time.time() * 1000)
    _agent_sessions[session_id] = session

    agent_result = {
        "final_answer": final_answer,
        "iterations": iterations_used,
        "tool_calls": tool_calls_log,
        "slot": slot,
        "name": slot_name,
        "duration_ms": total_ms,
    }

    envelope = {
        "session_id": session_id,
        "slot": slot,
        "result": agent_result,
        "blocked_tools": sorted(list(_AGENT_BLOCKED_TOOLS)),
        "turn_count": len(session.get("turns", [])),
        "history": session.get("turns", [])[-12:],
        "delegation_depth": delegation_depth,
        "parent_session_id": session.get("parent_session_id"),
        "pending_messages": len(session.get("inbox") or []),
    }

    # Wrap in MCP-compatible envelope
    result_text = json.dumps(envelope, indent=2, default=str)
    return {
        "result": {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        }
    }


async def _postprocess_tool_result(tool_name: str, args: dict, result: dict) -> dict:
    """Intercept and fix known capsule issues at the proxy layer.

    This lets us patch bugs without modifying the capsule backend.
    """
    parsed = _parse_mcp_result(result.get("result"))

    # --- Resolve cached stubs for multi-slot tools that need postprocessor retry ---
    # The capsule caches large results BEFORE the proxy sees them. For tools
    # like broadcast/all_slots/debate, the cached stub has no responses array,
    # so the retry logic can't run. Resolve the cache first.
    _CACHE_RESOLVE_TOOLS = ("broadcast", "all_slots", "debate", "compare", "pipe", "chain")
    if tool_name in _CACHE_RESOLVE_TOOLS and isinstance(parsed, dict) and parsed.get("_cached"):
        try:
            _cr = await _call_tool("get_cached", {"cache_id": str(parsed["_cached"])})
            _cr_parsed = _parse_mcp_result(_cr.get("result"))
            if _cr_parsed and isinstance(_cr_parsed, dict):
                parsed = _cr_parsed
                # Replace the result so downstream gets the full data
                result = {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
        except Exception:
            pass  # couldn't resolve cache — continue with stub

    def _decode_doc_in_text(value: str) -> str:
        import re as _re_doc
        if not isinstance(value, str) or "__docv2__" not in value:
            return value

        def _repl(m):
            token = m.group(0)
            return _doc_decode_key(token)

        return _re_doc.sub(r"__docv2__[^\s\",'}]+(?:__k)?", _repl, value)

    def _decode_doc_fields(obj):
        if isinstance(obj, dict):
            for key_field in ("key", "source_key", "restored_key", "pattern", "removed", "path", "old_path", "new_path", "source_path", "dest_path", "restored_path"):
                if isinstance(obj.get(key_field), str):
                    obj[key_field] = _doc_decode_key(obj[key_field])
            for ck_field in ("checkpoint_key", "from_checkpoint", "to_checkpoint", "to_target", "backup_checkpoint"):
                if isinstance(obj.get(ck_field), str):
                    obj[ck_field] = _doc_decode_checkpoint_key(obj[ck_field])
            if isinstance(obj.get("available"), list):
                obj["available"] = [(_doc_decode_key(v) if isinstance(v, str) else v) for v in obj["available"]]
            if isinstance(obj.get("error"), str):
                obj["error"] = _decode_doc_in_text(obj["error"])
            for v in list(obj.values()):
                _decode_doc_fields(v)
        elif isinstance(obj, list):
            for item in obj:
                _decode_doc_fields(item)

    # Decode virtualized doc keys back to logical slash-path keys.
    if (tool_name.startswith("bag_") or tool_name.startswith("file_")) and isinstance(parsed, (dict, list)):
        _decode_doc_fields(parsed)
        result = {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # bag_tree/file_tree fallback: synthesize from bag_list_docs when capsule returns empty tree.
    # C5 fix: also trigger for non-empty prefix (scoped subtrees), not just root.
    if tool_name in ("bag_tree", "file_tree") and isinstance(parsed, dict):
        tree = parsed.get("tree")
        doc_count = int(parsed.get("document_count", 0) or 0)
        req_prefix = str(args.get("prefix", args.get("path", "")) or "")
        if (not isinstance(tree, dict) or not tree) and doc_count == 0:
            try:
                ls_args = {
                    "prefix": "",
                    "include_checkpoints": bool(args.get("include_checkpoints", False)),
                    "limit": 500,
                }
                ls_raw = await _call_tool("bag_list_docs", _normalize_proxy_tool_args("bag_list_docs", ls_args))
                ls_parsed = _parse_mcp_result(ls_raw.get("result"))
                if isinstance(ls_parsed, dict) and ls_parsed.get("_cached"):
                    _ls_cache = await _call_tool("get_cached", {"cache_id": str(ls_parsed.get("_cached"))})
                    _ls_cache_parsed = _parse_mcp_result(_ls_cache.get("result"))
                    if isinstance(_ls_cache_parsed, dict):
                        ls_parsed = _ls_cache_parsed
                items = ls_parsed.get("items", []) if isinstance(ls_parsed, dict) else []
                # C5 fix: filter items to prefix BEFORE building tree
                _pfx_norm = req_prefix.strip("/") + "/" if req_prefix.strip("/") else ""
                matching_items = []
                built = {}
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    k = _doc_decode_key(str(it.get("key", "") or ""))
                    if not k:
                        continue
                    # When prefix is set, only include keys under that prefix
                    if _pfx_norm and not k.startswith(_pfx_norm) and k != req_prefix.strip("/"):
                        continue
                    matching_items.append(k)
                    # Build tree relative to the prefix so scoped view makes sense
                    rel_key = k[len(_pfx_norm):] if _pfx_norm else k
                    parts = [p for p in rel_key.split("/") if p]
                    if not parts:
                        continue
                    cur = built
                    for idx, part in enumerate(parts):
                        if part not in cur:
                            cur[part] = {}
                        node = cur[part]
                        if idx == len(parts) - 1:
                            node.setdefault("_items", [])
                            node["_items"].append(k)
                        cur = node
                parsed["tree"] = built
                parsed["document_count"] = len(matching_items)
                parsed["prefix"] = req_prefix
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

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

    # --- Helper: detect retryable slot errors (embedding 404, system role, etc.) ---
    def _is_retryable_slot_error(err_str: str) -> bool:
        if not err_str:
            return False
        markers = ("Remote embedding failed", "HTTP Error 404", "System role not supported",
                    "not callable", "is not callable", "embedding failed")
        return any(m.lower() in err_str.lower() for m in markers)

    # --- Helper: retry a slot via generate mode ---
    async def _retry_slot_generate(slot_idx: int, text: str, max_tokens: int = 300) -> str | None:
        """Robust generation retry for flaky providers.

        Some inference providers intermittently return empty output with no error.
        Try multiple generation prompts/tokens, then fallback through `chat`.
        """
        prompts = [
            text,
            (text + "\n\nRespond with a concise direct answer."),
            ("Answer briefly and directly:\n" + text),
        ]
        token_budgets = [max_tokens, max(max_tokens, 512), max(max_tokens, 768)]

        for p in prompts:
            for mt in token_budgets:
                try:
                    retry = await _call_tool("invoke_slot", {
                        "slot": int(slot_idx), "text": p, "mode": "generate", "max_tokens": int(mt),
                    })
                    retry_parsed = _parse_mcp_result(retry.get("result"))
                    if retry_parsed and isinstance(retry_parsed, dict):
                        out = str(retry_parsed.get("output", "") or "").strip()
                        if out:
                            # Ignore provider error strings disguised as output
                            if out.lower().startswith("[remote provider error"):
                                continue
                            # Strip think blocks when present
                            if "<think>" in out:
                                import re as _re_try
                                cleaned = _re_try.sub(r"<think>[\s\S]*?</think>\s*", "", out).strip()
                                if cleaned:
                                    out = cleaned
                                else:
                                    # unclosed/think-only response, retry
                                    continue
                            if out:
                                return out
                except Exception:
                    pass

        # Fallback through chat path (server has empty-response retry there)
        try:
            ch = await _call_tool("chat", {"slot": int(slot_idx), "message": text})
            ch_parsed = _parse_mcp_result(ch.get("result"))
            if isinstance(ch_parsed, dict):
                out = str(ch_parsed.get("response", "") or "").strip()
                if out:
                    if out.lower().startswith("[remote provider error"):
                        return None
                    return out
        except Exception:
            pass

        return None

    # --- Fix compare: retry slots that fail with embedding/system-role errors ---
    if tool_name == "compare" and isinstance(parsed, dict):
        comparisons = parsed.get("comparisons", [])
        patched = False
        for entry in comparisons:
            err = str(entry.get("error", ""))
            if entry.get("status") == "error" and _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    out = await _retry_slot_generate(slot_idx, args.get("input_text", ""))
                    if out:
                        entry["type"] = "generation"
                        entry["output"] = out
                        entry.pop("error", None)
                        entry["status"] = "ok"
                        entry["note"] = "retried via generate mode"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix debate: retry slots that fail with embedding/system-role errors ---
    if tool_name == "debate" and isinstance(parsed, dict):
        transcript = parsed.get("transcript", [])
        patched = False
        for rnd in transcript:
            for entry in rnd.get("entries", []):
                err = str(entry.get("error", ""))
                if _is_retryable_slot_error(err):
                    councilor = entry.get("councilor", "")
                    # Find slot index by councilor name (resolve cache if needed)
                    slot_idx = None
                    try:
                        slots_result = await _call_tool("list_slots", {})
                        slots_parsed = _parse_mcp_result(slots_result.get("result"))
                        if isinstance(slots_parsed, dict) and slots_parsed.get("_cached"):
                            _ls_cr = await _call_tool("get_cached", {"cache_id": str(slots_parsed["_cached"])})
                            slots_parsed = _parse_mcp_result(_ls_cr.get("result")) or slots_parsed
                        if isinstance(slots_parsed, dict):
                            for s in slots_parsed.get("slots", []):
                                if s.get("name") == councilor and s.get("plugged"):
                                    slot_idx = s.get("index")
                                    break
                    except Exception:
                        pass
                    if slot_idx is not None:
                        topic = args.get("text", "")
                        prompt = f"Debate topic: {topic}\nProvide your position in a clear paragraph."
                        out = await _retry_slot_generate(slot_idx, prompt, 400)
                        if out:
                            entry["response"] = out
                            entry.pop("error", None)
                            entry["note"] = "retried via generate mode"
                            patched = True
                    else:
                        entry["response"] = f"[Skipped: {err}]"
                        entry.pop("error", None)
                        entry["type"] = "skipped"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix broadcast/all_slots: retry slots that fail with embedding errors ---
    if tool_name in ("broadcast", "all_slots") and isinstance(parsed, dict):
        responses = parsed.get("responses", [])
        patched = False
        for entry in responses:
            err = str(entry.get("error", ""))
            if _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    text = args.get("message", "") or args.get("text", "")
                    out = await _retry_slot_generate(slot_idx, text)
                    if out:
                        entry["response"] = out
                        entry.pop("error", None)
                        entry.pop("status", None)
                        entry["note"] = "retried via generate mode"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix pipe/chain: retry slots that fail with embedding errors ---
    if tool_name in ("pipe", "chain") and isinstance(parsed, dict):
        trace = parsed.get("trace", [])
        patched = False
        prev_output = args.get("input_text", "") or args.get("text", "")
        for entry in trace:
            if entry.get("slot") == "input":
                prev_output = entry.get("output", "") or entry.get("value", "") or prev_output
                continue
            err = str(entry.get("error", ""))
            if _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    out = await _retry_slot_generate(slot_idx, prev_output)
                    if out:
                        entry["output"] = out
                        entry.pop("error", None)
                        entry.pop("status", None)
                        entry["note"] = "retried via generate mode"
                        prev_output = out
                        patched = True
                    else:
                        prev_output = prev_output  # keep previous for next slot
            elif entry.get("output"):
                prev_output = entry["output"]
        if patched:
            # Update final_output for pipe
            if "final_output" in parsed and trace:
                last_ok = [e for e in trace if e.get("output") and e.get("slot") != "input"]
                if last_ok:
                    parsed["final_output"] = last_ok[-1]["output"]
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix agent_chat: resolve cached responses for inner tool call broadcasting ---
    if tool_name == "agent_chat" and isinstance(parsed, dict):
        _cache_id = parsed.get("_cached")
        _full_parsed = parsed  # May be replaced with the resolved cache content below
        if _cache_id:
            try:
                _cache_resp = await _call_tool("get_cached", {"cache_id": str(_cache_id)})
                _cache_data = _parse_mcp_result((_cache_resp or {}).get("result"))
                if isinstance(_cache_data, dict) and ("result" in _cache_data or "tool_calls" in _cache_data):
                    _full_parsed = _cache_data
                    print(f"[AGENT-INNER] Resolved cache {_cache_id}: keys={list(_full_parsed.keys())[:8]}")
            except Exception as _ce:
                print(f"[AGENT-INNER] Cache resolve failed for {_cache_id}: {_ce}")

        # Extract inner tool_calls and broadcast each one to activity feed
        _inner = _full_parsed.get("result") if isinstance(_full_parsed.get("result"), dict) else _full_parsed
        _inner_tc = _inner.get("tool_calls", []) if isinstance(_inner, dict) else []
        if isinstance(_inner_tc, list) and len(_inner_tc) > 0:
            _slot_idx = _inner.get("slot") if isinstance(_inner, dict) else None
            _slot_name = _inner.get("name", "") if isinstance(_inner, dict) else ""
            print(f"[AGENT-INNER] Broadcasting {len(_inner_tc)} inner tool calls from agent_chat (slot={_slot_idx}/{_slot_name}, cached={bool(_cache_id)})")
            for _i, _tc_entry in enumerate(_inner_tc):
                if not isinstance(_tc_entry, dict):
                    continue
                _tc_tool = _tc_entry.get("tool", "unknown")
                _tc_args = _tc_entry.get("args", {})
                _tc_result_str = _tc_entry.get("result", "")
                _tc_error = _tc_entry.get("error")
                _tc_iter = _tc_entry.get("iteration", _i)
                _tc_content = {"content": [{"type": "text", "text": _tc_result_str if isinstance(_tc_result_str, str) else json.dumps(_tc_result_str)}]}
                _broadcast_activity(
                    _tc_tool, _tc_args, _tc_content, 0,
                    str(_tc_error) if _tc_error else None,
                    source="agent-inner",
                    client_id=None,
                )
                print(f"[AGENT-INNER] Broadcast {_i+1}/{len(_inner_tc)}: {_tc_tool} (iter={_tc_iter})")

        _result = _full_parsed.get("result") if isinstance(_full_parsed.get("result"), dict) else _full_parsed
        _fa = str(_result.get("final_answer", "")).strip() if isinstance(_result, dict) else ""
        _tc = _result.get("tool_calls", []) if isinstance(_result, dict) else []

        # --- Strip <think>...</think> reasoning blocks from final_answer ---
        # DeepSeek-R1 and similar reasoning models wrap their chain-of-thought
        # in <think> tags. Strip it to get the actual answer.
        import re as _re
        if _fa and "<think>" in _fa:
            _stripped = _re.sub(r"<think>[\s\S]*?</think>\s*", "", _fa).strip()
            if not _stripped and "<think>" in _fa:
                # The <think> block was never closed (truncated) — everything is thinking
                # Try to extract any content after an unclosed </think> or after the block
                _after_think = _re.split(r"</think>\s*", _fa, maxsplit=1)
                if len(_after_think) > 1:
                    _stripped = _after_think[-1].strip()
            if _stripped:
                _fa = _stripped
                _result["final_answer"] = _fa
                _result["_think_stripped"] = True
            else:
                # Entire response was thinking — treat as empty for synthesis
                _fa = ""
                _result["final_answer"] = ""
                _result["_think_stripped"] = True

        # --- Unwrap double-nested JSON in final_answer ---
        # GLM-5 sometimes wraps its answer in {"final_answer": "..."} inside the
        # already-extracted final_answer field.
        if _fa and _fa.startswith("{"):
            try:
                _inner = json.loads(_fa)
                if isinstance(_inner, dict) and "final_answer" in _inner:
                    _fa = str(_inner["final_answer"]).strip()
                    _result["final_answer"] = _fa
                    _result["_unwrapped"] = True
            except (json.JSONDecodeError, ValueError):
                pass  # Not valid JSON — leave as-is

        _empty_markers = (
            "", "model returned an empty response.", "model returned an empty response",
            "no response received", "no response received.",
        )
        if _fa.lower() in _empty_markers and isinstance(_tc, list) and len(_tc) > 0:
            # Synthesize a summary from the tool call results
            summary_parts = []
            for tc in _tc:
                if not isinstance(tc, dict):
                    continue
                t_name = tc.get("tool", "unknown")
                t_result = tc.get("result", "")
                t_error = tc.get("error")
                if t_error:
                    summary_parts.append(f"[{t_name}] ERROR: {t_error}")
                elif t_result:
                    preview = str(t_result)[:600]
                    if len(str(t_result)) > 600:
                        preview += "..."
                    summary_parts.append(f"[{t_name}] {preview}")
            if summary_parts:
                synthesized = "Tool results (model failed to synthesize):\n\n" + "\n\n".join(summary_parts)
                _result["final_answer"] = synthesized
                _result["_synthesized"] = True
                if "result" in parsed and isinstance(parsed["result"], dict):
                    parsed["result"] = _result
                else:
                    parsed = _result
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix invoke_slot/generate: strip <think> blocks from output ---
    if tool_name in ("invoke_slot", "generate") and isinstance(parsed, dict):
        import re as _re_gen
        _out = str(parsed.get("output", "")).strip()
        if _out and "<think>" in _out:
            _clean = _re_gen.sub(r"<think>[\s\S]*?</think>\s*", "", _out).strip()
            if not _clean:
                _after = _re_gen.split(r"</think>\s*", _out, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean and not _clean.lower().startswith("[remote provider error"):
                parsed["output"] = _clean
                parsed["_think_stripped"] = True
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            else:
                # think-only or error-like output; try chat fallback for invoke_slot
                if tool_name == "invoke_slot" and args.get("slot") is not None and args.get("text"):
                    try:
                        _cf = await _call_tool("chat", {"slot": int(args.get("slot", 0)), "message": str(args.get("text", ""))})
                        _cfp = _parse_mcp_result(_cf.get("result"))
                        if isinstance(_cfp, dict):
                            _resp = str(_cfp.get("response", "")).strip()
                            if _resp and not _resp.lower().startswith("[remote provider error"):
                                parsed["output"] = _resp
                                parsed["_fallback"] = "chat_after_think_only"
                                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
                    except Exception:
                        pass

    # --- Fix chat: strip <think> blocks and retry empty responses ---
    if tool_name == "chat" and isinstance(parsed, dict):
        _response = str(parsed.get("response", "")).strip()
        # Strip <think> blocks from chat responses
        if _response and "<think>" in _response:
            import re as _re_chat
            _clean = _re_chat.sub(r"<think>[\s\S]*?</think>\s*", "", _response).strip()
            if not _clean:
                _after = _re_chat.split(r"</think>\s*", _response, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean:
                parsed["response"] = _clean
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            else:
                _response = ""  # fall through to empty-response retry
        if not _response and args.get("message"):
            _slot = args.get("slot", 0)
            try:
                retry = await _call_tool("invoke_slot", {
                    "slot": int(_slot),
                    "text": str(args["message"]),
                    "mode": "generate",
                    "max_tokens": 512,
                })
                retry_parsed = _parse_mcp_result(retry.get("result"))
                if retry_parsed and isinstance(retry_parsed, dict):
                    _output = retry_parsed.get("output", "")
                    if _output:
                        parsed["response"] = _output
                        parsed["_fallback"] = "invoke_slot_generate"
                        return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

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

    raw_body = dict(body) if isinstance(body, dict) else {}

    # Normalise workflow definitions before they reach the capsule
    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        body["definition"] = _normalize_workflow_nodes(body["definition"])

    body = _normalize_proxy_tool_args(tool_name, body if isinstance(body, dict) else {})

    # Optional reserved body key for callers that can't set headers/query.
    body_source = _normalize_activity_source(body.pop("__source", None) if isinstance(body, dict) else None)
    source = body_source or _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)

    # Local virtual orchestrator tools (proxy-side; not forwarded to capsule).
    if tool_name == "agent_chat_inject":
        payload = _agent_inject_message(body if isinstance(body, dict) else {}, source=source, client_id=client_id)
        err = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, err, source=source, client_id=client_id)
        if err:
            return JSONResponse(status_code=404, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "agent_chat_sessions":
        payload = _agent_session_snapshot(body if isinstance(body, dict) else {})
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "agent_delegate":
        raw = body if isinstance(body, dict) else {}
        try:
            caller_slot = int(raw.get("caller_slot", -1))
        except Exception:
            caller_slot = -1
        caller_session_id = str(raw.get("caller_session_id", "external") or "external")
        try:
            caller_depth = int(raw.get("_agent_depth", 0) or 0)
        except Exception:
            caller_depth = 0
        started = time.time()
        payload, err = await _agent_delegate_call(caller_slot, caller_session_id, caller_depth, raw, source=source, client_id=client_id)
        duration_ms = int((time.time() - started) * 1000)
        out = payload if isinstance(payload, dict) else {"result": payload}
        if err:
            if isinstance(out, dict):
                out.setdefault("error", err)
            _broadcast_activity(tool_name, raw, out, duration_ms, err, source=source, client_id=client_id)
            return JSONResponse(status_code=409, content=out)
        _broadcast_activity(tool_name, raw, out, duration_ms, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}}

    slot_guard = await _slot_ready_guard(tool_name, body if isinstance(body, dict) else {})
    if slot_guard:
        error_msg = slot_guard.get("error") or f"Slot readiness guard blocked {tool_name}"
        payload = {"error": error_msg, "slot_guard": slot_guard}
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, error_msg, source=source, client_id=client_id)
        return JSONResponse(status_code=409, content=payload)

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
            _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, error_msg, source=source, client_id=client_id)
            return JSONResponse(status_code=429, content=payload)

    call_args = body if isinstance(body, dict) else {}
    tool_name_effective = tool_name

    # FelixBag doc-ops shim: treat bag_put on virtualized doc keys as document write.
    if tool_name == "bag_put" and isinstance(call_args.get("key"), str) and _doc_is_encoded_key(call_args.get("key", "")):
        tool_name_effective = "bag_induct"
        call_args = {
            "key": call_args.get("key"),
            "content": str(call_args.get("value", "")),
            "item_type": "document",
        }

    # FelixBag delete shim: key-delete on virtualized keys should remove exact key family.
    if tool_name == "bag_forget" and isinstance(call_args.get("key"), str) and _doc_is_encoded_key(call_args.get("key", "")) and not call_args.get("pattern"):
        call_args = {"pattern": str(call_args.get("key", ""))}

    # Slot execution guard: reject overlapping heavy calls on same slot.
    claim, busy_guard = await _claim_slot_execution(tool_name, call_args, source, client_id)
    if busy_guard:
        error_msg = busy_guard.get("error") or f"Slot busy while calling {tool_name}"
        payload = {"error": error_msg, "slot_busy": busy_guard}
        _broadcast_activity(tool_name, call_args, payload, 0, error_msg, source=source, client_id=client_id)
        return JSONResponse(status_code=409, content=payload)

    if tool_name in _LIVE_START_TOOLS:
        _broadcast_activity(
            tool_name,
            call_args,
            {"_phase": "start", "state": "running"},
            0,
            None,
            source=source,
            client_id=client_id,
        )

    # ── Server-side agent orchestration ──────────────────────────
    # Intercept agent_chat: run the tool-call loop HERE so each
    # step is individually visible via activity-stream SSE.
    # The capsule's monolithic agent_chat is bypassed entirely.
    if tool_name == "agent_chat":
        try:
            orchestrated = await _server_side_agent_chat(call_args, source=source, client_id=client_id)
            duration_ms = int((time.time() - (time.time())) * 0)  # per-step durations already broadcast
            _broadcast_activity("agent_chat", call_args, orchestrated.get("result"), 0, orchestrated.get("error"), source=source, client_id=client_id)
            if orchestrated.get("error"):
                return JSONResponse(status_code=503, content=orchestrated)
            return orchestrated
        finally:
            await _release_slot_execution(claim)

    # Auto-reset capsule chat session when slot changes to prevent cross-slot bleed.
    # The capsule's `chat` tool shares a single conversation — without reset,
    # slot 1 sees slot 0's history and responds with the wrong identity.
    global _last_chat_slot
    if tool_name == "chat":
        _chat_slot = int(call_args.get("slot", 0))
        if _last_chat_slot is not None and _last_chat_slot != _chat_slot:
            try:
                await _call_tool("chat_reset", {})
            except Exception:
                pass
        _last_chat_slot = _chat_slot

    start = time.time()
    try:
        result = await _call_tool(tool_name_effective, call_args)

        # Fallback for legacy/raw slash keys when virtualized key is missing.
        if tool_name in ("bag_get", "bag_read_doc", "file_read", "file_info"):
            raw_key = raw_body.get("key") if isinstance(raw_body, dict) else None
            if not isinstance(raw_key, str) or not raw_key:
                raw_key = raw_body.get("path") if isinstance(raw_body, dict) else None
            enc_key = call_args.get("key") if isinstance(call_args, dict) else None
            if not isinstance(enc_key, str) or not enc_key:
                enc_key = call_args.get("path") if isinstance(call_args, dict) else None
            if isinstance(raw_key, str) and isinstance(enc_key, str) and _doc_is_encoded_key(enc_key):
                probe = _parse_mcp_result(result.get("result"))
                probe_err = str(result.get("error") or (probe.get("error") if isinstance(probe, dict) else "") or "")
                if "not found" in probe_err.lower():
                    retry_args = dict(call_args)
                    if tool_name in ("file_read", "file_info"):
                        retry_args.pop("key", None)
                        retry_args["path"] = raw_key
                    else:
                        retry_args["key"] = raw_key
                    retry = await _call_tool(tool_name_effective, retry_args)
                    retry_probe = _parse_mcp_result(retry.get("result"))
                    retry_err = str(retry.get("error") or (retry_probe.get("error") if isinstance(retry_probe, dict) else "") or "")
                    if not retry_err:
                        result = retry

        # Post-process to fix known capsule bugs at proxy layer
        result = await _postprocess_tool_result(tool_name, call_args, result)
        duration_ms = int((time.time() - start) * 1000)
        error_str = result.get("error") if isinstance(result.get("error"), str) else None
        # Tag hydration calls so the frontend SSE listener can filter them
        _broadcast_activity(tool_name, call_args, result.get("result"), duration_ms, error_str, source=source, client_id=client_id)
        _broadcast_agent_inner_calls(tool_name, result.get("result"), duration_ms, source=source, client_id=client_id)
        if error_str:
            return JSONResponse(status_code=503, content=result)
        if capacity_guard and isinstance(result, dict):
            result["capacity_guard"] = capacity_guard
        return result
    finally:
        await _release_slot_execution(claim)


@app.get("/api/tools")
async def list_tools_route(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    start = time.time()
    result = await _list_tools()
    duration_ms = int((time.time() - start) * 1000)
    error_str = result.get("error") if isinstance(result.get("error"), str) else None
    _broadcast_activity("list_tools", {}, result.get("result"), duration_ms, error_str, source=source, client_id=client_id)
    if "error" in result and isinstance(result["error"], str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/health")
async def health(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
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
    _broadcast_activity("api_health", {}, {"content": [{"type": "text", "text": json.dumps(payload)}]}, duration_ms, None, source=source, client_id=client_id)
    return payload


@app.get("/api/runtime/capacity")
async def runtime_capacity(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
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
        client_id=client_id,
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


@app.get("/api/agent_chat/sessions")
async def api_agent_chat_sessions(request: Request, slot: int | None = None, active_only: bool = False, limit: int = 50):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    args = {"active_only": bool(active_only), "limit": int(limit)}
    if slot is not None:
        args["slot"] = int(slot)
    payload = _agent_session_snapshot(args)
    _broadcast_activity("agent_chat_sessions", args, payload, 0, None, source=source, client_id=client_id)
    return payload


@app.post("/api/agent_chat/inject")
async def api_agent_chat_inject(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    source = _normalize_activity_source(body.pop("__source", None)) or _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    payload = _agent_inject_message(body, source=source, client_id=client_id)
    err = payload.get("error") if isinstance(payload, dict) else "inject failed"
    _broadcast_activity("agent_chat_inject", body, payload, 0, err if isinstance(err, str) and err else None, source=source, client_id=client_id)
    if isinstance(payload, dict) and payload.get("error"):
        return JSONResponse(status_code=404, content=payload)
    return payload


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


async def _hf_router_proxy_impl(request: Request, subpath: str, provider: str = "auto"):
    token_hint = request.query_params.get("token") or request.query_params.get("hf_token")
    token = _hf_router_token(token_hint)
    if not token:
        return JSONResponse(
            status_code=401,
            content={
                "error": "HF token not configured",
                "hint": "Set HF_TOKEN in Space secrets (or pass hf_token query for direct testing).",
            },
        )

    target = f"{HF_ROUTER_BASE}/v1/{str(subpath or '').lstrip('/')}"

    fwd_params = dict(request.query_params)
    fwd_params.pop("token", None)
    fwd_params.pop("hf_token", None)

    headers = {"Accept": request.headers.get("accept", "application/json")}
    headers["Authorization"] = f"Bearer {token}"

    body_bytes = await request.body()
    method = request.method.upper()

    if method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                if provider and provider != "auto" and "provider" not in payload:
                    payload["provider"] = provider
                model_hint = fwd_params.get("model")
                if model_hint and not payload.get("model"):
                    payload["model"] = model_hint
                body_bytes = json.dumps(payload).encode("utf-8")
                headers["Content-Type"] = "application/json"
        elif content_type:
            headers["Content-Type"] = content_type

    timeout = 120.0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method,
                target,
                params=fwd_params,
                content=body_bytes if method in ("POST", "PUT", "PATCH") else None,
                headers=headers,
            )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"HF router proxy failed: {e}"})

    out_headers = {}
    ct = resp.headers.get("content-type")
    if ct:
        out_headers["Content-Type"] = ct
    rid = resp.headers.get("x-request-id")
    if rid:
        out_headers["x-request-id"] = rid
    xprov = resp.headers.get("x-inference-provider")
    if xprov:
        out_headers["x-inference-provider"] = xprov

    return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)


@app.api_route("/hf-router/v1/{subpath:path}", methods=["GET", "POST"])
async def hf_router_proxy_default(subpath: str, request: Request):
    return await _hf_router_proxy_impl(request, subpath, provider="auto")


@app.api_route("/hf-router/{provider}/v1/{subpath:path}", methods=["GET", "POST"])
async def hf_router_proxy_provider(provider: str, subpath: str, request: Request):
    return await _hf_router_proxy_impl(request, subpath, provider=provider)


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
                                                source="external", client_id=pending.get("client_id")
                                            )
                                            # Cache-aware inner tool call broadcasting for agent_chat
                                            if pending["tool"] == "agent_chat" and rpc_result:
                                                _ac_parsed = _parse_mcp_result(rpc_result)
                                                _ac_full = _ac_parsed
                                                if isinstance(_ac_parsed, dict) and _ac_parsed.get("_cached"):
                                                    try:
                                                        _ac_cache = await _call_tool("get_cached", {"cache_id": str(_ac_parsed["_cached"])})
                                                        _ac_resolved = _parse_mcp_result((_ac_cache or {}).get("result"))
                                                        if isinstance(_ac_resolved, dict) and ("result" in _ac_resolved or "tool_calls" in _ac_resolved):
                                                            _ac_full = _ac_resolved
                                                            print(f"[AGENT-INNER/SSE] Resolved cache {_ac_parsed['_cached']}")
                                                    except Exception:
                                                        pass
                                                _ac_inner = _ac_full.get("result") if isinstance(_ac_full, dict) and isinstance(_ac_full.get("result"), dict) else _ac_full
                                                _ac_tc = _ac_inner.get("tool_calls", []) if isinstance(_ac_inner, dict) else []
                                                for _aci, _ac_entry in enumerate(_ac_tc):
                                                    if not isinstance(_ac_entry, dict):
                                                        continue
                                                    _broadcast_activity(
                                                        _ac_entry.get("tool", "unknown"),
                                                        _ac_entry.get("args", {}),
                                                        {"content": [{"type": "text", "text": str(_ac_entry.get("result", ""))}]},
                                                        0, str(_ac_entry.get("error")) if _ac_entry.get("error") else None,
                                                        source="agent-inner", client_id=pending.get("client_id"),
                                                    )
                                                    print(f"[AGENT-INNER/SSE] Broadcast {_aci+1}/{len(_ac_tc)}: {_ac_entry.get('tool')}")
                                            else:
                                                _broadcast_agent_inner_calls(pending["tool"], rpc_result, duration_ms, source="external", client_id=pending.get("client_id"))
                                            await _release_slot_execution(pending.get("claim"))
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
                stale = _pending_external_calls.pop(k, None)
                if isinstance(stale, dict):
                    await _release_slot_execution(stale.get("claim"))

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
    _mcp_client_id = _extract_client_id(request)
    print(f"[MCP-PROXY] POST /mcp/message(s) session_id={session_id} client={_mcp_client_id} len={len(body)}")

    # Extract tools/call payload(s) for activity tracking (single or batch).
    rpc_calls = [
        {"tool": tool, "args": args, "rpc_id": rpc_id}
        for tool, args, rpc_id in _parse_rpc_tool_calls(body)
    ]

    # Slot readiness guard for external MCP calls (prevents hidden queueing
    # of invoke/chat calls while a model is still plugging).
    blocked_calls = []
    for call in rpc_calls:
        sg = await _slot_ready_guard(call.get("tool") or "", call.get("args") if isinstance(call, dict) else {})
        if sg:
            blocked_calls.append((call, sg))

    if blocked_calls:
        duration_ms = 0
        for call, sg in blocked_calls:
            err = sg.get("error") or "Slot readiness guard blocked request"
            _broadcast_activity(
                call.get("tool") or "",
                call.get("args") or {},
                {"slot_guard": sg},
                duration_ms,
                err,
                source="external",
                client_id=_mcp_client_id,
            )

        # Single-call JSON-RPC response (most MCP clients)
        if len(rpc_calls) == 1 and rpc_calls[0].get("rpc_id") is not None:
            rid = rpc_calls[0].get("rpc_id")
            err_msg = blocked_calls[0][1].get("error") or "Slot not ready"
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {
                        "code": -32010,
                        "message": err_msg,
                        "data": {"slot_guard": blocked_calls[0][1]},
                    },
                },
            )

        return JSONResponse(
            status_code=409,
            content={
                "error": blocked_calls[0][1].get("error") or "Slot readiness guard blocked request",
                "blocked": [sg for _, sg in blocked_calls],
            },
        )

    # Slot execution guard (reject overlap; don't queue hidden retries).
    busy_calls = []
    for call in rpc_calls:
        claim, busy = await _claim_slot_execution(
            call.get("tool") or "",
            call.get("args") if isinstance(call, dict) else {},
            "external",
            _mcp_client_id,
        )
        call["_claim"] = claim
        if busy:
            busy_calls.append((call, busy))

    if busy_calls:
        # Release any claims acquired in this batch before returning busy.
        for call in rpc_calls:
            await _release_slot_execution(call.get("_claim") if isinstance(call, dict) else None)

        for call, bg in busy_calls:
            err = bg.get("error") or "Slot busy"
            _broadcast_activity(
                call.get("tool") or "",
                call.get("args") or {},
                {"slot_busy": bg},
                0,
                err,
                source="external",
                client_id=_mcp_client_id,
            )

        if len(rpc_calls) == 1 and rpc_calls[0].get("rpc_id") is not None:
            rid = rpc_calls[0].get("rpc_id")
            err_msg = busy_calls[0][1].get("error") or "Slot busy"
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": rid,
                    "error": {
                        "code": -32011,
                        "message": err_msg,
                        "data": {"slot_busy": busy_calls[0][1]},
                    },
                },
            )

        return JSONResponse(
            status_code=409,
            content={
                "error": busy_calls[0][1].get("error") or "Slot busy",
                "blocked": [bg for _, bg in busy_calls],
            },
        )

    # Emit immediate "running" entries so UI shows in-flight work.
    for call in rpc_calls:
        tname = call.get("tool") if isinstance(call, dict) else None
        if tname in _LIVE_START_TOOLS:
            _broadcast_activity(
                tname,
                call.get("args") or {},
                {"_phase": "start", "state": "running"},
                0,
                None,
                source="external",
                client_id=_mcp_client_id,
            )

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
                        claim = call.get("_claim")
                        if rpc_id is not None:
                            _pending_external_calls[rpc_id] = {
                                "tool": call["tool"],
                                "args": call["args"],
                                "start": start,
                                "client_id": _mcp_client_id,
                                "claim": claim,
                            }
                            print(
                                f"[MCP-PROXY] Stored pending call id={rpc_id} "
                                f"(type={type(rpc_id).__name__}) tool={call['tool']}"
                            )
                        else:
                            # Notifications (no id) cannot be matched on SSE response.
                            _broadcast_activity(call["tool"], call["args"], None, duration_ms, None, source="external", client_id=_mcp_client_id)
                            await _release_slot_execution(claim)
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
                            source="external", client_id=_mcp_client_id,
                        )
                        # Cache-aware inner tool call broadcasting for agent_chat
                        if call["tool"] == "agent_chat" and item.get("result"):
                            _bac_parsed = _parse_mcp_result(item.get("result"))
                            _bac_full = _bac_parsed
                            if isinstance(_bac_parsed, dict) and _bac_parsed.get("_cached"):
                                try:
                                    _bac_cache = await _call_tool("get_cached", {"cache_id": str(_bac_parsed["_cached"])})
                                    _bac_resolved = _parse_mcp_result((_bac_cache or {}).get("result"))
                                    if isinstance(_bac_resolved, dict) and ("result" in _bac_resolved or "tool_calls" in _bac_resolved):
                                        _bac_full = _bac_resolved
                                except Exception:
                                    pass
                            _bac_inner = _bac_full.get("result") if isinstance(_bac_full, dict) and isinstance(_bac_full.get("result"), dict) else _bac_full
                            _bac_tc = _bac_inner.get("tool_calls", []) if isinstance(_bac_inner, dict) else []
                            for _baci, _bac_entry in enumerate(_bac_tc):
                                if not isinstance(_bac_entry, dict):
                                    continue
                                _broadcast_activity(
                                    _bac_entry.get("tool", "unknown"), _bac_entry.get("args", {}),
                                    {"content": [{"type": "text", "text": str(_bac_entry.get("result", ""))}]},
                                    0, str(_bac_entry.get("error")) if _bac_entry.get("error") else None,
                                    source="agent-inner", client_id=_mcp_client_id,
                                )
                        else:
                            _broadcast_agent_inner_calls(call["tool"], item.get("result"), duration_ms, source="external", client_id=_mcp_client_id)
                        await _release_slot_execution(call.get("_claim"))

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
                            source="external", client_id=_mcp_client_id,
                        )
                        await _release_slot_execution(call.get("_claim"))
                else:
                    for call in rpc_calls:
                        _broadcast_activity(
                            call["tool"],
                            call["args"],
                            None,
                            duration_ms,
                            f"HTTP {resp.status_code}",
                            source="external", client_id=_mcp_client_id,
                        )
                        await _release_slot_execution(call.get("_claim"))

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
            _broadcast_activity(call["tool"], call["args"], None, duration_ms, "Capsule timeout", source="external", client_id=_mcp_client_id)
            await _release_slot_execution(call.get("_claim"))
        return JSONResponse(status_code=504, content={"error": "Capsule timeout"})
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        for call in rpc_calls:
            _broadcast_activity(call["tool"], call["args"], None, duration_ms, str(e), source="external", client_id=_mcp_client_id)
            await _release_slot_execution(call.get("_claim"))
        print(f"[MCP-PROXY] POST error: {e}")
        return JSONResponse(status_code=502, content={"error": str(e)})


app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="."), name="media")


# ── Streamable HTTP transport ──────────────────────────────────────────
# Pi / Claude Desktop / Kiro try StreamableHTTP (POST) before SSE.
# Instead of rejecting with 405, we handle JSON-RPC here using the
# persistent _mcp_session.  This avoids the fragile SSE-per-client
# proxy where HF infrastructure can close long-lived SSE connections.

@app.post("/mcp/sse")
async def mcp_streamable_http(request: Request):
    """Handle MCP Streamable HTTP transport.

    Accepts JSON-RPC requests and responds synchronously using the
    persistent internal MCP session (same one /api/tool uses).
    """
    body_bytes = await request.body()
    if not body_bytes:
        return JSONResponse(status_code=400, content={"error": "Empty body"})

    try:
        payload = json.loads(body_bytes)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    client_id = _extract_client_id(request)

    # ── Handle single JSON-RPC object ──
    if isinstance(payload, dict):
        result = await _handle_streamable_rpc(payload, client_id)
        if result is None:
            return Response(status_code=202)
        return JSONResponse(content=result)

    # ── Handle batch JSON-RPC array ──
    if isinstance(payload, list):
        results = []
        for item in payload:
            if isinstance(item, dict):
                r = await _handle_streamable_rpc(item, client_id)
                if r is not None:
                    results.append(r)
        if not results:
            return Response(status_code=202)
        return JSONResponse(content=results)

    return JSONResponse(status_code=400, content={"error": "Invalid payload"})


async def _handle_streamable_rpc(obj: dict, client_id: str) -> dict | None:
    """Process one JSON-RPC message via the persistent MCP session."""
    method = obj.get("method", "")
    rpc_id = obj.get("id")
    params = obj.get("params", {})
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except Exception:
            params = {}
    if not isinstance(params, dict):
        params = {}

    # ── initialize ──
    if method == "initialize":
        session = await _ensure_session()
        if not session:
            return _rpc_error(rpc_id, -32603, "Failed to connect to capsule MCP")
        # Return server capabilities with the capsule's REAL instructions.
        # _capsule_instructions is populated during _connect_mcp() from the
        # capsule's _build_mcp_instructions() — the full onboarding orientation.
        _fallback_instructions = "Use tools/call for all operations. For large payloads, follow _cached via get_cached(cache_id). agent_chat supports granted_tools for agentic tool use. Local orchestration tools: agent_delegate, agent_chat_inject, agent_chat_sessions."
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": "champion-council", "version": "0.8.9"},
                "instructions": _capsule_instructions or _fallback_instructions,
            },
        }

    # ── notifications (initialized, etc.) — no response needed ──
    if method.startswith("notifications/"):
        return None

    # ── tools/list ──
    if method == "tools/list":
        session = await _ensure_session()
        if not session:
            return _rpc_error(rpc_id, -32603, "MCP session unavailable")
        try:
            result = await session.list_tools()
            tools_list = []
            for t in (result.tools or []):
                td = {"name": t.name, "description": getattr(t, "description", "") or ""}
                schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None)
                if schema:
                    td["inputSchema"] = schema if isinstance(schema, dict) else (schema.model_dump() if hasattr(schema, "model_dump") else {})
                tools_list.append(td)
            tools_list = _agent_augment_tools_list(tools_list)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": tools_list}}
        except Exception as e:
            await _disconnect_mcp()
            return _rpc_error(rpc_id, -32603, f"tools/list failed: {e}")

    # ── tools/call ──
    if method == "tools/call":
        tool_name = params.get("name", "")
        if not isinstance(tool_name, str) or not tool_name:
            return _rpc_error(rpc_id, -32602, "Invalid request parameters", "Missing tool name")

        args = params.get("arguments", {})
        if not isinstance(args, dict):
            args = _coerce_tool_arguments(args)

        if tool_name in ("workflow_create", "workflow_update") and "definition" in args:
            args = dict(args)
            args["definition"] = _normalize_workflow_nodes(args["definition"])

        args = _normalize_proxy_tool_args(tool_name, args)

        # Local virtual orchestrator tools (proxy-side).
        if tool_name == "agent_chat_inject":
            payload = _agent_inject_message(args, source="external", client_id=client_id)
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32012, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "agent_chat_sessions":
            payload = _agent_session_snapshot(args)
            _broadcast_activity(tool_name, args, payload, 0, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "agent_delegate":
            try:
                caller_slot = int(args.get("caller_slot", -1))
            except Exception:
                caller_slot = -1
            caller_session_id = str(args.get("caller_session_id", "external") or "external")
            try:
                caller_depth = int(args.get("_agent_depth", 0) or 0)
            except Exception:
                caller_depth = 0
            started = time.time()
            payload, err_msg = await _agent_delegate_call(caller_slot, caller_session_id, caller_depth, args, source="external", client_id=client_id)
            duration_ms = int((time.time() - started) * 1000)
            out = payload if isinstance(payload, dict) else {"result": payload}
            if err_msg:
                if isinstance(out, dict):
                    out.setdefault("error", err_msg)
                _broadcast_activity(tool_name, args, out, duration_ms, err_msg, source="external", client_id=client_id)
                return _rpc_error(rpc_id, -32013, err_msg, out)
            _broadcast_activity(tool_name, args, out, duration_ms, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}}

        # Slot readiness guard
        sg = await _slot_ready_guard(tool_name, args)
        if sg:
            err_msg = sg.get("error", "Slot not ready")
            _broadcast_activity(tool_name, args, {"slot_guard": sg}, 0, err_msg, source="external", client_id=client_id)
            return _rpc_error(rpc_id, -32010, err_msg, {"slot_guard": sg})

        claim, busy_guard = await _claim_slot_execution(tool_name, args, "external", client_id)
        if busy_guard:
            err_msg = busy_guard.get("error") or f"Slot busy while calling {tool_name}"
            _broadcast_activity(tool_name, args, {"slot_busy": busy_guard}, 0, err_msg, source="external", client_id=client_id)
            return _rpc_error(rpc_id, -32011, err_msg, {"slot_busy": busy_guard})

        if tool_name in _LIVE_START_TOOLS:
            _broadcast_activity(
                tool_name,
                args,
                {"_phase": "start", "state": "running"},
                0,
                None,
                source="external",
                client_id=client_id,
            )

        # ── Server-side agent orchestration for MCP transport ──
        if tool_name == "agent_chat":
            try:
                orchestrated = await _server_side_agent_chat(args, source="external", client_id=client_id)
                _broadcast_activity("agent_chat", args, orchestrated.get("result"), 0, orchestrated.get("error"), source="external", client_id=client_id)
                if orchestrated.get("error"):
                    return _rpc_error(rpc_id, -32603, orchestrated["error"])
                return {"jsonrpc": "2.0", "id": rpc_id, "result": orchestrated.get("result", orchestrated)}
            finally:
                await _release_slot_execution(claim)

        start = time.time()
        try:
            result = await _call_tool(tool_name, args)
            result = await _postprocess_tool_result(tool_name, args, result)
            duration_ms = int((time.time() - start) * 1000)

            error_str = result.get("error") if isinstance(result, dict) else None
            _result_payload = result.get("result", result) if isinstance(result, dict) else result
            _broadcast_activity(tool_name, args, _result_payload, duration_ms, error_str, source="external", client_id=client_id)
            _broadcast_agent_inner_calls(tool_name, _result_payload, duration_ms, source="external", client_id=client_id)

            if error_str:
                return _rpc_error(rpc_id, -32603, error_str)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": result.get("result", result)}
        finally:
            await _release_slot_execution(claim)

    # ── resources/list, prompts/list, etc. — pass through ──
    if method in ("resources/list", "resources/read", "prompts/list", "prompts/get"):
        session = await _ensure_session()
        if not session:
            return _rpc_error(rpc_id, -32603, "MCP session unavailable")
        try:
            if method == "resources/list":
                result = await session.list_resources()
                resources = []
                for r in (result.resources or []):
                    rd = {"uri": str(r.uri), "name": getattr(r, "name", "") or ""}
                    if getattr(r, "description", None):
                        rd["description"] = r.description
                    if getattr(r, "mimeType", None) or getattr(r, "mime_type", None):
                        rd["mimeType"] = getattr(r, "mimeType", None) or getattr(r, "mime_type", None)
                    resources.append(rd)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"resources": resources}}
            elif method == "resources/read":
                uri = params.get("uri", "")
                result = await session.read_resource(uri)
                contents = []
                for c in (result.contents or []):
                    cd = {"uri": str(c.uri)}
                    if hasattr(c, "text") and c.text is not None:
                        cd["text"] = c.text
                    if hasattr(c, "mimeType") and c.mimeType:
                        cd["mimeType"] = c.mimeType
                    contents.append(cd)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"contents": contents}}
            elif method == "prompts/list":
                result = await session.list_prompts()
                prompts = [{"name": p.name, "description": getattr(p, "description", "") or ""} for p in (result.prompts or [])]
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"prompts": prompts}}
            elif method == "prompts/get":
                result = await session.get_prompt(params.get("name", ""), params.get("arguments", {}))
                msgs = []
                for m in (result.messages or []):
                    md = {"role": m.role}
                    if hasattr(m.content, "text"):
                        md["content"] = {"type": "text", "text": m.content.text}
                    msgs.append(md)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"messages": msgs}}
        except Exception as e:
            return _rpc_error(rpc_id, -32603, str(e))

    # ── Unknown method ──
    return _rpc_error(rpc_id, -32601, f"Method not found: {method}")


def _rpc_error(rpc_id, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": err}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
