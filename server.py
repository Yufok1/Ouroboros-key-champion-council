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
import uuid
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
    if isinstance(info_raw, dict) and info_raw.get("error"):
        # Fail-open on transient slot_info errors to avoid false "not plugged" negatives.
        # The downstream call will still surface the real backend error if any.
        return None
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


_HF_CACHE_STATUS_CACHE = {"payload": None, "ts": 0.0}
_HF_CACHE_STATUS_TTL_SECONDS = 5.0
_UNPLUG_HARD_RECLAIM_DEFAULT = os.environ.get("UNPLUG_LOCAL_HARD_RECLAIM", "0").strip().lower() in ("1", "true", "yes", "on")


def _hf_cache_roots() -> list[Path]:
    roots: list[Path] = []

    def _add(p: str | Path | None):
        if not p:
            return
        try:
            path = Path(p).expanduser()
        except Exception:
            return
        if path not in roots:
            roots.append(path)

    _add(os.environ.get("HF_HUB_CACHE", ""))
    _add(os.environ.get("HUGGINGFACE_HUB_CACHE", ""))

    hf_home = os.environ.get("HF_HOME", "")
    if hf_home:
        _add(Path(hf_home).expanduser() / "hub")

    _add(os.environ.get("TRANSFORMERS_CACHE", ""))

    _add(Path.home() / ".cache" / "huggingface" / "hub")

    return roots


def _dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        for root, _, files in os.walk(path, topdown=True):
            for name in files:
                fp = Path(root) / name
                try:
                    total += fp.stat().st_size
                except Exception:
                    continue
    except Exception:
        pass
    return int(total)


def _model_dir_to_repo_id(dirname: str) -> str:
    raw = str(dirname or "")
    if not raw.startswith("models--"):
        return ""
    return raw[len("models--"):].replace("--", "/")


def _repo_id_to_model_dir_prefix(repo_id: str) -> str:
    return "models--" + str(repo_id or "").replace("/", "--")


def _collect_hf_cache_entries() -> tuple[list[str], list[dict], int]:
    roots = [p for p in _hf_cache_roots() if p.exists() and p.is_dir()]
    root_strings = [str(p) for p in roots]
    entries: list[dict] = []
    total_bytes = 0

    for root in roots:
        try:
            children = list(root.iterdir())
        except Exception:
            continue

        for child in children:
            if not child.is_dir():
                continue
            name = child.name
            if not name.startswith("models--"):
                continue

            size_bytes = _dir_size_bytes(child)
            total_bytes += size_bytes
            repo_id = _model_dir_to_repo_id(name)
            try:
                mtime = int(child.stat().st_mtime)
            except Exception:
                mtime = 0

            entries.append({
                "repo_id": repo_id,
                "dir_name": name,
                "path": str(child),
                "size_bytes": int(size_bytes),
                "size_gb": float(round(size_bytes / (1024.0 ** 3), 4)),
                "mtime": mtime,
            })

    entries.sort(key=lambda e: int(e.get("size_bytes", 0)), reverse=True)
    return root_strings, entries, int(total_bytes)


async def _get_plugged_local_model_sources() -> set[str]:
    sources: set[str] = set()
    try:
        ls_raw = await _call_tool("list_slots", {})
        ls_parsed = _parse_mcp_result((ls_raw or {}).get("result")) if isinstance(ls_raw, dict) else None
        slots = ls_parsed.get("slots", []) if isinstance(ls_parsed, dict) else []
        if isinstance(slots, list):
            for s in slots:
                if not isinstance(s, dict):
                    continue
                if not bool(s.get("plugged")):
                    continue
                src = s.get("model_source") or s.get("source") or ""
                if isinstance(src, str) and src and not src.startswith("http://") and not src.startswith("https://"):
                    sources.add(src)
    except Exception:
        pass
    return sources


async def _hf_cache_status_payload(limit: int = 200, force: bool = False) -> dict:
    now = time.time()
    if not force and _HF_CACHE_STATUS_CACHE.get("payload") and (now - float(_HF_CACHE_STATUS_CACHE.get("ts", 0.0))) < _HF_CACHE_STATUS_TTL_SECONDS:
        payload = dict(_HF_CACHE_STATUS_CACHE.get("payload") or {})
        entries = payload.get("entries", [])
        if isinstance(entries, list) and limit > 0:
            payload["entries"] = entries[:limit]
        return payload

    roots, entries, total_bytes = _collect_hf_cache_entries()
    plugged = await _get_plugged_local_model_sources()

    for entry in entries:
        rid = str(entry.get("repo_id") or "")
        entry["plugged"] = rid in plugged

    payload_full = {
        "roots": roots,
        "model_dirs": len(entries),
        "total_bytes": int(total_bytes),
        "total_gb": float(round(total_bytes / (1024.0 ** 3), 4)),
        "plugged_local_models": sorted(list(plugged)),
        "entries": entries,
        "generated_at": datetime.utcnow().isoformat(),
    }

    _HF_CACHE_STATUS_CACHE["payload"] = dict(payload_full)
    _HF_CACHE_STATUS_CACHE["ts"] = now

    payload = dict(payload_full)
    if limit > 0:
        payload["entries"] = entries[:limit]
    return payload


async def _restart_capsule_runtime(reason: str = "manual", preserve_state: bool = True, restore_state_after: bool = True) -> dict:
    started = False
    ready = False
    connected = False
    saved = False
    restored = False
    save_error = None
    restore_error = None

    session_drain_before = _agent_force_drain_sessions(f"restart:{reason}:before")

    if preserve_state and persistence.is_available():
        try:
            saved = await persistence.save_state(_call_tool, force=True)
        except Exception as exc:
            save_error = str(exc)

    try:
        await _disconnect_mcp()
    except Exception:
        pass

    try:
        stop_capsule()
    except Exception:
        pass

    started = bool(start_capsule())
    if started:
        ready = await _wait_for_capsule_sse(timeout=90)
    if ready:
        connected = bool(await _connect_mcp())

    if restore_state_after and connected and persistence.is_available():
        try:
            restored = await persistence.restore_state(_call_tool)
        except Exception as exc:
            restore_error = str(exc)

    session_gc_after = _agent_gc_sessions()

    restore_requested = bool(restore_state_after and connected and persistence.is_available())
    restore_ok = (not restore_requested) or bool(restored)
    if restore_requested and not restore_ok and not restore_error:
        restore_error = "restore_state requested but persistence restore returned no state"

    overall_ok = bool(started and ready and connected and restore_ok)

    return {
        "reason": reason,
        "status": "ok" if overall_ok else "degraded",
        "capsule_running": capsule_process is not None and capsule_process.poll() is None,
        "capsule_pid": capsule_process.pid if capsule_process and capsule_process.poll() is None else None,
        "mcp_ready": connected,
        "saved_state": saved,
        "restored_state": restored,
        "save_error": save_error,
        "restore_error": restore_error,
        "restore_requested": restore_requested,
        "restore_ok": restore_ok,
        "session_drain_before": session_drain_before,
        "session_gc_after": session_gc_after,
    }


async def _hf_cache_clear_payload(
    model_id: str = "",
    keep_plugged: bool = True,
    dry_run: bool = False,
    hard_reclaim: bool = False,
) -> dict:
    _, entries, _ = _collect_hf_cache_entries()
    targets: list[dict] = []
    skipped_plugged: list[dict] = []

    model_filter = str(model_id or "").strip()
    model_dir_prefix = _repo_id_to_model_dir_prefix(model_filter) if model_filter else ""

    plugged = await _get_plugged_local_model_sources() if keep_plugged else set()

    for entry in entries:
        rid = str(entry.get("repo_id") or "")
        dname = str(entry.get("dir_name") or "")

        if model_filter:
            if rid != model_filter and dname != model_dir_prefix and not dname.startswith(model_dir_prefix + "--"):
                continue

        if keep_plugged and rid in plugged:
            skipped_plugged.append(entry)
            continue

        targets.append(entry)

    candidate_bytes = int(sum(int(t.get("size_bytes", 0)) for t in targets))

    if dry_run:
        return {
            "status": "dry_run",
            "model_filter": model_filter or None,
            "keep_plugged": keep_plugged,
            "target_count": len(targets),
            "target_bytes": candidate_bytes,
            "target_gb": float(round(candidate_bytes / (1024.0 ** 3), 4)),
            "targets": targets[:200],
            "skipped_plugged": skipped_plugged[:50],
        }

    deleted = []
    failures = []
    deleted_bytes = 0

    for entry in targets:
        p = Path(str(entry.get("path", "")))
        if not p.exists():
            continue
        try:
            sz = int(entry.get("size_bytes", 0) or 0)
            shutil.rmtree(p, ignore_errors=False)
            deleted.append(entry)
            deleted_bytes += sz
        except Exception as exc:
            failures.append({"path": str(p), "error": str(exc), "repo_id": entry.get("repo_id")})

    _HF_CACHE_STATUS_CACHE["payload"] = None
    _HF_CACHE_STATUS_CACHE["ts"] = 0.0

    reclaim = None
    if hard_reclaim:
        reclaim = await _restart_capsule_runtime(reason="hf_cache_clear", preserve_state=True, restore_state_after=True)

    return {
        "status": "ok" if not failures else "partial",
        "model_filter": model_filter or None,
        "keep_plugged": keep_plugged,
        "deleted_count": len(deleted),
        "deleted_bytes": int(deleted_bytes),
        "deleted_gb": float(round(deleted_bytes / (1024.0 ** 3), 4)),
        "deleted": deleted[:200],
        "failures": failures[:50],
        "skipped_plugged": skipped_plugged[:50],
        "hard_reclaim": bool(hard_reclaim),
        "reclaim": reclaim,
    }


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
    if _DEBUG_FEED_MIRROR_ENABLED and tool not in _DEBUG_FEED_MIRROR_EXCLUDED_TOOLS:
        try:
            asyncio.get_running_loop().create_task(_mirror_activity_to_observe(entry))
        except Exception:
            pass


def _activity_preview(value, max_chars: int | None = None) -> str:
    limit = int(max_chars or _DEBUG_FEED_MIRROR_MAX_CHARS)
    try:
        if isinstance(value, str):
            out = value
        else:
            out = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        out = str(value)
    out = out.strip()
    if len(out) > limit:
        out = out[:limit] + "..."
    return out


async def _mirror_activity_to_observe(entry: dict):
    """Mirror activity entries into observe()/feed for direct debug telemetry."""
    if not _DEBUG_FEED_MIRROR_ENABLED:
        return
    tool = str((entry or {}).get("tool") or "")
    if tool in _DEBUG_FEED_MIRROR_EXCLUDED_TOOLS:
        return
    try:
        payload = {
            "tool": tool,
            "category": str((entry or {}).get("category") or ""),
            "source": str((entry or {}).get("source") or ""),
            "client_id": str((entry or {}).get("clientId") or ""),
            "duration_ms": int((entry or {}).get("durationMs") or 0),
            "error": (entry or {}).get("error"),
            "args_preview": _activity_preview((entry or {}).get("args") or {}, 220),
            "result_preview": _activity_preview((entry or {}).get("result"), _DEBUG_FEED_MIRROR_MAX_CHARS),
            "timestamp_ms": int((entry or {}).get("timestamp") or int(time.time() * 1000)),
        }
        await _call_tool("observe", {"signal_type": "event", "data": json.dumps(payload, ensure_ascii=False)})
    except Exception:
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
_MCP_TOOL_TIMEOUT_SECONDS = max(8, int(os.environ.get("MCP_TOOL_TIMEOUT_SECONDS", "180")))
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
_DEBUG_FEED_MIRROR_ENABLED = os.environ.get("DEBUG_FEED_MIRROR_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
_DEBUG_FEED_MIRROR_MAX_CHARS = max(64, int(os.environ.get("DEBUG_FEED_MIRROR_MAX_CHARS", "320") or 320))
_DEBUG_FEED_MIRROR_EXCLUDED_TOOLS = frozenset({
    "observe",
    "feed",
    "get_cached",
    "list_tools",
    "api_health",
})

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
        result = await asyncio.wait_for(
            session.call_tool(name, arguments),
            timeout=float(_MCP_TOOL_TIMEOUT_SECONDS),
        )
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
    except asyncio.TimeoutError:
        await _disconnect_mcp()
        return {"error": f"MCP tool '{name}' timed out after {_MCP_TOOL_TIMEOUT_SECONDS}s"}
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
        result = await asyncio.wait_for(session.list_tools(), timeout=float(_MCP_TOOL_TIMEOUT_SECONDS))
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

                # Restore persisted state (local-first, optional HF sync)
                if persistence.is_available():
                    pstat = persistence.status() if hasattr(persistence, "status") else {}
                    print(f"[INIT] Restoring persisted state (mode={pstat.get('mode', 'unknown')}, local={pstat.get('local_enabled')}, hf={pstat.get('hf_enabled')})...")
                    await persistence.restore_state(_call_tool)
                    autosave_interval = int(os.environ.get("AUTOSAVE_INTERVAL", "60"))
                    if autosave_interval < 15:
                        autosave_interval = 15
                    persistence.start_autosave(_call_tool, interval=autosave_interval)
                else:
                    pstat = persistence.status() if hasattr(persistence, "status") else {}
                    print(f"[INIT] Persistence unavailable: {pstat}")
            else:
                print("[WARN] MCP connect failed (will retry on first request)")

    yield

    # Shutdown — save state before stopping
    if persistence.is_available():
        print("[SHUTDOWN] Saving state...")
        try:
            await persistence.save_state(_call_tool, force=True)
        except TypeError:
            # Backward compatibility with legacy persistence adapters
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


_WORKFLOW_ALLOWED_NODE_TYPES = frozenset({
    "input", "output", "tool", "fan_out", "merge", "if", "set", "http", "web_search", "agent",
})


def _workflow_load_definition(definition: str | dict) -> tuple[dict | None, str | None]:
    try:
        defn = json.loads(definition) if isinstance(definition, str) else definition
    except Exception as exc:
        return None, f"Workflow definition is not valid JSON: {exc}"
    if not isinstance(defn, dict):
        return None, "Workflow definition must be an object"
    return defn, None


def _workflow_validate_definition(definition: str | dict) -> tuple[dict | None, str | None]:
    defn, err = _workflow_load_definition(definition)
    if err:
        return None, err

    wf_id = defn.get("id") or defn.get("workflow_id")
    if not isinstance(wf_id, str) or not wf_id.strip():
        return None, "Workflow must have an 'id' field"

    nodes = defn.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None, "Workflow must have a 'nodes' array"

    connections = defn.get("connections")
    if not isinstance(connections, list):
        return None, "Workflow must have a 'connections' array"

    node_ids: set[str] = set()
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            return None, f"Node at index {idx} must be an object"
        node_id = str(node.get("id", "") or "").strip()
        if not node_id:
            return None, f"Node at index {idx} is missing id"
        if node_id in node_ids:
            return None, f"Duplicate node id: {node_id}"
        node_ids.add(node_id)

        ntype = str(node.get("type", "") or "").strip()
        if not ntype:
            return None, f"Node '{node_id}' is missing type"
        if ntype not in _WORKFLOW_ALLOWED_NODE_TYPES:
            return None, f"Unknown node type: {ntype}"

        if ntype == "tool":
            t = node.get("tool_name") or node.get("tool")
            if not isinstance(t, str) or not t.strip():
                return None, f"Tool node '{node_id}' is missing tool_name/tool"
        if ntype == "fan_out":
            targets = node.get("targets") or ((node.get("parameters") or {}).get("targets") if isinstance(node.get("parameters"), dict) else None)
            if not isinstance(targets, list) or not targets:
                return None, f"fan_out node '{node_id}' must define non-empty targets"
            for ti, target in enumerate(targets):
                if not isinstance(target, dict):
                    return None, f"fan_out node '{node_id}' target[{ti}] must be object"
                tname = target.get("tool_name") or target.get("tool")
                if not isinstance(tname, str) or not tname.strip():
                    return None, f"fan_out node '{node_id}' target[{ti}] missing tool_name/tool"

    for ci, conn in enumerate(connections):
        if not isinstance(conn, dict):
            return None, f"Connection at index {ci} must be an object"
        src = str(conn.get("from", "") or "").strip()
        dst = str(conn.get("to", "") or "").strip()
        if not src or not dst:
            return None, f"Connection at index {ci} must have from/to"
        if src not in node_ids:
            return None, f"Connection source not found: {src}"
        if dst not in node_ids:
            return None, f"Connection target not found: {dst}"

    normalized = _normalize_workflow_nodes(defn)
    defn2, err2 = _workflow_load_definition(normalized)
    if err2:
        return None, err2
    return defn2, None


def _workflow_local_proxy_tool_names() -> set[str]:
    names = {
        "agent_delegate", "agent_chat_inject", "agent_chat_sessions",
        "agent_chat_result", "agent_chat_purge", "workflow_execute", "workflow_status", "workflow_history",
        "hf_cache_status", "hf_cache_clear", "capsule_restart",
        "persist_status", "persist_restore_revision",
    }
    try:
        if isinstance(_AGENT_LOCAL_TOOL_SPECS, dict):
            names.update(str(k) for k in _AGENT_LOCAL_TOOL_SPECS.keys())
    except Exception:
        pass
    return names


def _workflow_get_invoke_mode(obj: dict | None) -> str:
    if not isinstance(obj, dict):
        return ""
    mode = obj.get("mode")
    if mode is None and isinstance(obj.get("args"), dict):
        mode = obj.get("args", {}).get("mode")
    if mode is None and isinstance(obj.get("parameters"), dict):
        mode = obj.get("parameters", {}).get("mode")
    return str(mode or "").strip().lower()


def _workflow_contains_proxy_local_tools(defn: dict) -> bool:
    local_tools = _workflow_local_proxy_tool_names()
    for node in defn.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ntype = str(node.get("type", "") or "")
        if ntype == "tool":
            t = str(node.get("tool_name") or node.get("tool") or "").strip()
            if t in local_tools:
                return True
        if ntype == "fan_out":
            targets = node.get("targets") or ((node.get("parameters") or {}).get("targets") if isinstance(node.get("parameters"), dict) else [])
            if isinstance(targets, list):
                for target in targets:
                    if not isinstance(target, dict):
                        continue
                    t = str(target.get("tool_name") or target.get("tool") or "").strip()
                    if t in local_tools:
                        return True
    return False


def _workflow_is_proxy_executable(defn: dict) -> bool:
    supported = {"input", "output", "tool", "fan_out", "merge"}
    for node in defn.get("nodes", []):
        if not isinstance(node, dict):
            return False
        ntype = str(node.get("type", "") or "")
        if ntype not in supported:
            return False
    return True


def _workflow_resolve_path(base, path: str):
    cur = base
    if not path:
        return cur
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                idx = int(part)
            except Exception:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            return None
    return cur


def _workflow_resolve_value(value, node_outputs: dict, input_payload):
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("$"):
            ref = raw[1:]
            if ref == "input":
                return input_payload
            if ref.startswith("input."):
                resolved = _workflow_resolve_path(input_payload, ref[len("input."):])
                return resolved if resolved is not None else value
            if "." in ref:
                node_id, path = ref.split(".", 1)
            else:
                node_id, path = ref, ""
            if node_id in node_outputs:
                resolved = _workflow_resolve_path(node_outputs.get(node_id), path)
                return resolved if resolved is not None else value
        return value
    if isinstance(value, list):
        return [_workflow_resolve_value(v, node_outputs, input_payload) for v in value]
    if isinstance(value, dict):
        return {k: _workflow_resolve_value(v, node_outputs, input_payload) for k, v in value.items()}
    return value


def _json_clone(value):
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return value


def _workflow_proxy_trace_id(execution_id: str) -> str:
    return f"workflow:{execution_id}"


async def _workflow_proxy_register_start(
    execution_id: str,
    workflow_id: str,
    input_payload: dict,
    source: str,
    client_id: str | None,
) -> dict:
    now_ms = int(time.time() * 1000)
    started_iso = datetime.utcnow().isoformat()
    row = {
        "execution_id": execution_id,
        "status": "running",
        "workflow_id": workflow_id,
        "nodes_executed": 0,
        "output": None,
        "node_states": {},
        "started_at": started_iso,
        "elapsed_ms": 0,
        "proxy_execution": True,
        "source": source,
        "client_id": client_id,
        "input": _json_clone(input_payload if isinstance(input_payload, dict) else {}),
        "updated_ms": now_ms,
    }
    async with _workflow_proxy_exec_lock:
        _workflow_proxy_exec_store[execution_id] = row
        _workflow_proxy_exec_order.append(execution_id)
        if len(_workflow_proxy_exec_order) > _WORKFLOW_PROXY_HISTORY_LIMIT:
            trim = len(_workflow_proxy_exec_order) - _WORKFLOW_PROXY_HISTORY_LIMIT
            for old_id in _workflow_proxy_exec_order[:trim]:
                _workflow_proxy_exec_store.pop(old_id, None)
            del _workflow_proxy_exec_order[:trim]
    return _json_clone(row)


async def _workflow_proxy_register_update(
    execution_id: str,
    *,
    status: str | None = None,
    nodes_executed: int | None = None,
    node_states: dict | None = None,
    elapsed_ms: int | None = None,
    output: object | None = None,
    error: str | None = None,
) -> dict | None:
    async with _workflow_proxy_exec_lock:
        row = _workflow_proxy_exec_store.get(execution_id)
        if not isinstance(row, dict):
            return None
        if status is not None:
            row["status"] = status
        if nodes_executed is not None:
            row["nodes_executed"] = int(nodes_executed)
        if node_states is not None:
            row["node_states"] = _json_clone(node_states)
        if elapsed_ms is not None:
            row["elapsed_ms"] = int(elapsed_ms)
        if output is not None or status in ("completed", "partial_failure", "failed"):
            row["output"] = _json_clone(output)
        if error is not None:
            row["error"] = str(error)
        row["updated_ms"] = int(time.time() * 1000)
        return _json_clone(row)


async def _workflow_proxy_get_execution(execution_id: str) -> dict | None:
    async with _workflow_proxy_exec_lock:
        row = _workflow_proxy_exec_store.get(execution_id)
        return _json_clone(row) if isinstance(row, dict) else None


async def _workflow_proxy_history(workflow_id: str | None = None, limit: int = 50) -> list[dict]:
    wf = str(workflow_id or "").strip()
    lim = max(1, min(int(limit or 50), _WORKFLOW_PROXY_HISTORY_LIMIT))
    async with _workflow_proxy_exec_lock:
        rows: list[dict] = []
        for exec_id in reversed(_workflow_proxy_exec_order):
            row = _workflow_proxy_exec_store.get(exec_id)
            if not isinstance(row, dict):
                continue
            if wf and str(row.get("workflow_id") or "") != wf:
                continue
            rows.append(_json_clone(row))
            if len(rows) >= lim:
                break
    return rows


def _workflow_trace_args(args: dict | None, workflow_id: str, execution_id: str, node_id: str | None = None, target_id: str | None = None) -> dict:
    out = dict(args or {})
    trace_id = _workflow_proxy_trace_id(execution_id)
    out.setdefault("session_id", trace_id)
    out.setdefault("_trace_id", trace_id)
    out.setdefault("_trace_role", "workflow")
    out["_workflow_id"] = workflow_id
    out["_workflow_execution_id"] = execution_id
    if node_id:
        out["_workflow_node_id"] = str(node_id)
    if target_id:
        out["_workflow_target_id"] = str(target_id)
    return out


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

    # Normalize CASCADE tool operation aliases + params encoding.
    if tool_name in ("cascade_system", "cascade_data", "cascade_record"):
        op = str(patched.get("operation", "") or "").strip().lower()
        params_raw = patched.get("params")
        params_obj = {}
        if isinstance(params_raw, dict):
            params_obj = dict(params_raw)
        elif isinstance(params_raw, str):
            try:
                _parsed = json.loads(params_raw)
                if isinstance(_parsed, dict):
                    params_obj = dict(_parsed)
            except Exception:
                params_obj = {}

        if tool_name == "cascade_system":
            op_alias = {
                "ingest_logs": "ingest_text",
                "ingest_log": "ingest_text",
                "ingest": "ingest_text",
                "analysis": "analyze",
            }
            if op in op_alias:
                patched["operation"] = op_alias[op]
        elif tool_name == "cascade_data":
            op_alias = {
                "schema_inference": "schema",
                "schema-inference": "schema",
                "pii": "pii_scan",
                "scan_pii": "pii_scan",
                "license": "license_check",
                "observe_data": "observe",
            }
            if op in op_alias:
                patched["operation"] = op_alias[op]
            op = str(patched.get("operation", "") or "").strip().lower()
            if op == "license_check":
                top_license = patched.get("license")
                top_target = patched.get("target_license", patched.get("target"))
                if isinstance(top_license, str) and top_license.strip() and "license" not in params_obj:
                    params_obj["license"] = top_license.strip()
                if isinstance(top_target, str) and top_target.strip() and "target_license" not in params_obj:
                    params_obj["target_license"] = top_target.strip()

                lic_raw = params_obj.get("license", params_obj.get("text", ""))
                lic_norm = _normalize_license_id(str(lic_raw or ""))
                if lic_norm:
                    params_obj["license"] = lic_norm
                    if not str(params_obj.get("text", "") or "").strip():
                        params_obj["text"] = lic_norm

                target_raw = params_obj.get("target_license", params_obj.get("target", ""))
                target_norm = _normalize_license_id(str(target_raw or ""))
                if target_norm:
                    params_obj["target_license"] = target_norm

                src_raw = params_obj.get("source_licenses")
                if isinstance(src_raw, list):
                    normalized_src = []
                    for item in src_raw:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            origin = str(item[0] or "source").strip() or "source"
                            lid = _normalize_license_id(str(item[1] or ""))
                            if lid:
                                normalized_src.append([origin, lid])
                        elif isinstance(item, dict):
                            origin = str(item.get("source") or item.get("origin") or "source").strip() or "source"
                            lid = _normalize_license_id(str(item.get("license") or item.get("id") or item.get("name") or ""))
                            if lid:
                                normalized_src.append([origin, lid])
                        elif isinstance(item, str):
                            lid = _normalize_license_id(item)
                            if lid:
                                normalized_src.append(["source", lid])
                    if normalized_src:
                        params_obj["source_licenses"] = normalized_src
        elif tool_name == "cascade_record":
            op_alias = {
                "tape_record": "tape_write",
                "record_tape": "tape_write",
                "tape_log": "tape_write",
                "log": "log_interpretive",
            }
            if op in op_alias:
                patched["operation"] = op_alias[op]
            op = str(patched.get("operation", "") or "").strip().lower()
            if op == "tape_write":
                payload = params_obj.get("data")
                if payload is None:
                    for key in ("entry", "event", "payload", "value", "text", "message"):
                        if key in params_obj:
                            payload = params_obj.get(key)
                            break
                if payload is None:
                    for key in ("data", "entry", "event", "payload", "value", "text", "message"):
                        if key in patched:
                            payload = patched.get(key)
                            break
                if payload is not None:
                    params_obj["data"] = payload
            elif op == "tape_read":
                if "count" not in params_obj:
                    lim = params_obj.get("limit", patched.get("limit", patched.get("count")))
                    try:
                        if lim is not None and str(lim).strip():
                            params_obj["count"] = int(lim)
                    except Exception:
                        pass
            pth = patched.get("path")
            if isinstance(pth, str) and pth.strip() and "path" not in params_obj:
                params_obj["path"] = pth.strip()

        needs_params = (
            "params" in patched
            or (tool_name == "cascade_data" and str(patched.get("operation", "")).strip().lower() == "license_check")
            or (tool_name == "cascade_record" and str(patched.get("operation", "")).strip().lower() in ("tape_write", "tape_read"))
        )
        if needs_params:
            try:
                patched["params"] = json.dumps(params_obj)
            except Exception:
                patched["params"] = str(params_obj)

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


def _normalize_license_id(raw: str) -> str:
    """Normalize common free-text license labels to SPDX IDs."""
    s = str(raw or "").strip()
    if not s:
        return ""
    low = s.lower()

    # Preserve already SPDX-like tokens.
    if " " not in s and "/" not in s and any(ch.isdigit() for ch in s):
        return s

    if "apache" in low and ("2.0" in low or "2" in low):
        return "Apache-2.0"
    if "mit" in low:
        return "MIT"
    if "bsd" in low and "3" in low:
        return "BSD-3-Clause"
    if "bsd" in low and "2" in low:
        return "BSD-2-Clause"
    if "mpl" in low and "2" in low:
        return "MPL-2.0"
    if "agpl" in low and "3" in low:
        return "AGPL-3.0-only"
    if "lgpl" in low and "3" in low:
        return "LGPL-3.0-only"
    if "lgpl" in low and "2.1" in low:
        return "LGPL-2.1-only"
    if "gpl" in low and "3" in low:
        return "GPL-3.0-only"
    if "gpl" in low and "2" in low:
        return "GPL-2.0-only"
    if "cc0" in low:
        return "CC0-1.0"
    if "cc-by-nc-sa" in low:
        return "CC-BY-NC-SA-4.0"
    if "cc-by-nc" in low:
        return "CC-BY-NC-4.0"
    if "cc-by-sa" in low:
        return "CC-BY-SA-4.0"
    if "cc-by" in low:
        return "CC-BY-4.0"
    return s


# ═══════════════════════════════════════════════════════════════════════
# SERVER-SIDE AGENT ORCHESTRATOR
# Runs the agent tool-call loop at the proxy layer so every step is
# individually visible, timeout-resilient, and streamed via SSE.
# The capsule's monolithic agent_chat is bypassed entirely.
# ═══════════════════════════════════════════════════════════════════════

_AGENT_BLOCKED_TOOLS = frozenset({
    "start_api_server", "implode", "defrost",
    "spawn_quine", "spawn_swarm", "replicate", "export_quine",
    "agent_chat",  # prevent direct self-recursive nesting (use agent_delegate)
})

_AGENT_DEFAULT_GRANTED = [
    "get_status", "list_slots", "slot_info", "get_capabilities", "embed_text",
    "invoke_slot", "call", "agent_delegate", "agent_chat_inject", "agent_chat_sessions", "agent_chat_result", "agent_chat_purge",
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
    "metrics_analyze", "workflow_list", "workflow_get", "workflow_status", "workflow_execute",
]

_AGENT_MAX_DELEGATION_DEPTH = max(1, int(os.environ.get("AGENT_MAX_DELEGATION_DEPTH", "3")))
_AGENT_INJECT_QUEUE_LIMIT = max(5, int(os.environ.get("AGENT_INJECT_QUEUE_LIMIT", "64")))
_AGENT_TOOL_DESC_MAX = max(4, int(os.environ.get("AGENT_TOOL_DESC_MAX", "24")))
_AGENT_TOOL_DESC_PARAM_MAX = max(0, int(os.environ.get("AGENT_TOOL_DESC_PARAM_MAX", "4")))
_AGENT_MODEL_STEP_TIMEOUT_LOCAL = max(15, int(os.environ.get("AGENT_MODEL_STEP_TIMEOUT_LOCAL", "75")))
_AGENT_MODEL_STEP_TIMEOUT_REMOTE = max(10, int(os.environ.get("AGENT_MODEL_STEP_TIMEOUT_REMOTE", "45")))
_AGENT_TOOL_STEP_TIMEOUT = max(8, int(os.environ.get("AGENT_TOOL_STEP_TIMEOUT", "40")))
_AGENT_SESSION_MAX_WALLCLOCK_SEC = max(30, int(os.environ.get("AGENT_SESSION_MAX_WALLCLOCK_SEC", "180")))
_AGENT_SESSION_MAX_IDLE_SEC = max(20, int(os.environ.get("AGENT_SESSION_MAX_IDLE_SEC", "90")))
_AGENT_CONTEXT_WINDOW_DEFAULT = max(5, int(os.environ.get("AGENT_CONTEXT_WINDOW_DEFAULT", "20")))
_AGENT_CONTEXT_WINDOW_MAX = max(_AGENT_CONTEXT_WINDOW_DEFAULT, int(os.environ.get("AGENT_CONTEXT_WINDOW_MAX", "200")))
_AGENT_CONTEXT_SUMMARY_MAX_CHARS = max(500, int(os.environ.get("AGENT_CONTEXT_SUMMARY_MAX_CHARS", "4000")))
_AGENT_CONTEXT_ARCHIVE_MAX_ITEMS = max(4, int(os.environ.get("AGENT_CONTEXT_ARCHIVE_MAX_ITEMS", "64")))
_AGENT_SESSION_RETENTION_MAX = max(20, int(os.environ.get("AGENT_SESSION_RETENTION_MAX", "200")))
_AGENT_SESSION_RETENTION_SEC = max(60, int(os.environ.get("AGENT_SESSION_RETENTION_SEC", "3600")))

_PROVIDER_RETRY_ENABLED = str(os.environ.get("PROVIDER_RETRY_ENABLED", "1")).strip().lower() not in ("0", "false", "no", "off")
_PROVIDER_RETRY_MAX_ATTEMPTS = max(1, int(os.environ.get("PROVIDER_RETRY_MAX_ATTEMPTS", "3")))
_PROVIDER_RETRY_BASE_DELAY_MS = max(50, int(os.environ.get("PROVIDER_RETRY_BASE_DELAY_MS", "200")))

_WORKFLOW_PROXY_EXECUTION_ENABLED = str(os.environ.get("WORKFLOW_PROXY_EXECUTION_ENABLED", "1")).strip().lower() not in ("0", "false", "no", "off")
_WORKFLOW_EMBED_AUTOREROUTE = str(os.environ.get("WORKFLOW_EMBED_AUTOREROUTE", "1")).strip().lower() not in ("0", "false", "no", "off")
_WORKFLOW_PROXY_HISTORY_LIMIT = max(50, int(os.environ.get("WORKFLOW_PROXY_HISTORY_LIMIT", "500")))

_workflow_proxy_exec_store: dict[str, dict] = {}
_workflow_proxy_exec_order: list[str] = []
_workflow_proxy_exec_lock = asyncio.Lock()

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
                "granted_tools": {
                    "type": "array",
                    "description": "Optional delegated granted tools",
                    "items": {"type": "string"}
                },
                "context_strategy": {"type": "string", "description": "Optional delegated context policy: full|sliding-window|summarize"},
                "context_window_size": {"type": "integer", "description": "Optional delegated recent window size"}
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
    },
    "agent_chat_result": {
        "description": "Fetch latest result/state for an agent_chat session (timeout reconciliation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Agent session id"},
                "slot": {"type": "integer", "description": "Optional slot filter when session_id omitted"}
            }
        }
    },
    "agent_chat_purge": {
        "description": "Purge inactive agent_chat sessions to control memory/retention.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "older_than_seconds": {"type": "integer", "description": "Delete inactive sessions older than N seconds (default retention)"},
                "limit": {"type": "integer", "description": "Max sessions to purge in one call"},
                "slot": {"type": "integer", "description": "Optional slot filter"}
            }
        }
    },
    "hf_cache_status": {
        "description": "Inspect local HuggingFace model cache directories and sizes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max cache entries to return"},
                "force": {"type": "boolean", "description": "Bypass short-lived cache and rescan disk"}
            }
        }
    },
    "hf_cache_clear": {
        "description": "Delete local HuggingFace model cache directories (disk cleanup).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Optional specific model id (e.g. org/name)"},
                "keep_plugged": {"type": "boolean", "description": "Keep cache dirs for currently plugged local models"},
                "dry_run": {"type": "boolean", "description": "Preview deletions without deleting"},
                "hard_reclaim": {"type": "boolean", "description": "Restart capsule after cleanup to reclaim RAM"}
            }
        }
    },
    "capsule_restart": {
        "description": "Restart capsule process (optionally preserving and restoring persisted state).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preserve_state": {"type": "boolean", "description": "Save state before restart"},
                "restore_state": {"type": "boolean", "description": "Restore state after reconnect"},
                "reason": {"type": "string", "description": "Operator reason label for audit trail"}
            }
        }
    },
    "persist_status": {
        "description": "Return persistence configuration and durability/guard status.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "persist_restore_revision": {
        "description": "Restore persistence state from a specific HF dataset commit hash/revision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "revision": {"type": "string", "description": "HF dataset commit hash/revision"},
                "promote_after_restore": {"type": "boolean", "description": "Immediately persist restored state back to HEAD"}
            },
            "required": ["revision"]
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


def _schema_sanitize(node):
    if isinstance(node, list):
        return [_schema_sanitize(v) for v in node]
    if not isinstance(node, dict):
        return node

    out = {}
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            out[key] = {str(k): _schema_sanitize(v) if isinstance(v, dict) else {"type": "string"} for k, v in value.items()}
        elif key in ("items", "additionalProperties", "contains", "not", "if", "then", "else", "propertyNames", "unevaluatedItems", "unevaluatedProperties"):
            if isinstance(value, dict):
                out[key] = _schema_sanitize(value)
            elif isinstance(value, list):
                out[key] = [_schema_sanitize(v) for v in value]
            else:
                out[key] = value
        elif key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            out[key] = [_schema_sanitize(v) if isinstance(v, dict) else v for v in (value if isinstance(value, list) else [])]
        elif key in ("$defs", "definitions", "patternProperties", "dependentSchemas") and isinstance(value, dict):
            out[key] = {str(k): _schema_sanitize(v) if isinstance(v, dict) else {"type": "string"} for k, v in value.items()}
        else:
            out[key] = _schema_sanitize(value) if isinstance(value, (dict, list)) else value

    stype = out.get("type")
    if stype == "array" and "items" not in out:
        out["items"] = {"type": "string"}
    if stype == "object" and "properties" not in out and "additionalProperties" not in out:
        out["properties"] = {}
    return out


def _sanitize_tool_spec(tool: dict) -> dict | None:
    if not isinstance(tool, dict):
        return None
    item = dict(tool)
    schema = item.get("inputSchema")
    if schema is None:
        schema = item.get("input_schema")
    if hasattr(schema, "model_dump"):
        try:
            schema = schema.model_dump()
        except Exception:
            schema = {}
    if not isinstance(schema, dict):
        schema = {}
    item["inputSchema"] = _schema_sanitize(schema)
    item.pop("input_schema", None)
    return item


def _agent_augment_tools_list(tools: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for t in (tools or []):
        fixed = _sanitize_tool_spec(t)
        if not isinstance(fixed, dict):
            continue
        name = str(fixed.get("name", "") or "").strip()
        if not name:
            continue
        seen.add(name)
        merged.append(fixed)
    for t in _agent_local_tools_manifest():
        fixed = _sanitize_tool_spec(t)
        if not isinstance(fixed, dict):
            continue
        name = fixed.get("name")
        if name not in seen:
            merged.append(fixed)
    return merged


def _agent_session_snapshot(args: dict | None = None) -> dict:
    _agent_gc_sessions()
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
            "context_strategy": sess.get("context_strategy"),
            "context_window_size": sess.get("context_window_size"),
            "context_compactions": int(sess.get("context_compactions") or 0),
        })

    rows.sort(key=lambda r: int(r.get("updated_ts") or 0), reverse=True)
    if len(rows) > limit:
        rows = rows[:limit]

    return {
        "sessions": rows,
        "count": len(rows),
        "active_count": sum(1 for r in rows if r.get("active")),
    }


def _agent_session_result(args: dict | None = None) -> dict:
    _agent_gc_sessions()
    args = args or {}
    sid_req = str(args.get("session_id", "") or "").strip()
    slot_filter = args.get("slot", None)
    try:
        slot_filter = int(slot_filter) if slot_filter is not None else None
    except Exception:
        slot_filter = None

    sid, sess = _agent_select_session(sid_req, slot_filter, active_preferred=True, strict_id=bool(sid_req))
    if not sid or not isinstance(sess, dict):
        return {
            "error": f"Session not found: {sid_req}" if sid_req else "No matching session",
            "session_id": sid_req or None,
            "slot": slot_filter,
        }

    turns = sess.get("turns") if isinstance(sess.get("turns"), list) else []
    last_assistant = ""
    for t in reversed(turns):
        if isinstance(t, dict) and str(t.get("role", "")) == "assistant":
            last_assistant = str(t.get("content", "") or "")
            break

    return {
        "session_id": sid,
        "slot": sess.get("slot"),
        "active": bool(sess.get("active", False)),
        "updated_ts": int(sess.get("updated_ts") or sess.get("last_active_ts") or 0),
        "started_ts": int(sess.get("started_ts") or 0),
        "turn_count": len(turns),
        "pending_messages": len(sess.get("inbox") if isinstance(sess.get("inbox"), list) else []),
        "terminated_reason": sess.get("terminated_reason"),
        "delegation_depth": int(sess.get("delegation_depth") or 0),
        "parent_session_id": str(sess.get("parent_session_id") or ""),
        "source": sess.get("source"),
        "client_id": sess.get("client_id"),
        "context_strategy": sess.get("context_strategy"),
        "context_window_size": sess.get("context_window_size"),
        "context_compactions": int(sess.get("context_compactions") or 0),
        "context_dropped_messages": int(sess.get("context_dropped_messages") or 0),
        "last_assistant": last_assistant,
        "history_tail": turns[-12:],
    }


def _agent_session_purge(args: dict | None = None) -> dict:
    _agent_gc_sessions()
    args = args or {}
    now = int(time.time() * 1000)

    try:
        older_than_seconds = int(args.get("older_than_seconds", _AGENT_SESSION_RETENTION_SEC) or _AGENT_SESSION_RETENTION_SEC)
    except Exception:
        older_than_seconds = _AGENT_SESSION_RETENTION_SEC
    older_than_seconds = max(10, older_than_seconds)

    try:
        purge_limit = int(args.get("limit", _AGENT_SESSION_RETENTION_MAX) or _AGENT_SESSION_RETENTION_MAX)
    except Exception:
        purge_limit = _AGENT_SESSION_RETENTION_MAX
    purge_limit = max(1, purge_limit)

    slot_filter = args.get("slot", None)
    try:
        slot_filter = int(slot_filter) if slot_filter is not None else None
    except Exception:
        slot_filter = None

    cutoff_ms = now - int(older_than_seconds * 1000)
    inactive_rows = []
    for sid, sess in _agent_sessions.items():
        if not isinstance(sess, dict):
            continue
        if bool(sess.get("active", False)):
            continue
        try:
            sess_slot = int(sess.get("slot"))
        except Exception:
            sess_slot = None
        if slot_filter is not None and sess_slot != slot_filter:
            continue
        ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or 0)
        if ts <= cutoff_ms:
            inactive_rows.append((ts, sid))

    inactive_rows.sort(key=lambda x: x[0])
    removed = []
    for _, sid in inactive_rows[:purge_limit]:
        _agent_sessions.pop(sid, None)
        removed.append(sid)

    # Hard cap retention even if caller doesn't request aggressive age pruning.
    # Keep most recent sessions first.
    if len(_agent_sessions) > _AGENT_SESSION_RETENTION_MAX:
        rows = []
        for sid, sess in _agent_sessions.items():
            if not isinstance(sess, dict):
                continue
            ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or 0)
            active = bool(sess.get("active", False))
            rows.append((active, ts, sid))
        rows.sort(key=lambda r: (1 if r[0] else 0, r[1]), reverse=True)
        keep = set(sid for _, _, sid in rows[:_AGENT_SESSION_RETENTION_MAX])
        for _, _, sid in rows[_AGENT_SESSION_RETENTION_MAX:]:
            if sid in _agent_sessions and sid not in keep:
                _agent_sessions.pop(sid, None)
                removed.append(sid)

    return {
        "status": "ok",
        "purged": len(removed),
        "removed_session_ids": removed,
        "remaining": len(_agent_sessions),
        "cutoff_ms": cutoff_ms,
        "older_than_seconds": older_than_seconds,
        "retention_max": _AGENT_SESSION_RETENTION_MAX,
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
    _agent_gc_sessions()
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

    # Reject injections into inactive sessions (explicit or slot-selected).
    is_active = bool(session.get("active", False))
    if not is_active:
        if not has_explicit_id and target_slot is not None:
            return {
                "error": f"No active session for slot {target_slot}",
                "session_id": sid,
                "slot": target_slot,
                "active": False,
            }
        return {
            "error": f"Session is not active: {sid}",
            "session_id": sid,
            "slot": session.get("slot"),
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


def _is_remote_model_source(source: str | None) -> bool:
    src = str(source or "").strip().lower()
    return src.startswith("http://") or src.startswith("https://")


def _agent_gc_sessions(now_ms: int | None = None) -> dict:
    """Expire stale active sessions and clear orphaned pending inboxes."""
    now = int(now_ms or int(time.time() * 1000))
    wall_ms = int(_AGENT_SESSION_MAX_WALLCLOCK_SEC * 1000)
    idle_ms = int(_AGENT_SESSION_MAX_IDLE_SEC * 1000)

    expired = 0
    cleared_inboxes = 0

    for sid, sess in list(_agent_sessions.items()):
        if not isinstance(sess, dict):
            continue

        active = bool(sess.get("active", False))
        updated_ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or now)
        started_ts = int(sess.get("started_ts") or updated_ts)
        inbox = sess.get("inbox") if isinstance(sess.get("inbox"), list) else []

        if active:
            stale_reasons = []
            if wall_ms > 0 and (now - started_ts) > wall_ms:
                stale_reasons.append("wallclock")
            if idle_ms > 0 and (now - updated_ts) > idle_ms:
                stale_reasons.append("idle")
            if stale_reasons:
                dropped = len(inbox)
                sess["active"] = False
                sess["inbox"] = []
                sess["updated_ts"] = now
                sess["terminated_reason"] = f"watchdog:{','.join(stale_reasons)}"
                turns = sess.get("turns")
                if not isinstance(turns, list):
                    turns = []
                    sess["turns"] = turns
                turns.append({
                    "role": "system",
                    "content": f"[AUTO-TERMINATED] Session watchdog tripped ({', '.join(stale_reasons)}).",
                    "ts": now,
                })
                _agent_sessions[sid] = sess
                expired += 1
                cleared_inboxes += dropped
                continue

        if not active and inbox:
            cleared_inboxes += len(inbox)
            sess["inbox"] = []
            sess["updated_ts"] = now
            _agent_sessions[sid] = sess

    pruned_inactive = 0
    inactive_cutoff_ms = now - int(_AGENT_SESSION_RETENTION_SEC * 1000)
    for sid, sess in list(_agent_sessions.items()):
        if not isinstance(sess, dict):
            continue
        if bool(sess.get("active", False)):
            continue
        updated_ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or 0)
        if updated_ts and updated_ts < inactive_cutoff_ms:
            _agent_sessions.pop(sid, None)
            pruned_inactive += 1

    # hard cap retention (most recently updated first, active sessions preserved)
    if len(_agent_sessions) > _AGENT_SESSION_RETENTION_MAX:
        rows = []
        for sid, sess in _agent_sessions.items():
            if not isinstance(sess, dict):
                continue
            ts = int(sess.get("updated_ts") or sess.get("last_active_ts") or 0)
            active = bool(sess.get("active", False))
            rows.append((active, ts, sid))
        rows.sort(key=lambda r: (1 if r[0] else 0, r[1]), reverse=True)
        for _, _, sid in rows[_AGENT_SESSION_RETENTION_MAX:]:
            if sid in _agent_sessions and not bool((_agent_sessions.get(sid) or {}).get("active", False)):
                _agent_sessions.pop(sid, None)
                pruned_inactive += 1

    return {
        "expired": expired,
        "cleared_inboxes": cleared_inboxes,
        "pruned_inactive": pruned_inactive,
        "session_count": len(_agent_sessions),
    }


def _agent_force_drain_sessions(reason: str = "manual") -> dict:
    """Mark all sessions inactive and clear inboxes (used around runtime restarts)."""
    now = int(time.time() * 1000)
    deactivated = 0
    cleared = 0
    for sid, sess in list(_agent_sessions.items()):
        if not isinstance(sess, dict):
            continue
        if bool(sess.get("active", False)):
            deactivated += 1
        inbox = sess.get("inbox") if isinstance(sess.get("inbox"), list) else []
        cleared += len(inbox)
        sess["active"] = False
        sess["inbox"] = []
        sess["updated_ts"] = now
        sess["terminated_reason"] = f"runtime:{reason}"
        _agent_sessions[sid] = sess
    return {
        "deactivated": deactivated,
        "cleared_inboxes": cleared,
        "session_count": len(_agent_sessions),
    }


def _agent_normalize_context_strategy(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("rolling", "window", "sliding", "sliding_window", "sliding-window"):
        return "sliding-window"
    if raw in ("summary", "summarize", "tiered", "hybrid"):
        return "summarize"
    if raw in ("full", "all", "include-everything", "include_everything"):
        return "full"
    return "sliding-window"


def _agent_compose_summary_delta(messages: list[dict], max_points: int = 24, max_chars: int = 1800) -> str:
    points: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "") or "").strip().lower() or "msg"
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue

        # Skip repetitive orchestration boilerplate.
        if content.startswith("[SYSTEM INSTRUCTIONS]"):
            continue

        line = ""
        if content.startswith("TOOL RESULT ["):
            first = content.splitlines()[0].strip()
            line = f"tool: {first[:220]}"
        elif content.startswith("[LIVE UPDATE"):
            first = content.splitlines()[0].strip()
            line = f"update: {first[:220]}"
        elif role == "assistant" and content.startswith("{"):
            first = content.splitlines()[0].strip()
            line = f"assistant_json: {first[:220]}"
        else:
            compact = " ".join(content.split())
            line = f"{role}: {compact[:220]}"

        if line:
            points.append(line)
        if len(points) >= max_points:
            break

    if not points:
        return ""

    summary = "\n".join(f"- {p}" for p in points)
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary


def _agent_compact_chat_messages(session: dict, strategy: str, window_size: int) -> dict:
    """Apply context policy to session chat_messages.

    Keeps first system prompt, optionally a rolling summary, and a bounded recent window.
    """
    if not isinstance(session, dict):
        return {"changed": False, "dropped": 0}

    chat = session.get("chat_messages")
    if not isinstance(chat, list) or not chat:
        return {"changed": False, "dropped": 0}

    strategy = _agent_normalize_context_strategy(strategy)
    window = max(5, min(int(window_size or _AGENT_CONTEXT_WINDOW_DEFAULT), _AGENT_CONTEXT_WINDOW_MAX))

    primary_system = None
    prior_summary = str(session.get("context_summary") or "")
    body: list[dict] = []

    for idx, msg in enumerate(chat):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "") or "")
        content = str(msg.get("content", "") or "")

        if idx == 0 and role == "system" and primary_system is None:
            primary_system = msg
            continue

        if role == "system" and content.startswith("[CONTEXT SUMMARY]"):
            prior_summary = content[len("[CONTEXT SUMMARY]"):].strip()
            continue

        if role == "system":
            # Ignore auxiliary system payloads in rolling body.
            continue

        body.append(msg)

    if strategy == "full":
        session["context_strategy"] = strategy
        session["context_window_size"] = window
        return {"changed": False, "dropped": 0, "summary_chars": len(prior_summary)}

    if len(body) <= window:
        rebuilt = []
        if primary_system:
            rebuilt.append(primary_system)
        if strategy == "summarize" and prior_summary:
            rebuilt.append({"role": "system", "content": "[CONTEXT SUMMARY]\n" + prior_summary})
        rebuilt.extend(body)
        changed = rebuilt != chat
        if changed:
            session["chat_messages"] = rebuilt
        session["context_strategy"] = strategy
        session["context_window_size"] = window
        return {"changed": changed, "dropped": 0, "summary_chars": len(prior_summary)}

    older = body[:-window]
    recent = body[-window:]
    dropped = len(older)

    merged_summary = prior_summary
    if strategy == "summarize":
        delta = _agent_compose_summary_delta(older)
        if delta:
            merged = (prior_summary + "\n" + delta).strip() if prior_summary else delta
            if len(merged) > _AGENT_CONTEXT_SUMMARY_MAX_CHARS:
                merged = merged[-_AGENT_CONTEXT_SUMMARY_MAX_CHARS:]
            merged_summary = merged
            archive = session.get("context_archive") if isinstance(session.get("context_archive"), list) else []
            archive.append({
                "ts": int(time.time() * 1000),
                "dropped": dropped,
                "summary_preview": delta[:280],
            })
            if len(archive) > _AGENT_CONTEXT_ARCHIVE_MAX_ITEMS:
                archive = archive[-_AGENT_CONTEXT_ARCHIVE_MAX_ITEMS:]
            session["context_archive"] = archive
            session["context_summary"] = merged_summary

    rebuilt = []
    if primary_system:
        rebuilt.append(primary_system)
    if strategy == "summarize" and merged_summary:
        rebuilt.append({"role": "system", "content": "[CONTEXT SUMMARY]\n" + merged_summary})
    rebuilt.extend(recent)

    changed = rebuilt != chat
    if changed:
        session["chat_messages"] = rebuilt
    session["context_strategy"] = strategy
    session["context_window_size"] = window
    session["context_compactions"] = int(session.get("context_compactions") or 0) + (1 if dropped > 0 else 0)
    session["context_dropped_messages"] = int(session.get("context_dropped_messages") or 0) + dropped

    return {
        "changed": changed,
        "dropped": dropped,
        "summary_chars": len(merged_summary),
        "window_size": window,
        "strategy": strategy,
    }


async def _get_tool_descriptions(granted_tools: list[str]) -> str:
    """Build tool description block from capsule tool list with bounded prompt size."""
    tools_raw = await _list_tools()
    all_tools = (tools_raw.get("result", {}).get("tools") or []) if isinstance(tools_raw, dict) else []
    granted_set = set(granted_tools)

    lines = []
    omitted = 0
    max_tools = max(1, _AGENT_TOOL_DESC_MAX)
    max_params = max(0, _AGENT_TOOL_DESC_PARAM_MAX)

    for t in all_tools:
        name = str(t.get("name", "") or "").strip()
        if not name or name not in granted_set:
            continue

        if len(lines) >= max_tools:
            omitted += 1
            continue

        desc = (t.get("description") or "").strip().split("\n")[0][:120]
        schema = t.get("inputSchema", {}) if isinstance(t, dict) else {}
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = set(schema.get("required", [])) if isinstance(schema, dict) else set()

        params = []
        total_props = 0
        for pname, pinfo in props.items():
            total_props += 1
            if max_params and len(params) >= max_params:
                continue
            ptype = pinfo.get("type", "any") if isinstance(pinfo, dict) else "any"
            marker = " (required)" if pname in required else ""
            params.append(f"{pname}: {ptype}{marker}")

        if max_params and total_props > max_params:
            params.append(f"... +{total_props - max_params} more")

        sig = ", ".join(params)
        lines.append(f"- {name}({sig}): {desc}")

    if omitted > 0:
        lines.append(f"- ... plus {omitted} additional granted tools (available but omitted for brevity)")

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
    if called_args.get("context_strategy") is not None:
        delegate_args["context_strategy"] = called_args.get("context_strategy")
    if called_args.get("context_window_size") is not None:
        delegate_args["context_window_size"] = called_args.get("context_window_size")
    # C7 fix: only propagate granted_tools if the caller provided a non-empty list.
    # An empty list would starve the child agent of all tools. When omitted or empty,
    # the child inherits the server default grant set instead.
    caller_grants = called_args.get("granted_tools")
    if isinstance(caller_grants, list) and len(caller_grants) > 0:
        delegate_args["granted_tools"] = [str(t) for t in caller_grants if str(t).strip()]

    claim, busy = await _claim_slot_execution("agent_chat", {"slot": target_slot, "session_id": delegate_session_id}, source="agent-inner", client_id=client_id)
    if busy:
        return {"slot_busy": busy}, busy.get("error") or "delegate target busy"

    delegated = None
    try:
        attempts = _PROVIDER_RETRY_MAX_ATTEMPTS if _PROVIDER_RETRY_ENABLED else 1
        for attempt in range(1, attempts + 1):
            delegated = await _server_side_agent_chat(delegate_args, source="agent-inner", client_id=client_id)
            if isinstance(delegated, dict) and delegated.get("error"):
                if attempt >= attempts:
                    break
                await asyncio.sleep(min(1.5, (_PROVIDER_RETRY_BASE_DELAY_MS / 1000.0) * attempt))
                continue

            payload_probe = _parse_mcp_result(delegated.get("result")) if isinstance(delegated, dict) else delegated
            final_answer = ""
            if isinstance(payload_probe, dict):
                inner = payload_probe.get("result") if isinstance(payload_probe.get("result"), dict) else payload_probe
                if isinstance(inner, dict):
                    final_answer = str(inner.get("final_answer", "") or "").strip()
            retryable = (
                not final_answer
                or (
                    final_answer.lower().startswith("[remote provider error")
                    and any(m in final_answer.lower() for m in ("http error 500", "http error 502", "http error 503", "http error 504", "http error 429", "timeout"))
                )
            )
            if retryable and attempt < attempts:
                await asyncio.sleep(min(1.5, (_PROVIDER_RETRY_BASE_DELAY_MS / 1000.0) * attempt))
                continue
            break
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

    payload_inner = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else payload
    delegate_error = ""
    if isinstance(payload_inner, dict):
        delegate_error = str(payload_inner.get("error", "") or "").strip()
        delegate_answer = str(payload_inner.get("final_answer", "") or "").strip()
        answer_low = delegate_answer.lower()
        if not delegate_error:
            if not delegate_answer:
                delegate_error = "Delegated session returned no final answer."
            elif answer_low.startswith("agent reached max iterations"):
                delegate_error = delegate_answer
            elif answer_low.startswith("model returned empty response"):
                delegate_error = delegate_answer
            elif answer_low.startswith("model error at iteration"):
                delegate_error = delegate_answer
            elif answer_low.startswith("[remote provider error"):
                delegate_error = delegate_answer

    return payload, (delegate_error or None)


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

    _agent_gc_sessions()

    slot = int(args.get("slot", 0))
    message = str(args.get("message", "")).strip()
    max_iterations = max(1, min(int(args.get("max_iterations", 5)), 200))
    max_tokens = int(args.get("max_tokens", 0)) or 512
    reset = bool(args.get("reset", False))
    session_id = str(args.get("session_id", "")).strip()
    granted_tools = args.get("granted_tools")

    context_strategy_in = args.get("context_strategy") or args.get("contextStrategy")
    context_window_in = args.get("context_window_size") if args.get("context_window_size") is not None else args.get("contextWindowSize")

    if not message:
        return {"error": "message is required"}

    # ── Session management ──
    if not session_id:
        session_id = f"agent_chat:{slot}:{_uuid.uuid4().hex[:10]}"
    if reset and session_id in _agent_sessions:
        del _agent_sessions[session_id]
    session = _agent_sessions.get(session_id)
    if isinstance(session, dict):
        try:
            existing_slot = int(session.get("slot"))
        except Exception:
            existing_slot = None
        if existing_slot is not None and existing_slot != slot:
            # Prevent cross-slot context leakage when callers reuse session_id across slots.
            session_id = f"{session_id}:slot{slot}"
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

    # Respect explicit grants exactly (including explicit empty list).
    if isinstance(granted_tools, list):
        session["granted_tools"] = [str(t) for t in granted_tools if str(t).strip()]

    depth_in = args.get("_agent_depth", session.get("delegation_depth", 0))
    try:
        delegation_depth = int(depth_in)
    except Exception:
        delegation_depth = 0
    if delegation_depth < 0:
        delegation_depth = 0

    context_strategy = _agent_normalize_context_strategy(
        context_strategy_in if context_strategy_in is not None else session.get("context_strategy", "sliding-window")
    )
    try:
        context_window_size = int(
            context_window_in if context_window_in is not None else session.get("context_window_size", _AGENT_CONTEXT_WINDOW_DEFAULT)
        )
    except Exception:
        context_window_size = _AGENT_CONTEXT_WINDOW_DEFAULT
    context_window_size = max(5, min(context_window_size, _AGENT_CONTEXT_WINDOW_MAX))

    session["delegation_depth"] = delegation_depth
    session["parent_session_id"] = str(args.get("_parent_session_id", session.get("parent_session_id", "")) or "")
    session["source"] = source
    session["client_id"] = client_id
    session["context_strategy"] = context_strategy
    session["context_window_size"] = context_window_size
    _now_ms = int(time.time() * 1000)
    session["updated_ts"] = _now_ms
    if "last_active_ts" not in session:
        session["last_active_ts"] = _now_ms
    if not isinstance(session.get("inbox"), list):
        session["inbox"] = []
    _agent_sessions[session_id] = session

    explicit_grants = isinstance(granted_tools, list)
    granted = [t for t in session.get("granted_tools", []) if t not in _AGENT_BLOCKED_TOOLS]
    if not granted and not explicit_grants:
        granted = [t for t in _AGENT_DEFAULT_GRANTED if t not in _AGENT_BLOCKED_TOOLS]

    # ── Get slot info ──
    slot_info_raw = await _call_tool("slot_info", {"slot": slot})
    slot_info_error = slot_info_raw.get("error") if isinstance(slot_info_raw, dict) else None
    slot_info = _parse_mcp_result(slot_info_raw.get("result")) or {}
    if slot_info_error:
        return {"error": f"slot_info failed for slot {slot}: {slot_info_error}"}

    slot_name = slot_info.get("name", f"slot_{slot}") if isinstance(slot_info, dict) else f"slot_{slot}"
    plugged = bool(slot_info.get("plugged")) if isinstance(slot_info, dict) else False
    if not plugged:
        return {"error": f"Slot {slot} is not plugged. Plug a model first."}

    model_source = ""
    if isinstance(slot_info, dict):
        model_source = str(slot_info.get("source") or slot_info.get("model_source") or "")
    model_timeout = _AGENT_MODEL_STEP_TIMEOUT_REMOTE if _is_remote_model_source(model_source) else _AGENT_MODEL_STEP_TIMEOUT_LOCAL
    tool_timeout = max(float(_AGENT_TOOL_STEP_TIMEOUT), float(model_timeout))
    delegate_timeout = max(tool_timeout, float(model_timeout) * 2.0)

    session_was_active = bool(session.get("active", False))
    session["active"] = True
    session["last_active_ts"] = int(time.time() * 1000)
    session["updated_ts"] = session["last_active_ts"]
    if not session_was_active:
        session["started_ts"] = session["last_active_ts"]
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
    session["chat_messages"] = chat_messages

    # ── Agent loop ──
    tool_calls_log = []
    final_answer = None
    iterations_used = 0
    loop_start = time.time()

    _broadcast_activity(
        "agent_chat", args,
        {"_phase": "start", "state": "running", "session_id": session_id,
         "slot": slot, "name": slot_name, "max_iterations": max_iterations,
         "granted_tools_count": len(granted),
         "context_strategy": context_strategy,
         "context_window_size": context_window_size},
        0, None, source=source, client_id=client_id,
    )

    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        step_start = time.time()
        session["updated_ts"] = int(time.time() * 1000)
        session["last_active_ts"] = session["updated_ts"]

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

        compact_meta = _agent_compact_chat_messages(session, context_strategy, context_window_size)
        chat_messages = session.get("chat_messages") if isinstance(session.get("chat_messages"), list) else chat_messages
        if isinstance(compact_meta, dict) and int(compact_meta.get("dropped") or 0) > 0:
            _broadcast_activity(
                "agent_chat",
                {
                    "_phase": "context_compact",
                    "session_id": session_id,
                    "slot": slot,
                    "iteration": iterations_used,
                    "strategy": context_strategy,
                    "window_size": context_window_size,
                    "dropped": int(compact_meta.get("dropped") or 0),
                },
                {"content": [{"type": "text", "text": json.dumps(compact_meta)}]},
                0,
                None,
                source="agent-inner",
                client_id=client_id,
            )

        # Nudge on last iteration
        if max_iterations > 1 and iteration == max_iterations - 1:
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
            model_raw = await asyncio.wait_for(_call_tool("invoke_slot", invoke_args), timeout=float(model_timeout))
            model_parsed = _parse_mcp_result(model_raw.get("result"))
        except asyncio.TimeoutError:
            final_answer = f"Model invocation timed out after {model_timeout}s at iteration {iterations_used}."
            break
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
        _mo = model_output.strip()
        _is_provider_transient = _mo.lower().startswith("[remote provider error") and any(
            marker in _mo.lower() for marker in ("http error 500", "http error 502", "http error 503", "http error 504", "http error 429", "timeout")
        )

        # ── Empty/provider-transient response retry: nudge the model and retry ──
        if (not _mo or _is_provider_transient) and iteration < max_iterations - 1:
            _reason = "provider transient failure" if _is_provider_transient else "empty model response"
            chat_messages.append({
                "role": "user",
                "content": (
                    f"Your previous response failed ({_reason}). You MUST respond with exactly one JSON object.\n"
                    'Either: {"tool": "tool_name", "args": {...}}\n'
                    'Or: {"final_answer": "your answer"}\n'
                    "Try again now."
                ),
            })
            _broadcast_activity(
                "agent_chat",
                {"_phase": "model_retry", "iteration": iterations_used, "session_id": session_id, "slot": slot, "reason": _reason},
                {"content": [{"type": "text", "text": f"Model retry triggered: {_reason}"}]},
                int((time.time() - step_start) * 1000), None,
                source="agent-inner", client_id=client_id,
            )
            if _is_provider_transient:
                await asyncio.sleep(min(1.2, (_PROVIDER_RETRY_BASE_DELAY_MS / 1000.0) * (1 + iteration)))
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
        session["chat_messages"] = chat_messages
        session["updated_ts"] = int(time.time() * 1000)
        session["last_active_ts"] = session["updated_ts"]

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

            if called_tool == "workflow_execute":
                wf_id = str(called_args.get("workflow_id", "") or "").strip()
                if not wf_id:
                    guard_msg = "workflow_execute requires workflow_id"
                    chat_messages.append({"role": "user", "content": guard_msg})
                    tool_calls_log.append({
                        "tool": called_tool, "args": called_args,
                        "result": "DENIED - " + guard_msg, "iteration": iteration,
                    })
                    continue
                # Keep autonomous workflow execution safe: disallow recursive chains.
                if delegation_depth >= _AGENT_MAX_DELEGATION_DEPTH:
                    guard_msg = f"workflow_execute blocked at delegation depth {delegation_depth}."
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
                    tool_result, tool_error = await asyncio.wait_for(
                        _agent_delegate_call(
                            caller_slot=slot,
                            caller_session_id=session_id,
                            caller_depth=delegation_depth,
                            called_args=normalized_args,
                            source="agent-inner",
                            client_id=client_id,
                        ),
                        timeout=delegate_timeout,
                    )
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result is not None else ""
                else:
                    tool_raw = await asyncio.wait_for(_call_tool(called_tool, normalized_args), timeout=tool_timeout)
                    # Keep agent-inner semantics aligned with external calls so models
                    # see normalized slot/state payloads instead of raw capsule output.
                    try:
                        tool_raw = await _postprocess_tool_result(
                            called_tool,
                            normalized_args if isinstance(normalized_args, dict) else {},
                            tool_raw if isinstance(tool_raw, dict) else {"result": {"content": [{"type": "text", "text": str(tool_raw)}]}},
                        )
                    except Exception:
                        pass
                    tool_result = _parse_mcp_result((tool_raw or {}).get("result")) if isinstance(tool_raw, dict) else None
                    tool_error = (tool_raw.get("error") if isinstance(tool_raw, dict) else None) or (tool_result.get("error") if isinstance(tool_result, dict) else None)
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result else ""
            except asyncio.TimeoutError:
                tool_result = None
                timeout_used = int(delegate_timeout if called_tool == "agent_delegate" else tool_timeout)
                tool_error = f"Tool '{called_tool}' timed out after {timeout_used}s"
                tool_result_str = f"ERROR: {tool_error}"
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
                "result": tool_result_str if tool_result_str else "",
                "error": str(tool_error) if tool_error else None,
                "result_chars": len(tool_result_str) if tool_result_str else 0,
                "duration_ms": tool_ms,
                "iteration": iteration,
            })

            session["updated_ts"] = int(time.time() * 1000)
            session["last_active_ts"] = session["updated_ts"]

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
            session["chat_messages"] = chat_messages
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
    dropped_pending = len(session.get("inbox") or [])
    if dropped_pending:
        session.setdefault("turns", []).append({
            "role": "system",
            "content": f"[AUTO-DRAIN] Discarded {dropped_pending} pending injected message(s) on session close.",
            "ts": int(time.time() * 1000),
        })
    session["inbox"] = []
    session["chat_messages"] = chat_messages
    session["active"] = False
    session["updated_ts"] = int(time.time() * 1000)
    session["last_active_ts"] = session["updated_ts"]
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
        "pending_messages": 0,
        "dropped_pending_messages": dropped_pending,
        "context_policy": {
            "strategy": context_strategy,
            "window_size": context_window_size,
            "compactions": int(session.get("context_compactions") or 0),
            "dropped_messages": int(session.get("context_dropped_messages") or 0),
            "summary_chars": len(str(session.get("context_summary") or "")),
        },
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

    # file_write checkpoint contract normalization:
    # - checkpoint_key returned by write is a pre-write backup snapshot
    # - add backup_checkpoint explicitly
    # - promote checkpoint_key to a post-write snapshot for deterministic diff flows
    if tool_name == "file_write" and isinstance(parsed, dict):
        _path = str(args.get("path") or parsed.get("path") or parsed.get("key") or "").strip()
        _auto_ck = str(parsed.get("checkpoint_key") or "").strip()
        if _path and _auto_ck and bool(parsed.get("replaced")):
            parsed["backup_checkpoint"] = _auto_ck
            parsed["backup_checkpoint_semantics"] = "pre_write_backup"
            try:
                _post_ck_raw = await _call_tool("file_checkpoint", {"path": _path, "message": "auto post-write snapshot"})
                _post_ck = _parse_mcp_result((_post_ck_raw or {}).get("result"))
                if isinstance(_post_ck, dict) and isinstance(_post_ck.get("checkpoint_key"), str):
                    _post_key_raw = str(_post_ck.get("checkpoint_key") or "").strip()
                    _post_key = _doc_decode_checkpoint_key(_post_key_raw) if _post_key_raw else ""
                    if _post_key:
                        parsed["checkpoint_key"] = _post_key
                        parsed["post_write_checkpoint"] = _post_key
                        parsed["checkpoint_semantics"] = "post_write_snapshot"
                        note = str(parsed.get("note") or "").strip()
                        extra = "checkpoint_key is post-write; backup_checkpoint is pre-write state"
                        parsed["note"] = (note + "; " + extra) if note else extra
                        return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                # Preserve backward compatibility when post-write snapshot creation fails.
                parsed["checkpoint_semantics"] = "pre_write_backup"
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

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

    # --- Normalize slot payloads and clear stale unloaded metadata ---
    def _normalize_unplugged_slot_fields(slot_obj: dict):
        try:
            idx = int(slot_obj.get("index", slot_obj.get("slot", 0)))
        except Exception:
            idx = 0
        slot_obj["plugged"] = False
        slot_obj["name"] = f"slot_{idx}"
        slot_obj["model_source"] = None
        slot_obj["source"] = None
        slot_obj["model"] = None
        slot_obj["status"] = "empty"
        slot_obj["model_type"] = None
        slot_obj["type"] = None

    if tool_name == "slot_info" and isinstance(parsed, dict):
        if not bool(parsed.get("plugged")):
            _normalize_unplugged_slot_fields(parsed)
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    if tool_name in ("list_slots", "council_status") and isinstance(parsed, dict):
        slots = parsed.get("slots")
        all_ids = parsed.get("all_ids")
        total = parsed.get("total")

        if isinstance(slots, list) and len(slots) > 0:
            normalized_slots = []
            for i, raw_slot in enumerate(slots):
                slot = dict(raw_slot) if isinstance(raw_slot, dict) else {}
                try:
                    idx = int(slot.get("index", i))
                except Exception:
                    idx = i
                slot["index"] = idx

                is_plugged = bool(slot.get("plugged"))
                if is_plugged:
                    src = slot.get("model_source") or slot.get("source")
                    if not src and not _is_default_slot_name(slot.get("name", "")):
                        src = slot.get("name")
                    slot["model_source"] = src
                    if slot.get("status") in (None, "", "empty"):
                        slot["status"] = "plugged"
                else:
                    _normalize_unplugged_slot_fields(slot)

                normalized_slots.append(slot)

            parsed["slots"] = normalized_slots
            parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(normalized_slots)]
            parsed["total"] = len(normalized_slots)

            try:
                plugged_sum = sum(1 for s in normalized_slots if bool(s.get("plugged")))
                stats = parsed.get("stats") if isinstance(parsed.get("stats"), dict) else {}
                pstats = stats.get("plugged") if isinstance(stats.get("plugged"), dict) else {}
                pstats["sum"] = plugged_sum
                pstats["min"] = False
                pstats["max"] = True if plugged_sum > 0 else False
                pstats["avg"] = round(plugged_sum / max(1, len(normalized_slots)), 2)
                stats["plugged"] = pstats
                parsed["stats"] = stats
            except Exception:
                pass

            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

        # Compact list_slots shape from some external MCP paths (no explicit slots[])
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
                    for s in enriched_slots:
                        _normalize_unplugged_slot_fields(s)
                    parsed["slots"] = enriched_slots
                    parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(enriched_slots)]
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

            for s in enriched_slots:
                if not bool(s.get("plugged")):
                    _normalize_unplugged_slot_fields(s)

            parsed["slots"] = enriched_slots
            parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(enriched_slots)]
            parsed["total"] = len(enriched_slots)
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

    def _is_retryable_provider_output(text: str) -> bool:
        s = str(text or "").strip()
        if not s:
            return True
        low = s.lower()
        if low.startswith("[remote provider error"):
            retry_markers = (
                "http error 500",
                "http error 502",
                "http error 503",
                "http error 504",
                "http error 429",
                "gateway",
                "timeout",
                "temporarily",
            )
            return any(m in low for m in retry_markers)
        return False

    # --- Fix compare: retry failures + reconstruct explicit slot filters when capsule returns [] ---
    if tool_name == "compare" and isinstance(parsed, dict):
        comparisons = parsed.get("comparisons", [])
        patched = False

        async def _slot_info_fresh(slot_idx: int) -> dict:
            try:
                si_raw = await _call_tool("slot_info", {"slot": int(slot_idx)})
                si_parsed = _parse_mcp_result((si_raw or {}).get("result"))
                if isinstance(si_parsed, dict) and si_parsed.get("_cached"):
                    _si_cr = await _call_tool("get_cached", {"cache_id": str(si_parsed["_cached"])})
                    _si_full = _parse_mcp_result((_si_cr or {}).get("result"))
                    if isinstance(_si_full, dict):
                        si_parsed = _si_full
                return si_parsed if isinstance(si_parsed, dict) else {}
            except Exception:
                return {}
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

        # Normalize stale empty-slot names against current slot state.
        # Some compare paths can leak historical unplugged labels.
        _needs_empty_name_refresh = False
        if isinstance(comparisons, list):
            for entry in comparisons:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("status", "")).lower() != "empty":
                    continue
                if not _is_default_slot_name(str(entry.get("name", "") or "")):
                    try:
                        int(entry.get("slot"))
                        _needs_empty_name_refresh = True
                        break
                    except Exception:
                        continue
        if _needs_empty_name_refresh:
            try:
                slot_name_by_idx = {}
                refresh_idxs = set()
                for entry in comparisons:
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("status", "")).lower() != "empty":
                        continue
                    try:
                        refresh_idxs.add(int(entry.get("slot")))
                    except Exception:
                        continue
                for idx in refresh_idxs:
                    si = await _slot_info_fresh(idx)
                    fresh_name = str(si.get("name") or f"slot_{idx}")
                    if str(si.get("status", "")).strip().lower() == "empty" and not _is_default_slot_name(fresh_name):
                        fresh_name = f"slot_{idx}"
                    slot_name_by_idx[idx] = fresh_name

                _renamed = False
                for entry in comparisons:
                    if not isinstance(entry, dict):
                        continue
                    if str(entry.get("status", "")).lower() != "empty":
                        continue
                    try:
                        idx = int(entry.get("slot"))
                    except Exception:
                        continue
                    fresh_name = slot_name_by_idx.get(idx, f"slot_{idx}")
                    if str(entry.get("name") or "") != fresh_name:
                        entry["name"] = fresh_name
                        _renamed = True

                if _renamed:
                    parsed["comparisons"] = comparisons
                    parsed["_normalized_empty_slot_names"] = True
                    return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

        # Some capsule builds return an empty comparisons list when explicit slots
        # are provided. Reconstruct deterministically at proxy level.
        requested_slots = args.get("slots")
        if isinstance(requested_slots, list) and requested_slots and isinstance(comparisons, list) and len(comparisons) == 0:
            try:
                slots_result = await _call_tool("list_slots", {})
                slots_parsed = _parse_mcp_result(slots_result.get("result"))
                if isinstance(slots_parsed, dict) and slots_parsed.get("_cached"):
                    _ls_cr = await _call_tool("get_cached", {"cache_id": str(slots_parsed["_cached"])})
                    _ls_full = _parse_mcp_result(_ls_cr.get("result"))
                    if isinstance(_ls_full, dict):
                        slots_parsed = _ls_full
                slots_list = slots_parsed.get("slots", []) if isinstance(slots_parsed, dict) else []
                slots_by_idx = {}
                slots_by_name = {}
                for s in slots_list:
                    if not isinstance(s, dict):
                        continue
                    try:
                        idx = int(s.get("index", s.get("slot", -1)))
                    except Exception:
                        continue
                    slots_by_idx[idx] = s
                    nm = str(s.get("name") or "").strip().lower()
                    if nm:
                        slots_by_name[nm] = idx

                selected = []
                selected_set = set()
                unresolved = []
                for token in requested_slots:
                    idx = None
                    if isinstance(token, int):
                        idx = token
                    else:
                        raw = str(token).strip()
                        low = raw.lower()
                        if low.lstrip("+-").isdigit():
                            idx = int(low)
                        elif low.startswith("s") and low[1:].isdigit():
                            idx = int(low[1:]) - 1
                        elif low in slots_by_name:
                            idx = slots_by_name[low]
                    if idx is None:
                        unresolved.append(str(token))
                        continue
                    if idx in selected_set:
                        continue
                    selected_set.add(idx)
                    selected.append(idx)

                rebuilt = []
                compare_text = str(args.get("input_text", "") or "")
                for idx in selected:
                    slot_info = await _slot_info_fresh(idx)
                    if not slot_info:
                        slot_info = slots_by_idx.get(idx, {})
                    slot_name = str(slot_info.get("name") or f"slot_{idx}")
                    is_plugged = bool(slot_info.get("plugged"))
                    if not is_plugged:
                        slot_name = f"slot_{idx}"
                        rebuilt.append({"slot": idx, "name": slot_name, "status": "empty"})
                        continue
                    out = await _retry_slot_generate(idx, compare_text)
                    if out:
                        rebuilt.append({
                            "slot": idx,
                            "name": slot_name,
                            "status": "ok",
                            "type": "generation",
                            "output": out,
                            "note": "proxy slot-filter execution",
                        })
                    else:
                        rebuilt.append({
                            "slot": idx,
                            "name": slot_name,
                            "status": "error",
                            "error": "No output from slot during proxy slot-filter fallback",
                        })

                for token in unresolved:
                    rebuilt.append({
                        "selector": token,
                        "status": "error",
                        "error": "Slot selector did not match any slot",
                    })

                parsed["comparisons"] = rebuilt
                parsed["note"] = "compare slot-filter executed by proxy"
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

    # --- Trace/CASCADE bridge + PII false-positive filtering ---
    def _return_parsed(payload: dict | list | str) -> dict:
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}

    # cascade_graph connections can return component-global data for event-scoped queries.
    # Rebuild event-local connections deterministically from get_causes/get_effects.
    if tool_name == "cascade_graph" and isinstance(parsed, dict):
        op = str(args.get("operation", "") or "").strip().lower()
        if op == "connections":
            params_raw = args.get("params")
            event_id = ""
            if isinstance(params_raw, str):
                try:
                    _pj = json.loads(params_raw)
                    if isinstance(_pj, dict):
                        event_id = str(_pj.get("event_id") or "").strip()
                except Exception:
                    event_id = ""
            elif isinstance(params_raw, dict):
                event_id = str(params_raw.get("event_id") or "").strip()
            if not event_id:
                event_id = str(args.get("event_id") or parsed.get("event_id") or "").strip()

            has_connections = isinstance(parsed.get("connections"), list) and len(parsed.get("connections")) > 0
            if event_id and not has_connections:
                try:
                    causes_raw = await _call_tool(
                        "cascade_graph",
                        {"operation": "get_causes", "params": json.dumps({"event_id": event_id})},
                    )
                    effects_raw = await _call_tool(
                        "cascade_graph",
                        {"operation": "get_effects", "params": json.dumps({"event_id": event_id})},
                    )
                    causes_parsed = _parse_mcp_result((causes_raw or {}).get("result"))
                    effects_parsed = _parse_mcp_result((effects_raw or {}).get("result"))
                    if isinstance(causes_parsed, dict) and causes_parsed.get("_cached"):
                        _cgc = await _call_tool("get_cached", {"cache_id": str(causes_parsed["_cached"])})
                        _cgc_p = _parse_mcp_result((_cgc or {}).get("result"))
                        if isinstance(_cgc_p, dict):
                            causes_parsed = _cgc_p
                    if isinstance(effects_parsed, dict) and effects_parsed.get("_cached"):
                        _cge = await _call_tool("get_cached", {"cache_id": str(effects_parsed["_cached"])})
                        _cge_p = _parse_mcp_result((_cge or {}).get("result"))
                        if isinstance(_cge_p, dict):
                            effects_parsed = _cge_p

                    causes = causes_parsed.get("causes", []) if isinstance(causes_parsed, dict) else []
                    effects = effects_parsed.get("effects", []) if isinstance(effects_parsed, dict) else []
                    if not isinstance(causes, list):
                        causes = []
                    if not isinstance(effects, list):
                        effects = []

                    bridged = []
                    for c in causes:
                        if isinstance(c, dict):
                            cid = str(c.get("event_id") or "").strip()
                            if cid:
                                bridged.append({"from": cid, "to": event_id, "direction": "cause"})
                    for e in effects:
                        if isinstance(e, dict):
                            eid = str(e.get("event_id") or "").strip()
                            if eid:
                                bridged.append({"from": event_id, "to": eid, "direction": "effect"})

                    parsed["event_id"] = event_id
                    parsed["causes"] = causes
                    parsed["effects"] = effects
                    parsed["connections"] = bridged
                    parsed["_bridge"] = {
                        "source": "cascade_graph.get_causes/get_effects",
                        "operation": "connections",
                        "event_id": event_id,
                    }
                    parsed["note"] = "Event-scoped connections reconstructed from get_causes/get_effects."
                    return _return_parsed(parsed)
                except Exception:
                    pass

    # trace_root_causes can miss existing causal links; bridge from cascade_graph for event ids.
    if tool_name == "trace_root_causes" and isinstance(parsed, dict):
        event_desc = str(args.get("event_description") or parsed.get("event") or "").strip()
        root_causes = parsed.get("root_causes")
        no_prior = isinstance(root_causes, list) and any("no prior events to trace" in str(rc).lower() for rc in root_causes)
        if no_prior and event_desc.startswith("evt_"):
            try:
                cg_raw = await _call_tool(
                    "cascade_graph",
                    {"operation": "get_causes", "params": json.dumps({"event_id": event_desc})},
                )
                cg_parsed = _parse_mcp_result((cg_raw or {}).get("result"))
                cg_causes = cg_parsed.get("causes", []) if isinstance(cg_parsed, dict) else []
                if isinstance(cg_causes, list) and cg_causes:
                    normalized = []
                    for cause in cg_causes:
                        if not isinstance(cause, dict):
                            normalized.append(str(cause))
                            continue
                        cid = str(cause.get("event_id", "") or "").strip()
                        comp = str(cause.get("component", "") or "").strip()
                        etype = str(cause.get("event_type", "") or "").strip()
                        line = "cascade_graph"
                        if comp:
                            line += f":{comp}"
                        if etype:
                            line += f":{etype}"
                        if cid:
                            line += f":{cid}"
                        normalized.append(line)
                    parsed["root_causes"] = normalized
                    parsed["root_causes_structured"] = cg_causes
                    parsed["trace_depth"] = max(1, len(cg_causes))
                    parsed["_bridge"] = {"source": "cascade_graph.get_causes", "event_id": event_desc, "cause_count": len(cg_causes)}
                    return _return_parsed(parsed)
            except Exception:
                pass

    # cascade_data pii_scan can overmatch decimal metrics as PHONE_NUMBER; filter deterministically.
    if tool_name == "cascade_data" and isinstance(parsed, dict):
        op = str(args.get("operation", "") or "").strip().lower()
        if op == "pii_scan":
            hits = parsed.get("pii_found")
            if isinstance(hits, list) and hits:
                import re as _re_pii

                params_raw = args.get("params")
                params_text = ""
                try:
                    if isinstance(params_raw, str):
                        pj = json.loads(params_raw)
                        if isinstance(pj, dict):
                            params_text = str(pj.get("text") or pj.get("data") or pj.get("input") or params_raw)
                        else:
                            params_text = params_raw
                    elif isinstance(params_raw, dict):
                        params_text = str(params_raw.get("text") or params_raw.get("data") or params_raw.get("input") or "")
                    else:
                        params_text = str(params_raw or "")
                except Exception:
                    params_text = str(params_raw or "")

                metric_context = any(tok in params_text.lower() for tok in ("fitness", "loss", "accuracy", "reward", "score", "rate", "critic"))
                filtered_hits = []
                removed = []
                for hit in hits:
                    if not isinstance(hit, dict):
                        filtered_hits.append(hit)
                        continue
                    htype = str(hit.get("type", "") or "").upper()
                    preview = str(hit.get("value_preview", "") or "").replace(" ", "")
                    if htype == "PHONE_NUMBER":
                        looks_decimal = bool(_re_pii.match(r"^\d+\.\d+\*{0,8}$", preview))
                        lacks_phone_chars = not any(ch in preview for ch in "+()-")
                        if metric_context and looks_decimal and lacks_phone_chars:
                            removed.append({"type": htype, "value_preview": preview, "reason": "decimal_metric_false_positive"})
                            continue
                    filtered_hits.append(hit)

                if removed:
                    parsed["pii_found"] = filtered_hits
                    parsed["count"] = len(filtered_hits)
                    parsed["_false_positive_filtered"] = removed
                    parsed["note"] = "Filtered decimal metric false positives from pii_scan."
                    return _return_parsed(parsed)

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

        # --- Strict-JSON contract normalization for deterministic debug/eval paths ---
        _req_msg = str(args.get("message", "") or "")
        _req_low = _req_msg.lower()
        _strict_json_requested = (
            "strict json" in _req_low
            or "json only" in _req_low
            or "return json" in _req_low
        )
        if _strict_json_requested:
            _fa_obj = _result.get("final_answer") if isinstance(_result.get("final_answer"), (dict, list)) else None
            if _fa_obj is None and isinstance(_fa, str) and _fa:
                _cand = _fa.strip()
                _m = _re.search(r"```(?:json)?\s*([\s\S]*?)```", _cand, flags=_re.IGNORECASE)
                if _m:
                    _cand = _m.group(1).strip()
                try:
                    _parsed_json = json.loads(_cand)
                    if isinstance(_parsed_json, (dict, list)):
                        _fa_obj = _parsed_json
                except Exception:
                    _fa_obj = None

            if _fa_obj is not None:
                if not isinstance(_result.get("final_answer"), (dict, list)):
                    _result["final_answer"] = _fa_obj
                    _result["_strict_json_normalized"] = True
                    _fa = json.dumps(_fa_obj)
            else:
                _result["contract_violation"] = {
                    "type": "strict_json_not_returned",
                    "expected": "json",
                    "received": "text",
                }
                _result["final_answer_raw"] = _fa
                _result["final_answer"] = {
                    "status": "contract_violation",
                    "violation": "strict_json_not_returned",
                    "tool_calls": len(_tc) if isinstance(_tc, list) else 0,
                }
                if "result" in parsed and isinstance(parsed["result"], dict):
                    parsed["result"] = _result
                else:
                    parsed = _result
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

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

    # --- Fix invoke_slot/generate: strip <think> blocks and retry transient provider failures ---
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
                _out = _clean
            elif tool_name == "invoke_slot" and args.get("slot") is not None and args.get("text"):
                # think-only or error-like output; try chat fallback for invoke_slot
                try:
                    _cf = await _call_tool("chat", {"slot": int(args.get("slot", 0)), "message": str(args.get("text", ""))})
                    _cfp = _parse_mcp_result(_cf.get("result"))
                    if isinstance(_cfp, dict):
                        _resp = str(_cfp.get("response", "")).strip()
                        if _resp and not _resp.lower().startswith("[remote provider error"):
                            parsed["output"] = _resp
                            parsed["_fallback"] = "chat_after_think_only"
                            _out = _resp
                except Exception:
                    pass

        if (
            tool_name == "invoke_slot"
            and _PROVIDER_RETRY_ENABLED
            and args.get("slot") is not None
            and args.get("text")
            and _is_retryable_provider_output(_out)
        ):
            _slot_idx = int(args.get("slot", 0))
            _text = str(args.get("text", "") or "")
            _retry_tokens = int(args.get("max_tokens", 300) or 300)
            _retry_out = await _retry_slot_generate(_slot_idx, _text, max_tokens=max(64, _retry_tokens))
            if _retry_out:
                parsed["output"] = _retry_out
                parsed["_fallback"] = "retry_generate"
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

        if "_think_stripped" in parsed or parsed.get("_fallback"):
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix chat: strip <think> blocks and retry transient provider/empty responses ---
    if tool_name == "chat" and isinstance(parsed, dict):
        _chat_changed = False
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
                _response = _clean
                _chat_changed = True
            else:
                _response = ""  # fall through to retry

        if (
            _PROVIDER_RETRY_ENABLED
            and args.get("message")
            and args.get("slot") is not None
            and _is_retryable_provider_output(_response)
        ):
            _slot = int(args.get("slot", 0))
            _retry_out = await _retry_slot_generate(_slot, str(args.get("message", "")), max_tokens=512)
            if _retry_out:
                parsed["response"] = _retry_out
                parsed["_fallback"] = "invoke_slot_retry"
                _chat_changed = True

        if _chat_changed:
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


async def _workflow_call_local_proxy_tool(tool_name: str, args: dict, source: str, client_id: str | None):
    if tool_name == "agent_chat_inject":
        return _agent_inject_message(args, source=source, client_id=client_id)
    if tool_name == "agent_chat_sessions":
        return _agent_session_snapshot(args)
    if tool_name == "agent_chat_result":
        return _agent_session_result(args)
    if tool_name == "agent_chat_purge":
        return _agent_session_purge(args)
    if tool_name == "agent_delegate":
        try:
            caller_slot = int(args.get("caller_slot", -1)) if str(args.get("caller_slot", "")).strip() else -1
        except Exception:
            caller_slot = -1
        try:
            caller_depth = int(args.get("_agent_depth", 0) or 0)
        except Exception:
            caller_depth = 0
        payload, err = await _agent_delegate_call(
            caller_slot=caller_slot,
            caller_session_id=str(args.get("caller_session_id", "workflow-exec") or "workflow-exec"),
            caller_depth=caller_depth,
            called_args=args,
            source=source,
            client_id=client_id,
        )
        if err:
            return {"error": err, "detail": payload}
        return payload
    if tool_name == "agent_chat":
        return await _server_side_agent_chat(args, source=source, client_id=client_id)
    if tool_name == "hf_cache_status":
        limit = max(1, min(int(args.get("limit", 200) or 200), 2000))
        force = bool(args.get("force", False))
        return await _hf_cache_status_payload(limit=limit, force=force)
    if tool_name == "hf_cache_clear":
        return await _hf_cache_clear_payload(
            model_id=str(args.get("model_id", "") or ""),
            keep_plugged=bool(args.get("keep_plugged", True)),
            dry_run=bool(args.get("dry_run", False)),
            hard_reclaim=bool(args.get("hard_reclaim", False)),
        )
    if tool_name == "capsule_restart":
        return await _restart_capsule_runtime(
            reason=str(args.get("reason", "workflow:capsule_restart") or "workflow:capsule_restart"),
            preserve_state=bool(args.get("preserve_state", True)),
            restore_state_after=bool(args.get("restore_state", True)),
        )
    if tool_name == "persist_status":
        return persistence.status() if hasattr(persistence, "status") else {"available": persistence.is_available()}
    if tool_name == "persist_restore_revision":
        revision = str(args.get("revision", "") or "").strip()
        if not revision:
            return {"error": "Missing revision"}
        if hasattr(persistence, "restore_state_revision"):
            return await persistence.restore_state_revision(
                _call_tool,
                revision=revision,
                promote_after_restore=bool(args.get("promote_after_restore", False)),
            )
        return {"error": "restore_state_revision not supported by persistence adapter"}
    if tool_name == "workflow_status":
        execution_id = str(args.get("execution_id", "") or "").strip()
        if not execution_id:
            return {"error": "workflow_status requires execution_id"}
        payload = await _workflow_proxy_get_execution(execution_id)
        if payload is None:
            return {"error": f"Execution not found: {execution_id}", "execution_id": execution_id, "proxy_execution": True}
        return payload
    if tool_name == "workflow_history":
        workflow_id = str(args.get("workflow_id", "") or "").strip() or None
        try:
            limit = int(args.get("limit", 50) or 50)
        except Exception:
            limit = 50
        rows = await _workflow_proxy_history(workflow_id=workflow_id, limit=limit)
        return {
            "workflow_id": workflow_id,
            "history": rows,
            "executions": rows,
            "count": len(rows),
            "proxy_execution": True,
        }
    return {"error": f"Unsupported local proxy tool: {tool_name}"}


async def _workflow_proxy_call_tool(
    tool_name: str,
    args: dict,
    source: str,
    client_id: str | None,
    activity_meta: dict | None = None,
):
    tname = str(tool_name or "").strip()
    call_args = args if isinstance(args, dict) else {}
    started = time.time()

    def _activity_args(base_args: dict | None) -> dict:
        if not isinstance(activity_meta, dict):
            return dict(base_args or {})
        workflow_id = str(activity_meta.get("workflow_id") or "").strip()
        execution_id = str(activity_meta.get("execution_id") or "").strip()
        node_id = str(activity_meta.get("node_id") or "").strip()
        target_id = str(activity_meta.get("target_id") or "").strip()
        if workflow_id and execution_id:
            return _workflow_trace_args(
                base_args if isinstance(base_args, dict) else {},
                workflow_id=workflow_id,
                execution_id=execution_id,
                node_id=node_id or None,
                target_id=target_id or None,
            )
        return dict(base_args or {})

    local_tools = _workflow_local_proxy_tool_names()
    if tname in local_tools or tname == "agent_chat":
        payload = await _workflow_call_local_proxy_tool(tname, call_args, source=source, client_id=client_id)
        duration_ms = int((time.time() - started) * 1000)
        err = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(
            tname,
            _activity_args(call_args),
            payload if isinstance(payload, dict) else {"result": payload},
            duration_ms,
            str(err) if err else None,
            source="agent-inner",
            client_id=client_id,
        )
        return payload

    if tname == "workflow_execute":
        payload = {"error": "Nested workflow_execute is blocked in proxy workflow mode"}
        _broadcast_activity(
            tname,
            _activity_args(call_args),
            payload,
            int((time.time() - started) * 1000),
            payload["error"],
            source="agent-inner",
            client_id=client_id,
        )
        return payload

    normalized_args = _normalize_proxy_tool_args(tname, call_args)
    slot_guard = await _slot_ready_guard(tname, normalized_args)
    if slot_guard:
        payload = {"error": slot_guard.get("error") or f"Slot readiness guard blocked {tname}", "slot_guard": slot_guard}
        _broadcast_activity(
            tname,
            _activity_args(normalized_args),
            payload,
            int((time.time() - started) * 1000),
            payload["error"],
            source="agent-inner",
            client_id=client_id,
        )
        return payload

    claim = None
    try:
        claim, busy_guard = await _claim_slot_execution(tname, normalized_args, source, client_id)
        if busy_guard:
            payload = {"error": busy_guard.get("error") or f"Slot busy while calling {tname}", "slot_busy": busy_guard}
            _broadcast_activity(
                tname,
                _activity_args(normalized_args),
                payload,
                int((time.time() - started) * 1000),
                payload["error"],
                source="agent-inner",
                client_id=client_id,
            )
            return payload

        raw = await _call_tool(tname, normalized_args)
        if isinstance(raw, dict) and raw.get("error"):
            payload = {"error": str(raw.get("error"))}
            _broadcast_activity(
                tname,
                _activity_args(normalized_args),
                payload,
                int((time.time() - started) * 1000),
                payload["error"],
                source="agent-inner",
                client_id=client_id,
            )
            return payload

        processed = await _postprocess_tool_result(tname, normalized_args, raw)
        if isinstance(processed, dict) and processed.get("error"):
            payload = {"error": str(processed.get("error"))}
            _broadcast_activity(
                tname,
                _activity_args(normalized_args),
                payload,
                int((time.time() - started) * 1000),
                payload["error"],
                source="agent-inner",
                client_id=client_id,
            )
            return payload
        parsed = _parse_mcp_result((processed or {}).get("result")) if isinstance(processed, dict) else None
        if isinstance(parsed, dict) and parsed.get("error"):
            payload = {"error": str(parsed.get("error")), "detail": parsed}
            _broadcast_activity(
                tname,
                _activity_args(normalized_args),
                payload,
                int((time.time() - started) * 1000),
                payload["error"],
                source="agent-inner",
                client_id=client_id,
            )
            return payload

        payload = parsed if parsed is not None else {}
        _broadcast_activity(
            tname,
            _activity_args(normalized_args),
            payload if isinstance(payload, dict) else {"result": payload},
            int((time.time() - started) * 1000),
            None,
            source="agent-inner",
            client_id=client_id,
        )
        return payload
    finally:
        await _release_slot_execution(claim)


def _workflow_proxy_requires_parallel_provider_fanout(defn: dict) -> bool:
    for node in defn.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ntype = str(node.get("type", "") or "")

        if ntype == "parallel":
            children = node.get("nodes") if isinstance(node.get("nodes"), list) else []
            if len(children) > 1:
                return True
            continue

        if ntype != "fan_out":
            continue

        params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
        node_tool = str(
            node.get("tool_name")
            or node.get("tool")
            or params.get("tool_name")
            or params.get("tool")
            or "invoke_slot"
        ).strip()
        if node_tool in ("invoke_slot", "chat", "agent_chat", "agent_delegate"):
            return True

        targets = node.get("targets")
        if not isinstance(targets, list):
            targets = params.get("targets") if isinstance(params.get("targets"), list) else []
        for t in targets or []:
            if not isinstance(t, dict):
                continue
            tn = str(t.get("tool_name") or t.get("tool") or node_tool or "invoke_slot").strip()
            if tn in ("invoke_slot", "chat", "agent_chat", "agent_delegate"):
                return True

    return False


async def _workflow_apply_embed_reroute(defn: dict) -> tuple[dict, list[dict], list[dict]]:
    """Reroute invoke_slot(mode=embed) on remote-provider slots to embed_text.

    Returns: (patched_definition, rewrites, issues)
    """
    patched = json.loads(json.dumps(defn))
    rewrites: list[dict] = []
    issues: list[dict] = []
    slot_cache: dict[int, dict] = {}

    async def _slot_is_remote(slot_idx: int) -> bool:
        if slot_idx not in slot_cache:
            raw = await _call_tool("slot_info", {"slot": int(slot_idx)})
            slot_cache[slot_idx] = _parse_mcp_result((raw or {}).get("result")) if isinstance(raw, dict) else {}
        info = slot_cache.get(slot_idx) if isinstance(slot_cache.get(slot_idx), dict) else {}
        src = str(info.get("source") or info.get("model_source") or "")
        return bool(src.startswith("http://") or src.startswith("https://"))

    for node in patched.get("nodes", []):
        if not isinstance(node, dict):
            continue
        ntype = str(node.get("type", "") or "")

        if ntype == "tool":
            tname = str(node.get("tool_name") or node.get("tool") or "").strip()
            params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
            mode = _workflow_get_invoke_mode(params)
            if tname == "invoke_slot" and mode == "embed":
                slot_raw = params.get("slot")
                try:
                    slot_idx = int(slot_raw)
                except Exception:
                    slot_idx = None
                if slot_idx is None:
                    continue
                if await _slot_is_remote(slot_idx):
                    if _WORKFLOW_EMBED_AUTOREROUTE:
                        text_val = params.get("text")
                        node["tool_name"] = "embed_text"
                        node["tool"] = "embed_text"
                        node["parameters"] = {"text": text_val if text_val is not None else ""}
                        rewrites.append({"node_id": node.get("id"), "slot": slot_idx, "rewrite": "invoke_slot(embed)->embed_text"})
                    else:
                        issues.append({"node_id": node.get("id"), "slot": slot_idx, "error": "invoke_slot embed on remote provider slot unsupported"})

        if ntype == "fan_out":
            targets = node.get("targets")
            if not isinstance(targets, list):
                params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
                targets = params.get("targets") if isinstance(params.get("targets"), list) else []
            for target in targets:
                if not isinstance(target, dict):
                    continue
                tname = str(target.get("tool_name") or target.get("tool") or "").strip()
                tparams = target.get("params") if isinstance(target.get("params"), dict) else (target.get("parameters") if isinstance(target.get("parameters"), dict) else {})
                mode = _workflow_get_invoke_mode(tparams)
                if tname == "invoke_slot" and mode == "embed":
                    slot_raw = tparams.get("slot")
                    try:
                        slot_idx = int(slot_raw)
                    except Exception:
                        slot_idx = None
                    if slot_idx is None:
                        continue
                    if await _slot_is_remote(slot_idx):
                        if _WORKFLOW_EMBED_AUTOREROUTE:
                            text_val = tparams.get("text")
                            target["tool_name"] = "embed_text"
                            target["tool"] = "embed_text"
                            if "params" in target and isinstance(target.get("params"), dict):
                                target["params"] = {"text": text_val if text_val is not None else ""}
                            elif "parameters" in target and isinstance(target.get("parameters"), dict):
                                target["parameters"] = {"text": text_val if text_val is not None else ""}
                            else:
                                target["params"] = {"text": text_val if text_val is not None else ""}
                            rewrites.append({"node_id": node.get("id"), "target_id": target.get("id"), "slot": slot_idx, "rewrite": "fan_out invoke_slot(embed)->embed_text"})
                        else:
                            issues.append({"node_id": node.get("id"), "target_id": target.get("id"), "slot": slot_idx, "error": "fan_out invoke_slot embed on remote provider slot unsupported"})

    return patched, rewrites, issues


async def _execute_proxy_workflow(
    defn: dict,
    workflow_id: str,
    input_payload: dict,
    source: str,
    client_id: str | None,
    execution_id: str | None = None,
) -> dict:
    started = time.time()
    execution_id = str(execution_id or f"proxy_exec_{uuid.uuid4().hex[:12]}")
    started_row = await _workflow_proxy_register_start(
        execution_id=execution_id,
        workflow_id=workflow_id,
        input_payload=input_payload if isinstance(input_payload, dict) else {},
        source=source,
        client_id=client_id,
    )
    started_at = str(started_row.get("started_at") or datetime.utcnow().isoformat())

    nodes = defn.get("nodes") if isinstance(defn.get("nodes"), list) else []
    connections = defn.get("connections") if isinstance(defn.get("connections"), list) else []

    nodes_by_id: dict[str, dict] = {}
    order: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id", "") or "").strip()
        if not nid:
            continue
        nodes_by_id[nid] = node
        order.append(nid)

    incoming: dict[str, list[str]] = {nid: [] for nid in order}
    outgoing: dict[str, list[str]] = {nid: [] for nid in order}
    indegree: dict[str, int] = {nid: 0 for nid in order}

    for conn in connections:
        if not isinstance(conn, dict):
            continue
        src = str(conn.get("from", "") or "").strip()
        dst = str(conn.get("to", "") or "").strip()
        if src in outgoing and dst in incoming:
            outgoing[src].append(dst)
            incoming[dst].append(src)
            indegree[dst] += 1

    queue = [nid for nid in order if indegree.get(nid, 0) == 0]
    node_outputs: dict[str, object] = {}
    node_states: dict[str, dict] = {}
    failed = None
    had_partial = False

    while queue:
        nid = queue.pop(0)
        node = nodes_by_id.get(nid) or {}
        ntype = str(node.get("type", "") or "").strip()
        nstart = time.time()

        try:
            if ntype == "input":
                out = input_payload
            elif ntype == "tool":
                tname = str(node.get("tool_name") or node.get("tool") or "").strip()
                params = node.get("parameters") if isinstance(node.get("parameters"), dict) else (node.get("args") if isinstance(node.get("args"), dict) else {})
                resolved_args = _workflow_resolve_value(params, node_outputs, input_payload)
                resolved_args = resolved_args if isinstance(resolved_args, dict) else {}
                out = await _workflow_proxy_call_tool(
                    tname,
                    resolved_args,
                    source=source,
                    client_id=client_id,
                    activity_meta={"workflow_id": workflow_id, "execution_id": execution_id, "node_id": nid},
                )
                if isinstance(out, dict) and out.get("error"):
                    raise RuntimeError(str(out.get("error")))
            elif ntype == "fan_out":
                targets = node.get("targets")
                if not isinstance(targets, list):
                    params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
                    targets = params.get("targets") if isinstance(params.get("targets"), list) else []
                tasks = []
                target_meta = []
                for i, target in enumerate(targets or []):
                    if not isinstance(target, dict):
                        continue
                    tid = str(target.get("id") or f"target_{i}")
                    tname = str(target.get("tool_name") or target.get("tool") or "").strip()
                    tparams = target.get("params") if isinstance(target.get("params"), dict) else (target.get("parameters") if isinstance(target.get("parameters"), dict) else (target.get("args") if isinstance(target.get("args"), dict) else {}))
                    resolved_args = _workflow_resolve_value(tparams, node_outputs, input_payload)
                    resolved_args = resolved_args if isinstance(resolved_args, dict) else {}
                    target_meta.append((tid, tname, resolved_args))
                    tasks.append(
                        _workflow_proxy_call_tool(
                            tname,
                            resolved_args,
                            source=source,
                            client_id=client_id,
                            activity_meta={
                                "workflow_id": workflow_id,
                                "execution_id": execution_id,
                                "node_id": nid,
                                "target_id": tid,
                            },
                        )
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
                out = {}
                failed_targets = {}
                for idx, res in enumerate(results):
                    tid, tname, _ = target_meta[idx]
                    if isinstance(res, Exception):
                        failed_targets[tid] = str(res)
                        out[tid] = {"error": str(res), "tool": tname}
                        continue
                    out[tid] = res
                    if isinstance(res, dict) and res.get("error"):
                        failed_targets[tid] = str(res.get("error"))
                if failed_targets:
                    out["error"] = f"{len(failed_targets)}/{len(results)} targets failed"
                    out["failed_targets"] = failed_targets
                    had_partial = True
            elif ntype == "merge":
                mode = str(((node.get("parameters") or {}).get("mode") if isinstance(node.get("parameters"), dict) else "") or "combine").strip().lower()
                upstream = {src: node_outputs.get(src) for src in incoming.get(nid, [])}
                if mode == "first":
                    out = next(iter(upstream.values()), None)
                else:
                    out = {"mode": mode or "combine", "data": upstream}
            elif ntype == "output":
                params = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
                if isinstance(params, dict) and "value" in params:
                    out = _workflow_resolve_value(params.get("value"), node_outputs, input_payload)
                else:
                    ups = incoming.get(nid, [])
                    if len(ups) == 1:
                        out = node_outputs.get(ups[0])
                    else:
                        out = {src: node_outputs.get(src) for src in ups}
            else:
                raise RuntimeError(f"Unknown node type: {ntype}")

            node_outputs[nid] = out
            elapsed_node_ms = int((time.time() - nstart) * 1000)
            if isinstance(out, dict) and out.get("error") and ntype == "fan_out":
                node_states[nid] = {
                    "status": "partial_failure",
                    "elapsed_ms": elapsed_node_ms,
                    "error": str(out.get("error")),
                    "output_keys": list(out.keys()),
                }
            else:
                node_states[nid] = {
                    "status": "completed",
                    "elapsed_ms": elapsed_node_ms,
                    "output_keys": list(out.keys()) if isinstance(out, dict) else [],
                }
        except Exception as exc:
            elapsed_node_ms = int((time.time() - nstart) * 1000)
            node_states[nid] = {
                "status": "failed",
                "elapsed_ms": elapsed_node_ms,
                "error": str(exc),
                "output_keys": [],
            }
            failed = (nid, str(exc))
            await _workflow_proxy_register_update(
                execution_id,
                status="failed",
                nodes_executed=len(node_states),
                node_states=node_states,
                elapsed_ms=int((time.time() - started) * 1000),
                output=None,
                error=f"Node {nid} failed: {exc}",
            )
            _broadcast_activity(
                "workflow_status",
                _workflow_trace_args({"execution_id": execution_id}, workflow_id=workflow_id, execution_id=execution_id, node_id=nid),
                {
                    "execution_id": execution_id,
                    "status": "failed",
                    "workflow_id": workflow_id,
                    "failed_node": nid,
                    "node_states": node_states,
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "proxy_execution": True,
                },
                0,
                f"Node {nid} failed: {exc}",
                source=source,
                client_id=client_id,
            )
            break

        await _workflow_proxy_register_update(
            execution_id,
            status="running",
            nodes_executed=len(node_states),
            node_states=node_states,
            elapsed_ms=int((time.time() - started) * 1000),
        )
        _broadcast_activity(
            "workflow_status",
            _workflow_trace_args({"execution_id": execution_id}, workflow_id=workflow_id, execution_id=execution_id, node_id=nid),
            {
                "execution_id": execution_id,
                "status": "running",
                "workflow_id": workflow_id,
                "nodes_executed": len(node_states),
                "node_states": node_states,
                "elapsed_ms": int((time.time() - started) * 1000),
                "proxy_execution": True,
            },
            0,
            None,
            source=source,
            client_id=client_id,
        )

        for nxt in outgoing.get(nid, []):
            indegree[nxt] = max(0, int(indegree.get(nxt, 0)) - 1)
            if indegree[nxt] == 0:
                queue.append(nxt)

    elapsed_ms = int((time.time() - started) * 1000)
    if failed:
        nid, err = failed
        payload = {
            "execution_id": execution_id,
            "status": "failed",
            "workflow_id": workflow_id,
            "error": f"Node {nid} failed: {err}",
            "failed_node": nid,
            "node_states": node_states,
            "started_at": started_at,
            "elapsed_ms": elapsed_ms,
            "proxy_execution": True,
        }
        await _workflow_proxy_register_update(
            execution_id,
            status="failed",
            nodes_executed=len(node_states),
            node_states=node_states,
            elapsed_ms=elapsed_ms,
            output=payload.get("output"),
            error=payload.get("error"),
        )
        return payload

    final_output = None
    if "output" in node_outputs:
        final_output = node_outputs.get("output")
    elif node_outputs:
        final_output = node_outputs.get(list(node_outputs.keys())[-1])

    status = "partial_failure" if had_partial else "completed"
    payload = {
        "execution_id": execution_id,
        "status": status,
        "workflow_id": workflow_id,
        "nodes_executed": len(node_states),
        "output": final_output,
        "node_states": node_states,
        "started_at": started_at,
        "elapsed_ms": elapsed_ms,
        "proxy_execution": True,
    }
    await _workflow_proxy_register_update(
        execution_id,
        status=status,
        nodes_executed=len(node_states),
        node_states=node_states,
        elapsed_ms=elapsed_ms,
        output=final_output,
        error=None,
    )
    _broadcast_activity(
        "workflow_status",
        _workflow_trace_args({"execution_id": execution_id}, workflow_id=workflow_id, execution_id=execution_id),
        payload,
        0,
        None,
        source=source,
        client_id=client_id,
    )
    return payload


async def _maybe_execute_workflow_proxy(call_args: dict, source: str, client_id: str | None) -> dict | None:
    if not _WORKFLOW_PROXY_EXECUTION_ENABLED:
        return None

    workflow_id = str(call_args.get("workflow_id", "") or "").strip()
    if not workflow_id:
        return None

    wf_raw = await _call_tool("workflow_get", {"workflow_id": workflow_id})
    wf_def = _parse_mcp_result((wf_raw or {}).get("result")) if isinstance(wf_raw, dict) else None
    if not isinstance(wf_def, dict):
        return None

    validated, validation_err = _workflow_validate_definition(wf_def)
    if validation_err:
        return {
            "error": f"Workflow validation failed: {validation_err}",
            "workflow_id": workflow_id,
            "phase": "validation",
        }

    patched, rewrites, issues = await _workflow_apply_embed_reroute(validated)
    if issues:
        return {
            "error": "Workflow preflight blocked execution",
            "workflow_id": workflow_id,
            "phase": "preflight",
            "issues": issues,
            "rewrites": rewrites,
        }

    requires_proxy = _workflow_contains_proxy_local_tools(patched) or _workflow_proxy_requires_parallel_provider_fanout(patched) or bool(rewrites)
    if not requires_proxy:
        return None

    if not _workflow_is_proxy_executable(patched):
        return {
            "error": "Workflow requires proxy tools/fan_out but includes unsupported node types for proxy execution",
            "workflow_id": workflow_id,
            "phase": "proxy_support",
        }

    raw_input = call_args.get("input_data", "")
    if isinstance(raw_input, dict):
        input_payload = raw_input
    elif isinstance(raw_input, str) and raw_input.strip():
        try:
            parsed = json.loads(raw_input)
            input_payload = parsed if isinstance(parsed, dict) else {"input": parsed}
        except Exception:
            input_payload = {"input": raw_input}
    else:
        input_payload = {}

    execution_id = f"proxy_exec_{uuid.uuid4().hex[:12]}"
    running_payload = {
        "execution_id": execution_id,
        "status": "running",
        "workflow_id": workflow_id,
        "node_states": {},
        "elapsed_ms": 0,
        "proxy_execution": True,
    }
    _broadcast_activity(
        "workflow_execute",
        _workflow_trace_args(call_args, workflow_id=workflow_id, execution_id=execution_id),
        running_payload,
        0,
        None,
        source=source,
        client_id=client_id,
    )

    exec_payload = await _execute_proxy_workflow(
        patched,
        workflow_id,
        input_payload,
        source=source,
        client_id=client_id,
        execution_id=execution_id,
    )
    if rewrites:
        exec_payload["preflight_rewrites"] = rewrites
    return exec_payload


@app.post("/api/tool/{tool_name}")
async def proxy_tool_call(tool_name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_body = dict(body) if isinstance(body, dict) else {}

    # Normalize + validate workflow definitions before they reach the capsule
    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        _def_src = body.get("definition")
        _def_obj, _def_err = _workflow_load_definition(_def_src)
        if _def_err:
            return JSONResponse(status_code=400, content={"error": _def_err})
        if tool_name == "workflow_update":
            _wf_id = str(body.get("workflow_id", "") or "").strip()
            if _wf_id and isinstance(_def_obj, dict) and not _def_obj.get("id"):
                _def_obj["id"] = _wf_id
        validated, validation_err = _workflow_validate_definition(_def_obj)
        if validation_err:
            return JSONResponse(status_code=400, content={"error": validation_err})
        body["definition"] = json.dumps(validated)

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

    if tool_name == "agent_chat_result":
        payload = _agent_session_result(body if isinstance(body, dict) else {})
        err = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, err, source=source, client_id=client_id)
        if err:
            return JSONResponse(status_code=404, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "agent_chat_purge":
        payload = _agent_session_purge(body if isinstance(body, dict) else {})
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

    if tool_name == "hf_cache_status":
        args = body if isinstance(body, dict) else {}
        try:
            limit = int(args.get("limit", 200) or 200)
        except Exception:
            limit = 200
        force = bool(args.get("force", False))
        payload = await _hf_cache_status_payload(limit=max(1, min(limit, 2000)), force=force)
        _broadcast_activity(tool_name, args, payload, 0, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "hf_cache_clear":
        args = body if isinstance(body, dict) else {}
        payload = await _hf_cache_clear_payload(
            model_id=str(args.get("model_id", "") or ""),
            keep_plugged=bool(args.get("keep_plugged", True)),
            dry_run=bool(args.get("dry_run", False)),
            hard_reclaim=bool(args.get("hard_reclaim", False)),
        )
        err_msg = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, args, payload, 0, err_msg, source=source, client_id=client_id)
        code = 200 if not err_msg else 503
        if err_msg:
            return JSONResponse(status_code=code, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "capsule_restart":
        args = body if isinstance(body, dict) else {}
        payload = await _restart_capsule_runtime(
            reason=str(args.get("reason", "api_tool:capsule_restart") or "api_tool:capsule_restart"),
            preserve_state=bool(args.get("preserve_state", True)),
            restore_state_after=bool(args.get("restore_state", True)),
        )
        err_msg = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, args, payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg:
            return JSONResponse(status_code=503, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "persist_status":
        payload = persistence.status() if hasattr(persistence, "status") else {"available": persistence.is_available()}
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, payload, 0, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "persist_restore_revision":
        args = body if isinstance(body, dict) else {}
        revision = str(args.get("revision", "") or "").strip()
        if not revision:
            payload = {"error": "Missing revision"}
            _broadcast_activity(tool_name, args, payload, 0, "Missing revision", source=source, client_id=client_id)
            return JSONResponse(status_code=400, content=payload)
        if hasattr(persistence, "restore_state_revision"):
            payload = await persistence.restore_state_revision(
                _call_tool,
                revision=revision,
                promote_after_restore=bool(args.get("promote_after_restore", False)),
            )
        else:
            payload = {"error": "restore_state_revision not supported by persistence adapter"}
        err_msg = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, args, payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg:
            return JSONResponse(status_code=503, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "workflow_status":
        args = body if isinstance(body, dict) else {}
        execution_id = str(args.get("execution_id", "") or "").strip()
        if execution_id:
            payload = await _workflow_proxy_get_execution(execution_id)
            if payload is None and execution_id.startswith("proxy_exec_"):
                payload = {
                    "execution_id": execution_id,
                    "status": "not_found",
                    "error": f"Execution not found: {execution_id}",
                    "proxy_execution": True,
                }
            if isinstance(payload, dict):
                err_msg = payload.get("error") if isinstance(payload, dict) else None
                _broadcast_activity(tool_name, args, payload, 0, err_msg, source=source, client_id=client_id)
                if err_msg:
                    return JSONResponse(status_code=404, content=payload)
                return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "workflow_history":
        args = body if isinstance(body, dict) else {}
        workflow_id = str(args.get("workflow_id", "") or "").strip() or None
        try:
            limit = int(args.get("limit", 50) or 50)
        except Exception:
            limit = 50
        proxy_rows = await _workflow_proxy_history(workflow_id=workflow_id, limit=limit)
        if proxy_rows:
            payload = {
                "workflow_id": workflow_id,
                "history": proxy_rows,
                "executions": proxy_rows,
                "count": len(proxy_rows),
                "proxy_execution": True,
            }
            _broadcast_activity(tool_name, args, payload, 0, None, source=source, client_id=client_id)
            return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "workflow_execute":
        wf_args = body if isinstance(body, dict) else {}
        proxy_payload = await _maybe_execute_workflow_proxy(wf_args, source=source, client_id=client_id)
        if proxy_payload is not None:
            err_msg = proxy_payload.get("error") if isinstance(proxy_payload, dict) else None
            _broadcast_activity(tool_name, wf_args, proxy_payload, 0, err_msg, source=source, client_id=client_id)
            if err_msg:
                return JSONResponse(status_code=409, content=proxy_payload)
            return {"result": {"content": [{"type": "text", "text": json.dumps(proxy_payload)}], "isError": False}}

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

    unplug_hard_reclaim = False
    pre_unplug_slot_info = None
    if tool_name == "unplug_slot":
        unplug_hard_reclaim = bool(call_args.pop("hard_reclaim", _UNPLUG_HARD_RECLAIM_DEFAULT))
        call_args.pop("allow_oom_risk", None)
        try:
            pre_slot = int(call_args.get("slot", 0))
            pre_info_raw = await _call_tool("slot_info", {"slot": pre_slot})
            pre_unplug_slot_info = _parse_mcp_result((pre_info_raw or {}).get("result")) if isinstance(pre_info_raw, dict) else None
        except Exception:
            pre_unplug_slot_info = None

    clone_pre_plugged: set[int] = set()
    clone_src = ""
    clone_requested_count = 1
    clone_pre_snapshot_ok = False
    if tool_name == "clone_slot":
        try:
            clone_requested_count = max(1, int(call_args.get("count", 1) or 1))
        except Exception:
            clone_requested_count = 1
        try:
            src_slot = int(call_args.get("slot", -1))
        except Exception:
            src_slot = -1
        try:
            if src_slot >= 0:
                src_info_raw = await _call_tool("slot_info", {"slot": src_slot})
                src_info = _parse_mcp_result((src_info_raw or {}).get("result")) if isinstance(src_info_raw, dict) else None
                if isinstance(src_info, dict):
                    clone_src = str(src_info.get("source") or src_info.get("model_source") or "")
            pre_ls_raw = await _call_tool("list_slots", {})
            pre_ls = _parse_mcp_result((pre_ls_raw or {}).get("result")) if isinstance(pre_ls_raw, dict) else None
            if isinstance(pre_ls, dict):
                clone_pre_snapshot_ok = True
                for s in pre_ls.get("slots") or []:
                    if not isinstance(s, dict):
                        continue
                    idx = s.get("slot") if s.get("slot") is not None else s.get("index")
                    try:
                        idx_i = int(idx)
                    except Exception:
                        continue
                    if bool(s.get("plugged")):
                        clone_pre_plugged.add(idx_i)
        except Exception:
            clone_pre_plugged = set()
            clone_src = ""
            clone_pre_snapshot_ok = False

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

    if tool_name in _LIVE_START_TOOLS and tool_name != "agent_chat":
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

        # Optional hard reclaim after unplugging locally loaded models.
        if tool_name == "unplug_slot" and unplug_hard_reclaim and isinstance(result, dict) and not result.get("error"):
            pre_src = ""
            if isinstance(pre_unplug_slot_info, dict):
                pre_src = str(pre_unplug_slot_info.get("source") or pre_unplug_slot_info.get("model_source") or "")
            is_local_pre = bool(pre_src) and not pre_src.startswith("http://") and not pre_src.startswith("https://")
            if is_local_pre or not pre_src:
                reclaim_payload = await _restart_capsule_runtime(
                    reason="unplug_slot:hard_reclaim",
                    preserve_state=True,
                    restore_state_after=True,
                )
                parsed_result = _parse_mcp_result(result.get("result")) if isinstance(result.get("result"), dict) else None
                if isinstance(parsed_result, dict):
                    parsed_result["hard_reclaim"] = reclaim_payload
                    result = {
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(parsed_result)}],
                            "isError": bool(reclaim_payload.get("error")),
                        }
                    }
                else:
                    result["hard_reclaim"] = reclaim_payload

        if tool_name == "clone_slot" and clone_pre_snapshot_ok and isinstance(result, dict) and not result.get("error"):
            try:
                parsed_result = _parse_mcp_result(result.get("result")) if isinstance(result.get("result"), dict) else None
                new_slots: list[int] = []

                post_ls_raw = await _call_tool("list_slots", {})
                post_ls = _parse_mcp_result((post_ls_raw or {}).get("result")) if isinstance(post_ls_raw, dict) else None
                if isinstance(post_ls, dict):
                    for s in post_ls.get("slots") or []:
                        if not isinstance(s, dict):
                            continue
                        idx = s.get("slot") if s.get("slot") is not None else s.get("index")
                        try:
                            idx_i = int(idx)
                        except Exception:
                            continue
                        if idx_i in clone_pre_plugged:
                            continue
                        if not bool(s.get("plugged")):
                            continue
                        if clone_src:
                            s_src = str(s.get("source") or s.get("model_source") or "")
                            if s_src and s_src != clone_src:
                                continue
                        new_slots.append(idx_i)

                if not new_slots and isinstance(parsed_result, dict):
                    fallback_slots = parsed_result.get("clone_slots") or parsed_result.get("slots") or []
                    for item in fallback_slots:
                        try:
                            idx_i = int(item)
                        except Exception:
                            continue
                        if idx_i in clone_pre_plugged:
                            continue
                        new_slots.append(idx_i)

                # Deterministic ordering + count cap to newly created slots only.
                new_slots = sorted(set(new_slots))[:clone_requested_count]

                if isinstance(parsed_result, dict):
                    parsed_result["clone_slots"] = new_slots
                    parsed_result["cloned"] = len(new_slots)
                    parsed_result["requested_clones"] = clone_requested_count
                    result = {
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(parsed_result)}],
                            "isError": False,
                        }
                    }
            except Exception:
                pass

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


@app.post("/api/capsule/restart")
async def capsule_restart(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}

    payload = await _restart_capsule_runtime(
        reason=str(body.get("reason", "api:capsule_restart") or "api:capsule_restart"),
        preserve_state=bool(body.get("preserve_state", True)),
        restore_state_after=bool(body.get("restore_state", True)),
    )
    err = payload.get("error") if isinstance(payload, dict) else None
    _broadcast_activity("capsule_restart", body, payload, 0, err, source=source, client_id=client_id)
    if err:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/api/cache/hf/status")
async def hf_cache_status(limit: int = 200, force: bool = False):
    limit = max(1, min(int(limit), 2000))
    payload = await _hf_cache_status_payload(limit=limit, force=bool(force))
    return payload


@app.post("/api/cache/hf/clear")
async def hf_cache_clear(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}

    payload = await _hf_cache_clear_payload(
        model_id=str(body.get("model_id", "") or ""),
        keep_plugged=bool(body.get("keep_plugged", True)),
        dry_run=bool(body.get("dry_run", False)),
        hard_reclaim=bool(body.get("hard_reclaim", False)),
    )
    code = 200 if payload.get("status") in ("ok", "dry_run") else 207
    if payload.get("error"):
        code = 503
    return JSONResponse(status_code=code, content=payload)


@app.post("/api/persist/save")
async def persist_save():
    """Manually trigger a state save (local snapshot + optional HF sync)."""
    if not persistence.is_available():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Persistence not available",
                "status": persistence.status() if hasattr(persistence, "status") else {},
            },
        )
    try:
        ok = await persistence.save_state(_call_tool, force=True)
    except TypeError:
        ok = await persistence.save_state(_call_tool)
    return {"status": "saved" if ok else "failed"}


@app.post("/api/persist/restore")
async def persist_restore():
    """Manually trigger state restore (local snapshot first, then optional HF sync)."""
    if not persistence.is_available():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Persistence not available",
                "status": persistence.status() if hasattr(persistence, "status") else {},
            },
        )
    ok = await persistence.restore_state(_call_tool)
    return {"status": "restored" if ok else "failed"}


@app.post("/api/persist/restore_revision")
async def persist_restore_revision(request: Request):
    """Restore persisted state from a specific HF dataset revision/commit hash."""
    if not persistence.is_available():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Persistence not available",
                "status": persistence.status() if hasattr(persistence, "status") else {},
            },
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}

    revision = str(body.get("revision", "") or "").strip()
    if not revision:
        return JSONResponse(status_code=400, content={"error": "Missing revision"})

    if not hasattr(persistence, "restore_state_revision"):
        return JSONResponse(status_code=501, content={"error": "restore_state_revision not supported"})

    payload = await persistence.restore_state_revision(
        _call_tool,
        revision=revision,
        promote_after_restore=bool(body.get("promote_after_restore", False)),
    )
    code = 200
    if isinstance(payload, dict) and payload.get("error"):
        code = 503
    return JSONResponse(status_code=code, content=payload if isinstance(payload, dict) else {"status": "failed"})


@app.get("/api/persist/status")
async def persist_status():
    """Check persistence configuration status."""
    if hasattr(persistence, "status"):
        return persistence.status()
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


@app.get("/api/agent_chat/result")
async def api_agent_chat_result(request: Request, session_id: str = "", slot: int | None = None):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    args = {"session_id": str(session_id or "")}
    if slot is not None:
        args["slot"] = int(slot)
    payload = _agent_session_result(args)
    err = payload.get("error") if isinstance(payload, dict) else None
    _broadcast_activity("agent_chat_result", args, payload, 0, err, source=source, client_id=client_id)
    if err:
        return JSONResponse(status_code=404, content=payload)
    return payload


@app.post("/api/agent_chat/purge")
async def api_agent_chat_purge(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    payload = _agent_session_purge(body)
    _broadcast_activity("agent_chat_purge", body, payload, 0, None, source=source, client_id=client_id)
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

    # Local proxy tools should work even for SSE-only MCP clients.
    _local_proxy_tools = {
        "agent_delegate", "agent_chat_inject", "agent_chat_sessions",
        "agent_chat_result", "agent_chat_purge", "workflow_execute", "workflow_status", "workflow_history",
        "hf_cache_status", "hf_cache_clear", "capsule_restart",
        "persist_status", "persist_restore_revision",
    }
    if len(rpc_calls) == 1 and rpc_calls[0].get("tool") in _local_proxy_tools:
        call = rpc_calls[0]
        rpc_obj = {
            "jsonrpc": "2.0",
            "id": call.get("rpc_id"),
            "method": "tools/call",
            "params": {"name": call.get("tool"), "arguments": call.get("args") or {}},
        }
        handled = await _handle_streamable_rpc(rpc_obj, _mcp_client_id)
        if handled is None:
            return Response(status_code=202)
        return JSONResponse(status_code=200, content=handled)

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
    response_payload_override = None
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
                            response_payload_override = resp_json
                        elif isinstance(resp_json, list):
                            response_items = [item for item in resp_json if isinstance(item, dict)]
                            response_payload_override = resp_json
                    except Exception:
                        response_items = []
                        response_payload_override = None

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

                        result_payload = item.get("result")
                        if error_str is None and isinstance(result_payload, dict):
                            try:
                                processed = await _postprocess_tool_result(call["tool"], call["args"], {"result": result_payload})
                                if isinstance(processed, dict) and isinstance(processed.get("result"), dict):
                                    result_payload = processed.get("result")
                                    item["result"] = result_payload
                            except Exception:
                                pass

                        _broadcast_activity(
                            call["tool"],
                            call["args"],
                            result_payload,
                            duration_ms,
                            error_str,
                            source="external", client_id=_mcp_client_id,
                        )
                        # Cache-aware inner tool call broadcasting for agent_chat
                        if call["tool"] == "agent_chat" and result_payload:
                            _bac_parsed = _parse_mcp_result(result_payload)
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
                            _broadcast_agent_inner_calls(call["tool"], result_payload, duration_ms, source="external", client_id=_mcp_client_id)
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
                if response_payload_override is not None:
                    return JSONResponse(content=response_payload_override, status_code=resp.status_code)
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
        _fallback_instructions = "Use tools/call for all operations. For large payloads, follow _cached via get_cached(cache_id). agent_chat supports granted_tools for agentic tool use. Local proxy tools: agent_delegate, agent_chat_inject, agent_chat_sessions, agent_chat_result, agent_chat_purge, workflow_execute, hf_cache_status, hf_cache_clear, capsule_restart, persist_status, persist_restore_revision."
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
            _def_obj, _def_err = _workflow_load_definition(args.get("definition"))
            if _def_err:
                return _rpc_error(rpc_id, -32602, "Invalid workflow definition", _def_err)
            if tool_name == "workflow_update":
                _wf_id = str(args.get("workflow_id", "") or "").strip()
                if _wf_id and isinstance(_def_obj, dict) and not _def_obj.get("id"):
                    _def_obj["id"] = _wf_id
            validated, validation_err = _workflow_validate_definition(_def_obj)
            if validation_err:
                return _rpc_error(rpc_id, -32602, "Invalid workflow definition", validation_err)
            args = dict(args)
            args["definition"] = json.dumps(validated)

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

        if tool_name == "agent_chat_result":
            payload = _agent_session_result(args)
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32012, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "agent_chat_purge":
            payload = _agent_session_purge(args)
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

        if tool_name == "hf_cache_status":
            try:
                limit = int(args.get("limit", 200) or 200)
            except Exception:
                limit = 200
            force = bool(args.get("force", False))
            payload = await _hf_cache_status_payload(limit=max(1, min(limit, 2000)), force=force)
            _broadcast_activity(tool_name, args, payload, 0, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "hf_cache_clear":
            payload = await _hf_cache_clear_payload(
                model_id=str(args.get("model_id", "") or ""),
                keep_plugged=bool(args.get("keep_plugged", True)),
                dry_run=bool(args.get("dry_run", False)),
                hard_reclaim=bool(args.get("hard_reclaim", False)),
            )
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "capsule_restart":
            payload = await _restart_capsule_runtime(
                reason=str(args.get("reason", "mcp:capsule_restart") or "mcp:capsule_restart"),
                preserve_state=bool(args.get("preserve_state", True)),
                restore_state_after=bool(args.get("restore_state", True)),
            )
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "persist_status":
            payload = persistence.status() if hasattr(persistence, "status") else {"available": persistence.is_available()}
            _broadcast_activity(tool_name, args, payload, 0, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "persist_restore_revision":
            revision = str(args.get("revision", "") or "").strip()
            if not revision:
                return _rpc_error(rpc_id, -32602, "Invalid request parameters", "Missing revision")
            if hasattr(persistence, "restore_state_revision"):
                payload = await persistence.restore_state_revision(
                    _call_tool,
                    revision=revision,
                    promote_after_restore=bool(args.get("promote_after_restore", False)),
                )
            else:
                payload = {"error": "restore_state_revision not supported by persistence adapter"}
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "workflow_status":
            execution_id = str(args.get("execution_id", "") or "").strip()
            if execution_id:
                payload = await _workflow_proxy_get_execution(execution_id)
                if payload is None and execution_id.startswith("proxy_exec_"):
                    payload = {
                        "execution_id": execution_id,
                        "status": "not_found",
                        "error": f"Execution not found: {execution_id}",
                        "proxy_execution": True,
                    }
                if isinstance(payload, dict):
                    err_msg = payload.get("error") if isinstance(payload, dict) else None
                    _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
                    if err_msg:
                        return _rpc_error(rpc_id, -32014, err_msg, payload)
                    return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "workflow_history":
            workflow_id = str(args.get("workflow_id", "") or "").strip() or None
            try:
                limit = int(args.get("limit", 50) or 50)
            except Exception:
                limit = 50
            proxy_rows = await _workflow_proxy_history(workflow_id=workflow_id, limit=limit)
            if proxy_rows:
                payload = {
                    "workflow_id": workflow_id,
                    "history": proxy_rows,
                    "executions": proxy_rows,
                    "count": len(proxy_rows),
                    "proxy_execution": True,
                }
                _broadcast_activity(tool_name, args, payload, 0, None, source="external", client_id=client_id)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "workflow_execute":
            proxy_payload = await _maybe_execute_workflow_proxy(args, source="external", client_id=client_id)
            if proxy_payload is not None:
                err_msg = proxy_payload.get("error") if isinstance(proxy_payload, dict) else None
                _broadcast_activity(tool_name, args, proxy_payload, 0, err_msg, source="external", client_id=client_id)
                if err_msg:
                    return _rpc_error(rpc_id, -32603, err_msg, proxy_payload)
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(proxy_payload)}], "isError": False}}

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

        if tool_name in _LIVE_START_TOOLS and tool_name != "agent_chat":
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

        unplug_hard_reclaim = False
        pre_unplug_slot_info = None
        if tool_name == "unplug_slot":
            unplug_hard_reclaim = bool(args.pop("hard_reclaim", _UNPLUG_HARD_RECLAIM_DEFAULT))
            args.pop("allow_oom_risk", None)
            try:
                pre_slot = int(args.get("slot", 0))
                pre_info_raw = await _call_tool("slot_info", {"slot": pre_slot})
                pre_unplug_slot_info = _parse_mcp_result((pre_info_raw or {}).get("result")) if isinstance(pre_info_raw, dict) else None
            except Exception:
                pre_unplug_slot_info = None

        clone_pre_plugged: set[int] = set()
        clone_src = ""
        clone_requested_count = 1
        clone_pre_snapshot_ok = False
        if tool_name == "clone_slot":
            try:
                clone_requested_count = max(1, int(args.get("count", 1) or 1))
            except Exception:
                clone_requested_count = 1
            try:
                src_slot = int(args.get("slot", -1))
            except Exception:
                src_slot = -1
            try:
                if src_slot >= 0:
                    src_info_raw = await _call_tool("slot_info", {"slot": src_slot})
                    src_info = _parse_mcp_result((src_info_raw or {}).get("result")) if isinstance(src_info_raw, dict) else None
                    if isinstance(src_info, dict):
                        clone_src = str(src_info.get("source") or src_info.get("model_source") or "")
                pre_ls_raw = await _call_tool("list_slots", {})
                pre_ls = _parse_mcp_result((pre_ls_raw or {}).get("result")) if isinstance(pre_ls_raw, dict) else None
                if isinstance(pre_ls, dict):
                    clone_pre_snapshot_ok = True
                    for s in pre_ls.get("slots") or []:
                        if not isinstance(s, dict):
                            continue
                        idx = s.get("slot") if s.get("slot") is not None else s.get("index")
                        try:
                            idx_i = int(idx)
                        except Exception:
                            continue
                        if bool(s.get("plugged")):
                            clone_pre_plugged.add(idx_i)
            except Exception:
                clone_pre_plugged = set()
                clone_src = ""
                clone_pre_snapshot_ok = False

        start = time.time()
        try:
            result = await _call_tool(tool_name, args)
            result = await _postprocess_tool_result(tool_name, args, result)

            if tool_name == "unplug_slot" and unplug_hard_reclaim and isinstance(result, dict) and not result.get("error"):
                pre_src = ""
                if isinstance(pre_unplug_slot_info, dict):
                    pre_src = str(pre_unplug_slot_info.get("source") or pre_unplug_slot_info.get("model_source") or "")
                is_local_pre = bool(pre_src) and not pre_src.startswith("http://") and not pre_src.startswith("https://")
                if is_local_pre or not pre_src:
                    reclaim_payload = await _restart_capsule_runtime(
                        reason="unplug_slot:hard_reclaim",
                        preserve_state=True,
                        restore_state_after=True,
                    )
                    parsed_result = _parse_mcp_result(result.get("result")) if isinstance(result.get("result"), dict) else None
                    if isinstance(parsed_result, dict):
                        parsed_result["hard_reclaim"] = reclaim_payload
                        result = {
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(parsed_result)}],
                                "isError": bool(reclaim_payload.get("error")),
                            }
                        }
                    else:
                        result["hard_reclaim"] = reclaim_payload

            if tool_name == "clone_slot" and clone_pre_snapshot_ok and isinstance(result, dict) and not result.get("error"):
                try:
                    parsed_result = _parse_mcp_result(result.get("result")) if isinstance(result.get("result"), dict) else None
                    new_slots: list[int] = []

                    post_ls_raw = await _call_tool("list_slots", {})
                    post_ls = _parse_mcp_result((post_ls_raw or {}).get("result")) if isinstance(post_ls_raw, dict) else None
                    if isinstance(post_ls, dict):
                        for s in post_ls.get("slots") or []:
                            if not isinstance(s, dict):
                                continue
                            idx = s.get("slot") if s.get("slot") is not None else s.get("index")
                            try:
                                idx_i = int(idx)
                            except Exception:
                                continue
                            if idx_i in clone_pre_plugged:
                                continue
                            if not bool(s.get("plugged")):
                                continue
                            if clone_src:
                                s_src = str(s.get("source") or s.get("model_source") or "")
                                if s_src and s_src != clone_src:
                                    continue
                            new_slots.append(idx_i)

                    if not new_slots and isinstance(parsed_result, dict):
                        fallback_slots = parsed_result.get("clone_slots") or parsed_result.get("slots") or []
                        for item in fallback_slots:
                            try:
                                idx_i = int(item)
                            except Exception:
                                continue
                            if idx_i in clone_pre_plugged:
                                continue
                            new_slots.append(idx_i)

                    new_slots = sorted(set(new_slots))[:clone_requested_count]

                    if isinstance(parsed_result, dict):
                        parsed_result["clone_slots"] = new_slots
                        parsed_result["cloned"] = len(new_slots)
                        parsed_result["requested_clones"] = clone_requested_count
                        result = {
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(parsed_result)}],
                                "isError": False,
                            }
                        }
                except Exception:
                    pass

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
