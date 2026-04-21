"""
Champion Council runtime gateway.
Serves the operational panel, proxies capsule tool calls, and exposes the spatial substrate to browser and MCP-facing clients.

Architecture:
  1. The capsule runs as an MCP/SSE server on MCP_PORT
  2. FastAPI serves the operational theater and panel on WEB_PORT
  3. FastAPI proxies browser requests into the capsule, activity surfaces, and environment state
"""
import os
import sys
import json
import base64
import asyncio
import importlib.util
import subprocess
import shutil
import threading
import mimetypes
import tempfile
import re
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlsplit, urlunsplit, unquote, parse_qsl

import uvicorn
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from mcp import ClientSession
from mcp.client.sse import sse_client

import time
import uuid
import persistence
import pack_storage
from continuity_restore import continuity_restore_payload, continuity_status_payload

# Ensure Starlette static serving emits correct MIME for audio container files.
mimetypes.add_type("audio/mp4", ".m4a")

# Track last chat slot — auto-reset capsule chat session on slot change
_last_chat_slot: int | None = None

# Tools that are internal plumbing — don't broadcast to activity feed
_SILENT_TOOLS = frozenset([
    'get_status', 'list_slots', 'bag_catalog', 'workflow_list',
    'verify_integrity', 'get_cached', 'get_identity', 'feed',
    'get_capabilities', 'get_help', 'get_onboarding', 'get_quickstart',
    'hub_tasks', 'list_tools', 'heartbeat', 'api_health', 'env_help',
    'env_report',
])

_ENV_CAPTURE_DIR = Path("static") / "captures"
_ENV_CAPTURE_INDEX_PATH = _ENV_CAPTURE_DIR / "_index.json"
_ENV_CAPTURE_LIMIT = 20
_ENV_HELP_DATA_PATH = Path("static") / "data" / "help" / "environment_command_registry.json"
_env_capture_history: list[dict] = []
_env_capture_lock = threading.Lock()
_env_help_cache_lock = threading.Lock()
_env_help_cache: dict[str, object] = {"mtime_ns": None, "data": None}
_env_live_cache_lock = threading.Lock()
_env_live_cache: dict[str, object] = {"live_state": None, "updated_ms": 0}
_env_text_theater_read_gate_lock = threading.Lock()
_env_text_theater_read_gate: dict[str, object] = {
    "updated_ms": 0,
    "snapshot_timestamp": 0,
    "query": "",
    "observed_at_ms": 0,
    "visual_updated_ms": 0,
    "visual_snapshot_timestamp": 0,
    "visual_query": "",
    "visual_capture_ts": 0,
    "visual_observed_at_ms": 0,
}
_env_control_command_seq_lock = threading.Lock()
_env_control_command_seq = 0
_text_theater_module_lock = threading.Lock()
_text_theater_module = None
_text_theater_module_mtime_ns = None


def _env_help_unique_list(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _env_help_apply_registry_overrides(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    commands = data.get("commands") if isinstance(data.get("commands"), dict) else None
    if not commands:
        return data

    editing_entry = commands.get("workbench_set_editing_mode")
    if isinstance(editing_entry, dict):
        patched = dict(editing_entry)
        patched["summary"] = "Switch the builder between pose and structure editing modes."
        target_contract = dict(patched.get("target_contract") or {})
        target_contract.update({
            "shape": "string_or_json",
            "description": "Builder editing mode. Valid modes are pose and structure; JSON payloads may use an editing_mode field.",
            "examples": [
                "pose",
                "structure",
                "{\"editing_mode\":\"pose\"}",
                "{\"editing_mode\":\"structure\"}",
            ],
        })
        patched["target_contract"] = target_contract
        availability = dict(patched.get("availability") or {})
        availability["valid_editing_modes"] = ["pose", "structure"]
        patched["availability"] = availability
        patched["gotchas"] = _env_help_unique_list([
            *(patched.get("gotchas") or []),
            "Valid builder editing modes are pose and structure.",
            "Local gizmo modes such as rotate/translate and spaces such as local/world are separate controls; use workbench_set_gizmo_mode or workbench_set_gizmo_space for those.",
        ])
        commands["workbench_set_editing_mode"] = patched

    reset_entry = commands.get("workbench_reset_angles")
    if isinstance(reset_entry, dict):
        patched = dict(reset_entry)
        patched["summary"] = "Reset the selected builder bone, a supplied target bone, or all bones back toward neutral angles."
        target_contract = dict(patched.get("target_contract") or {})
        target_contract.update({
            "shape": "string_or_json",
            "description": "Reset target for the builder angle reset path. Accepts one bone id, all, or JSON payloads naming bone/all.",
            "examples": [
                "hips",
                "all",
                "{\"bone\":\"hips\"}",
                "{\"all\":true}",
            ],
        })
        patched["target_contract"] = target_contract
        availability = dict(patched.get("availability") or {})
        availability["required_editing_mode"] = ["structure"]
        patched["availability"] = availability
        patched["gotchas"] = _env_help_unique_list([
            *(patched.get("gotchas") or []),
            "workbench_reset_angles is gated to structure mode; pose mode rejects the reset.",
            "Without an explicit target, the reset falls back to the currently selected bone.",
        ])
        commands["workbench_reset_angles"] = patched

    return data


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
_plug_exec_gate = asyncio.Lock()
_plug_exec_active: dict[str, dict] = {}


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


def _plug_exec_key(tool_name: str, args: dict | None) -> str | None:
    if tool_name not in ("plug_model", "hub_plug"):
        return None
    if not isinstance(args, dict):
        return None
    model_id = str(args.get("model_id", "") or "").strip()
    if not model_id:
        return None
    slot_name = str(args.get("slot_name", "") or "").strip()
    return f"{tool_name}|{model_id}|{slot_name}"


async def _claim_plug_execution(tool_name: str, args: dict | None, source: str, client_id: str | None) -> tuple[dict | None, dict | None]:
    key = _plug_exec_key(tool_name, args)
    if key is None:
        return None, None
    now_ms = int(time.time() * 1000)
    async with _plug_exec_gate:
        active = _plug_exec_active.get(key)
        if active:
            started_ms = active.get("started_ms")
            running_for_ms = None
            try:
                if started_ms is not None:
                    running_for_ms = max(0, now_ms - int(started_ms))
            except Exception:
                running_for_ms = None
            busy = {
                "guard": "plug_busy",
                "tool": tool_name,
                "key": key,
                "active": {
                    "tool": active.get("tool") or tool_name,
                    "source": active.get("source"),
                    "client_id": active.get("client_id"),
                    "started_ms": started_ms,
                    "running_for_ms": running_for_ms,
                    "model_id": active.get("model_id"),
                    "slot_name": active.get("slot_name"),
                },
                "error": f"Model load already in progress for {active.get('model_id') or 'requested model'}. Wait for completion before retrying {tool_name}.",
            }
            return None, busy
        _plug_exec_active[key] = {
            "tool": tool_name,
            "source": source,
            "client_id": client_id,
            "started_ms": now_ms,
            "model_id": str((args or {}).get("model_id", "") or ""),
            "slot_name": str((args or {}).get("slot_name", "") or ""),
        }
        return {"key": key}, None


async def _release_plug_execution(claim: dict | None) -> None:
    if not isinstance(claim, dict):
        return
    key = str(claim.get("key", "") or "").strip()
    if not key:
        return
    async with _plug_exec_gate:
        _plug_exec_active.pop(key, None)


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


def _coerce_int(value, default: int = 0) -> int:
    fallback = int(default)
    if value is None:
        return fallback
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return fallback
        try:
            return int(raw)
        except (TypeError, ValueError):
            try:
                return int(float(raw))
            except (TypeError, ValueError, OverflowError):
                return fallback
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback


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


_activity_event_seq = 0
_activity_log_lock = threading.Lock()


def _json_safe_snapshot(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        try:
            return {"_snapshot_error": True, "preview": _activity_preview(value, 320)}
        except Exception:
            return {"_snapshot_error": True, "preview": str(value)}


def _broadcast_activity(tool: str, args: dict, result: dict | None, duration_ms: int, error: str | None, source: str = "external", client_id: str | None = None):
    """Record and broadcast a tool call to all SSE activity subscribers."""
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
    global _activity_event_seq
    _activity_event_seq += 1
    hidden_from_activity = source == "hydration"
    entry = {
        "id": f"act-{int(time.time() * 1000)}-{_activity_event_seq}",
        "tool": tool,
        "category": cat,
        "args": _json_safe_snapshot(args or {}),
        "result": _json_safe_snapshot(parsed_result),
        "error": error,
        "durationMs": duration_ms,
        "timestamp": int(time.time() * 1000),
        "source": source,
        "clientId": client_id,  # granular client identification
        "hiddenFromActivity": hidden_from_activity,
    }
    with _activity_log_lock:
        _activity_log.append(entry)
        if len(_activity_log) > 500:
            _activity_log.pop(0)
    if _DEBUG_FEED_MIRROR_ENABLED and tool not in _DEBUG_FEED_MIRROR_EXCLUDED_TOOLS:
        try:
            asyncio.get_running_loop().create_task(_mirror_activity_to_observe(entry))
        except Exception:
            pass
    if hidden_from_activity:
        return
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


def _activity_mirror_value(value, max_chars: int = 6000):
    try:
        if isinstance(value, str):
            encoded = value
        else:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        encoded = str(value)
    if len(encoded) <= max_chars:
        return value
    payload = {
        "_truncated": True,
        "chars": len(encoded),
        "preview": _activity_preview(value, min(640, max_chars)),
    }
    if isinstance(value, dict) and value.get("_cached"):
        payload["_cached"] = value.get("_cached")
    return payload


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
            "activity_id": str((entry or {}).get("id") or ""),
            "hidden_from_activity": bool((entry or {}).get("hiddenFromActivity")),
            "duration_ms": _coerce_int((entry or {}).get("durationMs"), 0),
            "error": (entry or {}).get("error"),
            "args": _activity_mirror_value((entry or {}).get("args") or {}, 5000),
            "result": _activity_mirror_value((entry or {}).get("result"), 14000),
            "args_preview": _activity_preview((entry or {}).get("args") or {}, 220),
            "result_preview": _activity_preview((entry or {}).get("result"), _DEBUG_FEED_MIRROR_MAX_CHARS),
            "timestamp_ms": _coerce_int((entry or {}).get("timestamp"), int(time.time() * 1000)),
        }
        await _call_tool("observe", {"signal_type": "agent_debug", "data": json.dumps(payload, ensure_ascii=False)})
        # Also inject a debug-shaped activity entry into the SSE stream
        # so the frontend Debug tab can see it (the _call_tool above only
        # writes to the capsule observation store, not the SSE broadcast).
        global _activity_event_seq
        _activity_event_seq += 1
        debug_entry = {
            "id": f"dbg-{int(time.time() * 1000)}-{_activity_event_seq}",
            "tool": tool,
            "category": "debug",
            "args": {"signal_type": "agent_debug", "detail": f"DEBUG {tool}", "mirror": payload},
            "result": _json_safe_snapshot(entry.get("result")),
            "error": entry.get("error"),
            "durationMs": _coerce_int(entry.get("durationMs"), 0),
            "timestamp": int(time.time() * 1000),
            "source": "agent-debug",
            "clientId": str((entry or {}).get("clientId") or ""),
            "hiddenFromActivity": True,
        }
        with _activity_log_lock:
            _activity_log.append(debug_entry)
            if len(_activity_log) > 500:
                _activity_log.pop(0)
        for q in list(_activity_subscribers):
            try:
                q.put_nowait(debug_entry)
            except Exception:
                pass
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
WEB_HOST = (os.environ.get("WEB_HOST", "0.0.0.0") or "0.0.0.0").strip() or "0.0.0.0"
WEB_PORT = int(os.environ.get("WEB_PORT", "7860"))
CAPSULE_PATH = Path("capsule/champion_gen8.py")
MCP_BASE = f"http://127.0.0.1:{MCP_PORT}"
_MCP_TOOL_TIMEOUT_SECONDS = max(8, int(os.environ.get("MCP_TOOL_TIMEOUT_SECONDS", "600")))
_MCP_SESSION_READ_TIMEOUT_SECONDS = max(
    _MCP_TOOL_TIMEOUT_SECONDS + 60,
    int(os.environ.get("MCP_SESSION_READ_TIMEOUT_SECONDS", str(_MCP_TOOL_TIMEOUT_SECONDS + 60))),
)
_HF_ROUTER_REQUEST_TIMEOUT_SECONDS = max(
    30.0,
    float(os.environ.get("HF_ROUTER_REQUEST_TIMEOUT_SECONDS", str(_MCP_TOOL_TIMEOUT_SECONDS))),
)
HF_ROUTER_BASE = os.environ.get("HF_ROUTER_BASE", "https://router.huggingface.co").rstrip("/")
_PI_ROUTER_REQUEST_TIMEOUT_SECONDS = max(
    30.0,
    float(os.environ.get("PI_ROUTER_REQUEST_TIMEOUT_SECONDS", str(_MCP_TOOL_TIMEOUT_SECONDS))),
)
_PI_ROUTER_MAX_PROMPT_CHARS = max(
    4096,
    int(os.environ.get("PI_ROUTER_MAX_PROMPT_CHARS", "64000")),
)
_PI_ROUTER_SYSTEM_PROMPT_MAX_CHARS = max(
    1024,
    int(os.environ.get("PI_ROUTER_SYSTEM_PROMPT_MAX_CHARS", "12000")),
)
_PI_ROUTER_ALLOWED_PROVIDERS = frozenset({
    "anthropic",
    "cerebras",
    "github-copilot",
    "google-antigravity",
    "groq",
    "openai-codex",
    "openrouter",
})
_PI_ROUTER_PROVIDER_ALIASES = {
    "claude": "anthropic",
    "codex": "openai-codex",
    "copilot": "github-copilot",
    "gemini": "google-antigravity",
    "google": "google-antigravity",
}
APP_MODE = str(os.environ.get("APP_MODE", "development") or "development").strip().lower()
if APP_MODE not in ("development", "product"):
    APP_MODE = "development"
MCP_EXTERNAL_POLICY = str(
    os.environ.get("MCP_EXTERNAL_POLICY", "closed" if APP_MODE == "product" else "full")
    or ("closed" if APP_MODE == "product" else "full")
).strip().lower()
if MCP_EXTERNAL_POLICY not in ("full", "guided", "closed"):
    MCP_EXTERNAL_POLICY = "closed" if APP_MODE == "product" else "full"

_PRODUCT_BUNDLE_PROFILES = {
    "environment_product": {
        "label": "Environment Product",
        "description": "Package the environment theater as the primary product surface with its backing seed state.",
        "default_app_mode": "product",
        "default_mcp_external_policy": "closed",
        "include_runtime_shell": True,
        "include_live_mirror": True,
        "include_visual_evidence": True,
        "include_activity_log": False,
        "include_workflow_history": False,
    },
    "interface_product": {
        "label": "Interface Product",
        "description": "Package the interface/panel shell with packaged state and environment surfaces for product delivery.",
        "default_app_mode": "product",
        "default_mcp_external_policy": "closed",
        "include_runtime_shell": True,
        "include_live_mirror": True,
        "include_visual_evidence": False,
        "include_activity_log": False,
        "include_workflow_history": False,
    },
    "agent_api_service": {
        "label": "Agent API Service",
        "description": "Package the council, workflows, and service state for an agent/API-oriented runtime.",
        "default_app_mode": "development",
        "default_mcp_external_policy": "guided",
        "include_runtime_shell": True,
        "include_live_mirror": False,
        "include_visual_evidence": False,
        "include_activity_log": False,
        "include_workflow_history": True,
    },
    "research_capsule": {
        "label": "Research Capsule",
        "description": "Package the runtime with extra live evidence and recent provenance surfaces for reconstruction.",
        "default_app_mode": "development",
        "default_mcp_external_policy": "full",
        "include_runtime_shell": True,
        "include_live_mirror": True,
        "include_visual_evidence": True,
        "include_activity_log": True,
        "include_workflow_history": True,
    },
}

_PRODUCT_BUNDLE_RUNTIME_COPY_SOURCES = (
    "server.py",
    "persistence.py",
    "run_local.ps1",
    "README.md",
    "requirements.txt",
    "package.json",
    "Dockerfile",
    "static",
    "scripts",
    "capsule/capsule.gz",
)

_GUIDED_EXTERNAL_MCP_TOOLS = frozenset({
    "env_help",
    "env_read",
    "env_report",
    "env_control",
    "workflow_execute",
    "workflow_status",
    "workflow_history",
    "get_status",
    "heartbeat",
    "get_cached",
})

_ENV_CONTROL_PROXY_COMMANDS = frozenset({
    "activate_profile",
    "branch_snapshot",
    "camera_dolly_in",
    "camera_dolly_out",
    "camera_frame_focus",
    "camera_frame_overview",
    "camera_frame_replay",
    "camera_orbit_left",
    "camera_orbit_right",
    "sample_now",
    "capture_frame",
    "capture_frame_overview",
    "capture_strip",
    "capture_time_strip",
    "capture_supercam",
    "capture_focus",
    "capture_probe",
    "scan_docs",
    "set_theater_mode",
    "set_camera_mode",
    "set_replay_mode",
    "toggle_stream",
    "toggle_replay",
    "replay_prev",
    "replay_next",
    "focus_actor",
    "focus_artifact",
    "focus_branch",
    "focus_dispatch",
    "focus_district",
    "focus_doc",
    "focus_event",
    "focus_execution",
    "focus_node",
    "focus_profile",
    "focus_queued",
    "focus_recipe",
    "focus_replay",
    "focus_sample",
    "focus_slot",
    "focus_trace",
    "focus_watch",
    "focus_workflow",
    "follow_failed",
    "focus_surface",
    "inspect_surface",
    "open_surface",
    "open_doc_memory",
    "close_surface",
    "camera_reset_pose",
    "camera_tilt_down",
    "camera_tilt_up",
    "surface_tab",
    "surface_scroll",
    "surface_action",
    "surface_click",
    "surface_input",
    "surface_submit",
    "close_inspector",
    "camera_pan_left",
    "camera_pan_right",
    "camera_pan_up",
    "camera_pan_down",
    "camera_pan_forward",
    "camera_pan_back",
    "camera_pose",
    "run_recipe",
    "spawn_inhabitant",
    "despawn_inhabitant",
    "focus_inhabitant",
    "character_mount",
    "character_unmount",
    "character_focus",
    "character_move_to",
    "character_stop",
    "character_look_at",
    "character_set_model",
    "workbench_new_builder",
    "workbench_get_blueprint",
    "workbench_get_part_surface",
    "workbench_frame_part",
    "workbench_select_bone",
    "workbench_select_bones",
    "workbench_select_chain",
    "workbench_select_controller",
    "workbench_set_editing_mode",
    "workbench_set_display_scope",
    "workbench_set_gizmo_mode",
    "workbench_set_gizmo_space",
    "workbench_set_bone",
    "workbench_set_pose",
    "workbench_set_pose_batch",
    "workbench_clear_pose",
    "workbench_capture_pose",
    "workbench_delete_pose",
    "workbench_apply_pose",
    "workbench_apply_pose_macro",
    "workbench_set_timeline_cursor",
    "workbench_compile_clip",
    "workbench_play_authored_clip",
    "workbench_assert_balance",
    "workbench_reset_angles",
    "workbench_isolate_chain",
    "workbench_save_blueprint",
    "workbench_load_blueprint",
    "character_play_clip",
    "character_queue_clips",
    "character_stop_clip",
    "character_set_loop",
    "character_set_speed",
    "character_get_animation_state",
    "character_play_reaction",
    "workbench_set_scaffold",
    "workbench_set_load_field",
    "workbench_stage_contact",
    "text_theater_set_view",
    "toggle_inhabitant_fov_debug",
    "set_world_profile",
    "apply_profile_kit",
    "clear_profile_kit",
    "set_camera_preset",
})


def _external_mcp_blocked() -> bool:
    return MCP_EXTERNAL_POLICY == "closed"


def _external_mcp_allowed_tools() -> set[str] | None:
    if MCP_EXTERNAL_POLICY == "full":
        return None
    if MCP_EXTERNAL_POLICY == "guided":
        return set(_GUIDED_EXTERNAL_MCP_TOOLS)
    return set()


def _external_mcp_policy_note() -> str:
    if MCP_EXTERNAL_POLICY == "guided":
        tools = ", ".join(sorted(_GUIDED_EXTERNAL_MCP_TOOLS))
        return f" External MCP policy: guided. Allowed tools: {tools}."
    if MCP_EXTERNAL_POLICY == "closed":
        return " External MCP policy: closed."
    return ""


def _external_mcp_local_bridge_note() -> str:
    return (
        " Proxy bridge note: this server exposes local proxy tools beyond the capsule-generated "
        "help surfaces. Do not conclude a tool is absent from capsule get_help(...) alone; use "
        "tools/list as the availability authority. Important proxy-local tools include "
        "continuity_status, continuity_restore, env_help, env_report, agent_delegate, "
        "agent_chat_inject, agent_chat_sessions, agent_chat_result, agent_chat_purge, "
        "hf_cache_status, hf_cache_clear, capsule_restart, persist_status, "
        "persist_restore_revision, product_bundle_profiles, and product_bundle_export. "
        "For continuity after compaction, call continuity_restore(summary=<objective + subject + "
        "pivot>, cwd=<repo>) and treat it as archive-side reacclimation only; fresh live "
        "theater/blackboard corroboration still decides current truth. For environment/browser/"
        "runtime work, treat get_help('environment') as the umbrella capsule view and "
        "env_help(topic='env_help') plus env_help(topic='index') as the richer local registry. "
        "Use env_report(...) for scoped diagnosis once fresh text-theater and snapshot reads exist."
    )


def _filter_external_mcp_tools_list(tools_list: list[dict]) -> list[dict]:
    allowed = _external_mcp_allowed_tools()
    if allowed is None:
        return tools_list
    return [tool for tool in tools_list if str((tool or {}).get("name") or "") in allowed]


def _external_mcp_policy_violation(method: str, params: dict | None) -> dict | None:
    if MCP_EXTERNAL_POLICY == "full":
        return None

    m = str(method or "").strip()
    p = params if isinstance(params, dict) else {}

    if m == "initialize" or m.startswith("notifications/") or m == "tools/list":
        return None

    if m == "tools/call":
        tool_name = str(p.get("name") or "").strip()
        allowed = _external_mcp_allowed_tools() or set()
        if tool_name and tool_name in allowed:
            return None
        return {
            "code": -32004,
            "message": f"Tool '{tool_name or 'unknown'}' is not available under external MCP policy '{MCP_EXTERNAL_POLICY}'",
            "data": {
                "app_mode": APP_MODE,
                "mcp_external_policy": MCP_EXTERNAL_POLICY,
                "allowed_tools": sorted(list(allowed)),
                "requested_tool": tool_name,
            },
        }

    return {
        "code": -32005,
        "message": f"Method '{m or 'unknown'}' is not available under external MCP policy '{MCP_EXTERNAL_POLICY}'",
        "data": {
            "app_mode": APP_MODE,
            "mcp_external_policy": MCP_EXTERNAL_POLICY,
        },
    }


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
_external_mcp_sse_subscribers: dict[str, list[asyncio.Queue]] = {}


def _register_external_mcp_sse_subscriber(session_id: str, queue: asyncio.Queue):
    sid = str(session_id or "").strip()
    if not sid:
        return
    queues = _external_mcp_sse_subscribers.setdefault(sid, [])
    if queue not in queues:
        queues.append(queue)


def _unregister_external_mcp_sse_subscriber(session_id: str, queue: asyncio.Queue):
    sid = str(session_id or "").strip()
    if not sid:
        return
    queues = _external_mcp_sse_subscribers.get(sid)
    if not queues:
        return
    try:
        queues.remove(queue)
    except ValueError:
        pass
    if not queues:
        _external_mcp_sse_subscribers.pop(sid, None)


def _push_external_mcp_sse_response(session_id: str, payload: dict) -> bool:
    sid = str(session_id or "").strip()
    if not sid or not isinstance(payload, dict):
        return False
    queues = list(_external_mcp_sse_subscribers.get(sid) or [])
    if not queues:
        return False
    chunk = "event: message\ndata: " + json.dumps(payload) + "\n\n"
    delivered = False
    dead = []
    for queue in queues:
        try:
            queue.put_nowait(chunk)
            delivered = True
        except Exception:
            dead.append(queue)
    for queue in dead:
        _unregister_external_mcp_sse_subscriber(sid, queue)
    return delivered

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
            _session_cm = ClientSession(
                _read_stream,
                _write_stream,
                read_timeout_seconds=timedelta(seconds=_MCP_SESSION_READ_TIMEOUT_SECONDS),
            )
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

                ppack = pack_storage.status() if hasattr(pack_storage, "status") else {"available": False}
                print(
                    f"[INIT] Pack storage (hf={ppack.get('hf_enabled')}, local_index={ppack.get('local_index_exists')}, "
                    f"cache_index={ppack.get('cache_index_exists')}, repo={ppack.get('repo_id')})..."
                )
                if hasattr(pack_storage, "bootstrap_runtime_packs"):
                    try:
                        ppack = await pack_storage.bootstrap_runtime_packs()
                        print(
                            f"[OK] Pack bootstrap complete (cache_index={ppack.get('cache_index_exists')}, "
                            f"cache_manifests={ppack.get('cache_manifest_count')}, last_sync_ok={ppack.get('last_sync_ok')})"
                        )
                    except Exception as exc:
                        print(f"[WARN] Pack bootstrap failed: {exc}")

            else:
                print("[WARN] MCP connect failed (will retry on first request)")

    global _dreamer_sampler_task
    if _dreamer_sampler_task is None or _dreamer_sampler_task.done():
        _dreamer_sampler_task = asyncio.create_task(_dreamer_sampler_loop())

    yield

    # Shutdown — save state before stopping
    if _dreamer_sampler_task is not None:
        _dreamer_sampler_task.cancel()
        try:
            await _dreamer_sampler_task
        except asyncio.CancelledError:
            pass
        _dreamer_sampler_task = None

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
        "env_control", "env_read", "env_help", "env_report",
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


def _pi_router_normalize_provider(provider: str | None) -> str | None:
    raw = str(provider or "").strip().lower()
    if not raw:
        return None
    normalized = _PI_ROUTER_PROVIDER_ALIASES.get(raw, raw)
    return normalized if normalized in _PI_ROUTER_ALLOWED_PROVIDERS else None


def _pi_router_cli_prefix() -> list[str] | None:
    candidates: list[str] = []
    explicit = str(os.environ.get("PI_CLI_PATH", "") or "").strip()
    if explicit:
        candidates.append(explicit)
    if os.name == "nt":
        for name in ("pi.cmd", "pi", "pi.ps1"):
            hit = shutil.which(name)
            if hit:
                candidates.append(hit)
    else:
        for name in ("pi", "pi.cmd", "pi.ps1"):
            hit = shutil.which(name)
            if hit:
                candidates.append(hit)

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        suffix = Path(candidate).suffix.lower()
        if suffix == ".ps1":
            pwsh = shutil.which("pwsh") or shutil.which("powershell")
            if pwsh:
                return [pwsh, "-File", candidate]
            continue
        return [candidate]
    return None


def _pi_router_strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", str(text or ""))


def _pi_router_trim_text(text: str, max_chars: int, keep_tail: bool = False) -> str:
    value = str(text or "")
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    marker = "\n\n[Earlier content truncated]\n\n"
    room = max(0, max_chars - len(marker))
    if room <= 0:
        return value[-max_chars:] if keep_tail else value[:max_chars]
    return marker + value[-room:] if keep_tail else value[:room] + marker


def _pi_router_content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type in ("text", "input_text"):
                text = str(item.get("text") or item.get("input_text") or "").strip()
                if text:
                    parts.append(text)
            elif item_type in ("image_url", "input_image", "image"):
                parts.append("[image input omitted for Pi bridge]")
            elif item_type == "input_audio":
                fmt = ""
                payload = item.get("input_audio")
                if isinstance(payload, dict):
                    fmt = str(payload.get("format") or "").strip().lower()
                parts.append(
                    "[audio input omitted for Pi bridge"
                    + (f": {fmt}" if fmt else "")
                    + "]"
                )
            elif "text" in item:
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    return str(content).strip()


def _pi_router_build_prompt(messages, fallback_prompt: str = "", max_tokens=None) -> tuple[str, str]:
    convo_parts: list[str] = []
    system_parts: list[str] = []

    for msg in messages if isinstance(messages, list) else []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user").strip().lower() or "user"
        text = _pi_router_content_to_text(msg.get("content"))
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        if not text:
            continue
        convo_parts.append(f"{role.upper()}:\n{text}")

    fallback_text = str(fallback_prompt or "").strip()
    if not convo_parts and fallback_text:
        convo_parts.append(f"USER:\n{fallback_text}")
    if not convo_parts:
        convo_parts.append("USER:\n")

    convo_text = _pi_router_trim_text(
        "\n\n".join(convo_parts).strip(),
        _PI_ROUTER_MAX_PROMPT_CHARS,
        keep_tail=True,
    )

    base_instruction = (
        "You are operating inside Champion Council as a remote council slot. "
        "Continue the conversation faithfully and return only the assistant's next reply."
    )
    try:
        if max_tokens is not None:
            max_token_int = max(1, int(max_tokens))
            base_instruction += f" Keep the reply under approximately {max_token_int} tokens."
    except Exception:
        pass

    system_prompt = "\n\n".join(part for part in system_parts if part).strip()
    if system_prompt:
        system_prompt = system_prompt + "\n\n" + base_instruction
    else:
        system_prompt = base_instruction
    system_prompt = _pi_router_trim_text(
        system_prompt,
        _PI_ROUTER_SYSTEM_PROMPT_MAX_CHARS,
        keep_tail=False,
    )
    prompt = f"Conversation so far:\n\n{convo_text}\n\nASSISTANT:"
    return system_prompt, prompt


def _pi_router_run_completion_sync(
    provider: str,
    model: str,
    system_prompt: str,
    prompt: str,
    thinking: str | None = None,
) -> dict:
    prefix = _pi_router_cli_prefix()
    if not prefix:
        raise RuntimeError("Pi CLI not found on PATH. Set PI_CLI_PATH or install pi locally.")

    cmd = list(prefix) + [
        "--provider", provider,
        "--model", model,
        "--print",
        "--no-session",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
    ]
    thinking_value = str(thinking or "").strip().lower()
    if thinking_value in {"off", "minimal", "low", "medium", "high", "xhigh"}:
        cmd += ["--thinking", thinking_value]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    cmd.append(prompt)

    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_PI_ROUTER_REQUEST_TIMEOUT_SECONDS,
        env=env,
    )
    stdout = _pi_router_strip_ansi(proc.stdout or "").strip()
    stderr = _pi_router_strip_ansi(proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(stderr or stdout or f"Pi CLI exited with status {proc.returncode}")
    if not stdout:
        raise RuntimeError("Pi CLI returned empty output")
    return {"text": stdout, "stderr": stderr}


async def _pi_router_run_completion(
    provider: str,
    model: str,
    system_prompt: str,
    prompt: str,
    thinking: str | None = None,
) -> dict:
    return await asyncio.to_thread(
        _pi_router_run_completion_sync,
        provider,
        model,
        system_prompt,
        prompt,
        thinking,
    )


def _pi_router_feature_not_supported(provider: str, feature: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": f"Pi router does not expose {feature} for provider '{provider}'",
            "hint": "Use a dedicated embedding/audio slot or a direct OpenAI-compatible endpoint for that capability.",
        },
    )


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

    if tool_name in ("env_spawn", "env_mutate"):
        params_raw = patched.get("params")
        if params_raw is None:
            params_raw = {
                key: value
                for key, value in patched.items()
                if key not in ("__source",)
            }
            if params_raw:
                patched = {"params": params_raw}
        if isinstance(params_raw, (dict, list)):
            try:
                patched["params"] = json.dumps(params_raw)
            except Exception:
                patched["params"] = str(params_raw)

    if tool_name == "env_persist":
        params_raw = patched.get("params")
        if params_raw is None:
            lifted = {}
            for key in ("payload", "include_empty", "empty_only", "names"):
                if key in patched:
                    lifted[key] = patched.pop(key)
            if lifted:
                params_raw = lifted
        if isinstance(params_raw, (dict, list)):
            try:
                patched["params"] = json.dumps(params_raw)
            except Exception:
                patched["params"] = str(params_raw)

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
    },
    "continuity_status": {
        "description": "Inspect local Codex session archives that can be used for continuity restore after context compaction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of recent sessions to return"},
                "codex_home": {"type": "string", "description": "Optional explicit .codex home override"}
            }
        }
    },
    "continuity_restore": {
        "description": "Restore operational continuity from local Codex session archives using a summary or cwd hint as the lookup key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Compaction summary or semantic recall prompt"},
                "cwd": {"type": "string", "description": "Optional cwd hint to bias matching toward the right worktree"},
                "limit": {"type": "integer", "description": "Maximum number of matched sessions to surface"},
                "since_days": {"type": "integer", "description": "Only search sessions newer than this many days"},
                "session_path": {"type": "string", "description": "Optional exact rollout JSONL path to restore from"},
                "codex_home": {"type": "string", "description": "Optional explicit .codex home override"}
            }
        }
    },
    "product_bundle_profiles": {
        "description": "List canonical product bundle export profiles for the current shell runtime.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "product_bundle_export": {
        "description": "Export a product bundle using the current persistence snapshot, environment state, and optional runtime shell copy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string", "description": "Bundle profile: environment_product|interface_product|agent_api_service|research_capsule"},
                "bundle_name": {"type": "string", "description": "Optional friendly name used in the bundle directory and manifest"},
                "include_runtime_shell": {"type": "boolean", "description": "Override whether the current shell/runtime files are copied into the bundle"},
                "app_mode": {"type": "string", "description": "Optional launch default override: development|product"},
                "mcp_external_policy": {"type": "string", "description": "Optional launch default override: full|guided|closed"},
                "include_activity_log": {"type": "boolean", "description": "Include the recent in-memory activity log even if the selected profile normally omits it"},
                "include_workflow_history": {"type": "boolean", "description": "Include recent workflow execution history even if the selected profile normally omits it"},
                "workflow_history_limit": {"type": "integer", "description": "Maximum workflow history rows to capture when included"}
            }
        }
    },
    "env_report": {
        "description": "Build a scoped, theater-first diagnostic report over live environment state using a registered report recipe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_id": {"type": "string", "description": "Stable report recipe id, e.g. route_stability_diagnosis"},
                "raw_slice": {"type": "boolean", "description": "Opt in to a scoped raw evidence slice when the recipe allows it"},
                "target": {
                    "type": "object",
                    "description": "Optional focus target with kind/id",
                    "properties": {
                        "kind": {"type": "string"},
                        "id": {"type": "string"}
                    }
                }
            },
            "required": ["report_id"]
        }
    },
    "env_help": {
        "description": "Query the local environment/browser/runtime help registry. Use this first to learn environment-specific commands, query surfaces, command families, and playbooks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Specific environment topic, command, query, builtin topic, or playbook alias"},
                "category": {"type": "string", "description": "Environment help family/category such as builder_motion"},
                "search": {"type": "string", "description": "Free-text search over environment commands, queries, families, playbooks, and builtin topics"}
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


def _proxy_tool_schema_overrides(name: str, schema: dict) -> dict:
    tool_name = str(name or "").strip()
    base = dict(schema) if isinstance(schema, dict) else {}
    if tool_name != "env_read":
        return base
    return {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Read target. Supports standard env_read queries plus text-theater lanes such as "
                    "text_theater_embodiment, text_theater_snapshot, text_theater_view, "
                    "text_theater_blackboard, and text_theater_query_work."
                ),
            },
            "view": {
                "type": "string",
                "description": "Optional text theater view mode for text_theater_view queries, e.g. consult, render, or split.",
            },
            "section": {
                "type": "string",
                "description": "Optional text theater section for text_theater_view queries, e.g. theater, blackboard, embodiment, or snapshot.",
            },
            "width": {
                "type": "integer",
                "description": "Optional render width for text_theater_view queries.",
            },
            "height": {
                "type": "integer",
                "description": "Optional render height for text_theater_view queries.",
            },
            "timeout": {
                "type": "number",
                "description": "Optional render timeout in seconds for text_theater_view queries.",
            },
            "diagnostics": {
                "type": "boolean",
                "description": "Enable diagnostics for text_theater_view queries.",
            },
        },
        "required": ["query"],
    }


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
        fixed["inputSchema"] = _schema_sanitize(_proxy_tool_schema_overrides(name, fixed.get("inputSchema", {})))
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


def _coerce_flag(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def _product_bundle_slug(value: str) -> str:
    out = []
    last_dash = False
    for ch in str(value or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
            last_dash = False
            continue
        if not last_dash:
            out.append("-")
            last_dash = True
    slug = "".join(out).strip("-")
    return slug or "bundle"


def _product_bundle_rel(path: Path, bundle_root: Path) -> str:
    return path.relative_to(bundle_root).as_posix()


def _product_bundle_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def _product_bundle_resolve_cached_payload(payload):
    current = payload
    for _ in range(4):
        if not isinstance(current, dict):
            return current
        cache_id = str(current.get("_cached", "") or "").strip()
        if not cache_id:
            return current
        cached_raw = await _call_tool("get_cached", {"cache_id": cache_id})
        parsed = _parse_mcp_result((cached_raw or {}).get("result") if isinstance(cached_raw, dict) else None)
        if parsed is None:
            return current
        current = parsed
    return current


def _product_bundle_profiles_payload() -> dict:
    profiles = []
    for name, spec in _PRODUCT_BUNDLE_PROFILES.items():
        row = dict(spec)
        row["name"] = name
        profiles.append(row)
    return {
        "profiles": profiles,
        "count": len(profiles),
        "notes": {
            "canonical_state": ["seed_state", "environment/shared_state", "environment/contracts", "environment/habitat_objects"],
            "auxiliary_state": ["environment/live", "environment/render_truth", "environment/layout_snapshot", "environment/activity_log", "environment/workflow_history"],
            "secrets_policy": "Provider tokens and API keys are not exported. Reconfigure them in the target environment.",
            "capsule_policy": "The protected capsule is exported only as capsule/capsule.gz when the runtime shell is copied.",
        },
    }


def _product_bundle_copy_path(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(
            src,
            dest,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


async def _product_bundle_collect_seed_state(bundle_root: Path) -> dict:
    seed_dir = bundle_root / "seed_state"
    seed_dir.mkdir(parents=True, exist_ok=True)
    copied_files: list[str] = []
    warnings: list[str] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="cc_bundle_seed_"))
    try:
        state_files = await persistence._collect_state_files(_call_tool, tmpdir)
        if not isinstance(state_files, dict) or not state_files:
            warnings.append("No state files were captured from the current runtime snapshot.")
            return {
                "path": _product_bundle_rel(seed_dir, bundle_root),
                "files": copied_files,
                "count": 0,
                "warnings": warnings,
            }
        for name, src in state_files.items():
            src_path = src if isinstance(src, Path) else Path(str(src))
            if not src_path.exists():
                warnings.append(f"State file missing after snapshot: {name}")
                continue
            rel = persistence.LOCAL_LAYOUT.get(name, Path(name))
            dest = seed_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest)
            copied_files.append(_product_bundle_rel(dest, bundle_root))
        return {
            "path": _product_bundle_rel(seed_dir, bundle_root),
            "files": copied_files,
            "count": len(copied_files),
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def _product_bundle_collect_environment(
    bundle_root: Path,
    profile_spec: dict,
    include_activity_log: bool,
    include_workflow_history: bool,
    workflow_history_limit: int,
) -> dict:
    env_dir = bundle_root / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    warnings: list[str] = []
    captured_queries: list[str] = []

    requests: list[tuple[str, str, dict]] = [
        ("snapshot", "env_read", {"query": "snapshot"}),
        ("scene_objects", "env_read", {"query": "list"}),
        ("snapshot_index", "env_persist", {"operation": "list"}),
    ]

    if profile_spec.get("include_live_mirror"):
        requests.extend([
            ("live", "env_read", {"query": "live"}),
            ("shared_state", "env_read", {"query": "shared_state"}),
            ("contracts", "env_read", {"query": "contracts"}),
            ("habitat_objects", "env_read", {"query": "habitat_objects"}),
        ])

    for label, tool_name, tool_args in requests:
        payload = await persistence._call_capsule_tool(_call_tool, tool_name, tool_args)
        if payload is None:
            warnings.append(f"{tool_name} returned no payload for {label}.")
            continue
        payload = await _product_bundle_resolve_cached_payload(payload)
        out_path = env_dir / f"{label}.json"
        _product_bundle_write_json(out_path, payload)
        files.append(_product_bundle_rel(out_path, bundle_root))
        captured_queries.append(label)
        if label == "live" and isinstance(payload, dict) and profile_spec.get("include_visual_evidence"):
            for child_key in ("render_truth", "layout_snapshot", "corroboration", "recent_bus"):
                if child_key not in payload:
                    continue
                child_path = env_dir / f"{child_key}.json"
                _product_bundle_write_json(child_path, payload.get(child_key))
                files.append(_product_bundle_rel(child_path, bundle_root))

    status_payload = persistence.status() if hasattr(persistence, "status") else {"available": persistence.is_available()}
    status_path = env_dir / "persistence_status.json"
    _product_bundle_write_json(status_path, status_payload)
    files.append(_product_bundle_rel(status_path, bundle_root))

    if include_activity_log:
        activity_payload = {
            "count": len(_activity_log),
            "events": list(_activity_log),
        }
        activity_path = env_dir / "activity_log.json"
        _product_bundle_write_json(activity_path, activity_payload)
        files.append(_product_bundle_rel(activity_path, bundle_root))

    if include_workflow_history:
        rows = await _workflow_proxy_history(workflow_id=None, limit=workflow_history_limit)
        workflow_payload = {
            "count": len(rows),
            "history": rows,
            "executions": rows,
        }
        workflow_path = env_dir / "workflow_history.json"
        _product_bundle_write_json(workflow_path, workflow_payload)
        files.append(_product_bundle_rel(workflow_path, bundle_root))

    return {
        "path": _product_bundle_rel(env_dir, bundle_root),
        "files": files,
        "count": len(files),
        "captured_queries": captured_queries,
        "warnings": warnings,
    }


def _product_bundle_copy_runtime_shell(bundle_root: Path) -> dict:
    runtime_dir = bundle_root / "runtime_shell"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    copied_entries: list[str] = []
    warnings: list[str] = []

    for rel_text in _PRODUCT_BUNDLE_RUNTIME_COPY_SOURCES:
        src = Path(rel_text)
        if not src.exists():
            warnings.append(f"Runtime source missing: {rel_text}")
            continue
        dest = runtime_dir / rel_text
        _product_bundle_copy_path(src, dest)
        copied_entries.append(_product_bundle_rel(dest, bundle_root))

    return {
        "path": _product_bundle_rel(runtime_dir, bundle_root),
        "entries": copied_entries,
        "count": len(copied_entries),
        "warnings": warnings,
    }


def _product_bundle_provider_descriptor(source: str) -> dict:
    src = str(source or "").strip()
    if not src:
        return {"kind": "unknown", "is_remote": False}
    if not _is_remote_model_source(src):
        return {
            "kind": "local_model",
            "is_remote": False,
            "model_id": src,
            "requires_external_secret": False,
        }

    parts = urlsplit(src)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    segments = [seg for seg in (parts.path or "").split("/") if seg]
    kind = "openai_compatible"
    router_provider = None
    if "hf-router" in segments:
        kind = "huggingface_router"
        idx = segments.index("hf-router")
        if idx + 1 < len(segments):
            candidate = segments[idx + 1]
            if candidate and candidate != "v1":
                router_provider = candidate
    elif "pi-router" in segments:
        kind = "pi_router"
        idx = segments.index("pi-router")
        if idx + 1 < len(segments):
            candidate = segments[idx + 1]
            if candidate and candidate != "v1":
                router_provider = candidate

    return {
        "kind": kind,
        "is_remote": True,
        "scheme": parts.scheme,
        "host": parts.hostname,
        "port": parts.port,
        "path": parts.path,
        "query": query,
        "model": query.get("model") or None,
        "router_provider": router_provider,
        "local_loopback": str(parts.hostname or "").strip().lower() in ("127.0.0.1", "localhost"),
        "requires_external_secret": kind == "openai_compatible",
    }


async def _product_bundle_collect_document_history(bundle_root: Path) -> dict:
    ctx_dir = bundle_root / "development_context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    out_path = ctx_dir / "document_history.json"
    warnings: list[str] = []
    payload = await persistence._call_capsule_tool(
        _call_tool,
        "file_list",
        {"path": "docs/", "include_checkpoints": False, "limit": 1000},
    )
    payload = await _product_bundle_resolve_cached_payload(payload)
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    documents = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_path = str(item.get("key") or item.get("path") or "").strip()
        if not doc_path:
            continue
        versions_payload = await persistence._call_capsule_tool(
            _call_tool,
            "file_versions",
            {"path": doc_path, "limit": 250},
        )
        versions_payload = await _product_bundle_resolve_cached_payload(versions_payload)
        if not isinstance(versions_payload, dict):
            versions_payload = {"count": 0, "checkpoints": []}
            warnings.append(f"Could not resolve file_versions for {doc_path}.")
        documents.append({
            "path": doc_path,
            "type": item.get("type"),
            "version": item.get("version"),
            "size": item.get("size"),
            "modified": item.get("modified"),
            "preview": item.get("preview"),
            "history": versions_payload,
        })

    _product_bundle_write_json(out_path, {
        "path_prefix": "docs/",
        "doc_count": len(documents),
        "documents": documents,
    })
    return {
        "path": _product_bundle_rel(out_path, bundle_root),
        "doc_count": len(documents),
        "warnings": warnings,
    }


async def _product_bundle_collect_slot_provider_metadata(bundle_root: Path) -> dict:
    ctx_dir = bundle_root / "development_context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    out_path = ctx_dir / "slot_provider_metadata.json"
    warnings: list[str] = []
    payload = await persistence._call_capsule_tool(_call_tool, "list_slots", {})
    payload = await _product_bundle_resolve_cached_payload(payload)

    all_ids = payload.get("all_ids") if isinstance(payload, dict) else []
    total = payload.get("total") if isinstance(payload, dict) else 0
    if not isinstance(all_ids, list):
        all_ids = []
    try:
        total = int(total or len(all_ids))
    except Exception:
        total = len(all_ids)

    slots = []
    for idx in range(total):
        info_payload = await persistence._call_capsule_tool(_call_tool, "slot_info", {"slot": idx})
        info_payload = await _product_bundle_resolve_cached_payload(info_payload)
        if not isinstance(info_payload, dict):
            warnings.append(f"Could not resolve slot_info for slot {idx}.")
            continue

        slot_name = str(info_payload.get("name") or (all_ids[idx] if idx < len(all_ids) else f"slot_{idx}") or f"slot_{idx}")
        source = str(
            info_payload.get("source")
            or info_payload.get("model_source")
            or info_payload.get("model_id")
            or info_payload.get("model")
            or ""
        ).strip()
        plugged = bool(info_payload.get("plugged")) or bool(source)
        if not plugged:
            continue

        normalized_source = source
        if source:
            normalized_source, _ = _normalize_remote_provider_model_id(source)
        provider = _product_bundle_provider_descriptor(normalized_source or source)
        restore_strategy = "plug_model" if provider.get("is_remote") else "hub_plug"
        slots.append({
            "slot": idx,
            "name": slot_name,
            "plugged": plugged,
            "status": info_payload.get("status"),
            "type": info_payload.get("type"),
            "model_type": info_payload.get("model_type"),
            "source": source or None,
            "normalized_source": normalized_source or None,
            "provider": provider,
            "restore": {
                "strategy": restore_strategy,
                "preferred_slot_index": idx,
                "slot_name": slot_name,
                "model_id": normalized_source or source or None,
            },
            "slot_info": info_payload,
        })

    _product_bundle_write_json(out_path, {
        "slot_count": len(slots),
        "slots": slots,
    })
    return {
        "path": _product_bundle_rel(out_path, bundle_root),
        "slot_count": len(slots),
        "warnings": warnings,
    }


async def _product_bundle_collect_development_context(bundle_root: Path) -> dict:
    doc_history = await _product_bundle_collect_document_history(bundle_root)
    slot_metadata = await _product_bundle_collect_slot_provider_metadata(bundle_root)
    warnings = []
    warnings.extend(doc_history.get("warnings", []))
    warnings.extend(slot_metadata.get("warnings", []))
    return {
        "path": "development_context",
        "document_history": doc_history,
        "slot_provider_metadata": slot_metadata,
        "warnings": warnings,
    }


async def _product_bundle_export(args: dict | None = None) -> dict:
    args = args or {}
    profile_name = str(args.get("profile", "environment_product") or "environment_product").strip().lower()
    profile_spec = _PRODUCT_BUNDLE_PROFILES.get(profile_name)
    if not profile_spec:
        return {
            "error": f"Unknown profile: {profile_name}",
            "available_profiles": sorted(_PRODUCT_BUNDLE_PROFILES.keys()),
        }

    bundle_name = str(args.get("bundle_name", "") or profile_spec.get("label") or profile_name).strip()
    bundle_slug = _product_bundle_slug(bundle_name)
    timestamp_token = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    export_root = Path("exports") / "product-bundles"
    export_root.mkdir(parents=True, exist_ok=True)
    bundle_root = export_root / f"{timestamp_token}-{bundle_slug}"
    suffix = 2
    while bundle_root.exists():
        bundle_root = export_root / f"{timestamp_token}-{bundle_slug}-{suffix}"
        suffix += 1
    bundle_root.mkdir(parents=True, exist_ok=False)

    include_runtime_shell = _coerce_flag(
        args.get("include_runtime_shell"),
        default=bool(profile_spec.get("include_runtime_shell", True)),
    )
    include_activity_log = _coerce_flag(
        args.get("include_activity_log"),
        default=bool(profile_spec.get("include_activity_log", False)),
    )
    include_workflow_history = _coerce_flag(
        args.get("include_workflow_history"),
        default=bool(profile_spec.get("include_workflow_history", False)),
    )
    try:
        workflow_history_limit = int(args.get("workflow_history_limit", 200) or 200)
    except Exception:
        workflow_history_limit = 200
    workflow_history_limit = max(10, min(workflow_history_limit, 5000))

    app_mode = str(args.get("app_mode", "") or profile_spec.get("default_app_mode") or APP_MODE).strip().lower()
    if app_mode not in ("development", "product"):
        app_mode = str(profile_spec.get("default_app_mode") or APP_MODE)

    mcp_external_policy = str(
        args.get("mcp_external_policy", "")
        or profile_spec.get("default_mcp_external_policy")
        or MCP_EXTERNAL_POLICY
    ).strip().lower()
    if mcp_external_policy not in ("full", "guided", "closed"):
        mcp_external_policy = str(profile_spec.get("default_mcp_external_policy") or MCP_EXTERNAL_POLICY)

    seed_state = await _product_bundle_collect_seed_state(bundle_root)
    environment_capture = await _product_bundle_collect_environment(
        bundle_root=bundle_root,
        profile_spec=profile_spec,
        include_activity_log=include_activity_log,
        include_workflow_history=include_workflow_history,
        workflow_history_limit=workflow_history_limit,
    )
    development_context = await _product_bundle_collect_development_context(bundle_root)
    runtime_shell = None
    if include_runtime_shell:
        runtime_shell = _product_bundle_copy_runtime_shell(bundle_root)

    warnings = []
    warnings.extend(seed_state.get("warnings", []))
    warnings.extend(environment_capture.get("warnings", []))
    warnings.extend(development_context.get("warnings", []))
    if isinstance(runtime_shell, dict):
        warnings.extend(runtime_shell.get("warnings", []))

    manifest = {
        "bundle_version": 1,
        "bundle_name": bundle_name,
        "bundle_slug": bundle_slug,
        "profile": {"name": profile_name, **profile_spec},
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "launch_defaults": {
            "app_mode": app_mode,
            "mcp_external_policy": mcp_external_policy,
        },
        "source_runtime": {
            "web_host": WEB_HOST,
            "web_port": WEB_PORT,
            "mcp_port": MCP_PORT,
            "app_mode": APP_MODE,
            "mcp_external_policy": MCP_EXTERNAL_POLICY,
            "persistence": persistence.status() if hasattr(persistence, "status") else {"available": persistence.is_available()},
        },
        "seed_state": seed_state,
        "environment": environment_capture,
        "development_context": development_context,
        "runtime_shell": runtime_shell,
        "policies": {
            "secrets": "Provider tokens and API keys are not exported. Configure them in the target environment.",
            "capsule": "The protected capsule source is not copied directly. Runtime shell copies capsule/capsule.gz only.",
        },
        "warnings": warnings,
    }
    manifest_path = bundle_root / "product_manifest.json"
    _product_bundle_write_json(manifest_path, manifest)

    return {
        "status": "ok",
        "bundle_dir": str(bundle_root.resolve()),
        "bundle_manifest": str(manifest_path.resolve()),
        "profile": profile_name,
        "seed_state_count": int(seed_state.get("count", 0) or 0),
        "environment_file_count": int(environment_capture.get("count", 0) or 0),
        "document_history_count": int((development_context.get("document_history") or {}).get("doc_count", 0) or 0),
        "slot_provider_metadata_count": int((development_context.get("slot_provider_metadata") or {}).get("slot_count", 0) or 0),
        "runtime_shell_count": int((runtime_shell or {}).get("count", 0) or 0),
        "warnings": warnings,
    }


async def _product_bundle_local_tool(tool_name: str, args: dict | None = None) -> dict | None:
    args = args or {}
    if tool_name == "product_bundle_profiles":
        return _product_bundle_profiles_payload()
    if tool_name == "product_bundle_export":
        return await _product_bundle_export(args)
    return None


def _env_control_local_proxy_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    command = str(args.get("command", "") or "").strip()
    if command not in _ENV_CONTROL_PROXY_COMMANDS:
        return None
    target_id = str(args.get("target_id", "") or "").strip()
    actor = str(args.get("actor", "assistant") or "assistant").strip() or "assistant"
    command_sync_token = _env_next_control_sync_token(command)
    payload = {
        "status": "ok",
        "summary": f"Dispatched environment control command {command}",
        "normalized_args": {
            "command": command,
            "target_id": target_id,
            "actor": actor,
            "command_sync_token": command_sync_token,
        },
        "delta": {
            "command": command,
            "target_id": target_id,
            "command_sync_token": command_sync_token,
        },
        "environment_effects": {},
        "operation": "env_control",
        "operation_status": "dispatched",
        "command": command,
        "target_id": target_id,
        "target": target_id,
        "actor": actor,
        "command_sync_token": command_sync_token,
    }
    if command == "set_theater_mode":
        payload["environment_effects"]["theater_mode_action"] = command
    elif command.startswith("camera_"):
        payload["environment_effects"]["camera_action"] = command
    elif command in ("spawn_inhabitant", "despawn_inhabitant", "focus_inhabitant", "character_mount", "character_unmount", "character_focus", "character_move_to", "character_stop", "character_look_at", "character_set_model", "workbench_new_builder", "workbench_get_blueprint", "workbench_get_part_surface", "workbench_frame_part", "workbench_select_bone", "workbench_select_bones", "workbench_select_chain", "workbench_select_controller", "workbench_set_editing_mode", "workbench_set_display_scope", "workbench_set_gizmo_mode", "workbench_set_gizmo_space", "workbench_set_bone", "workbench_set_pose", "workbench_set_pose_batch", "workbench_clear_pose", "workbench_capture_pose", "workbench_delete_pose", "workbench_apply_pose", "workbench_apply_pose_macro", "workbench_set_timeline_cursor", "workbench_compile_clip", "workbench_play_authored_clip", "workbench_assert_balance", "workbench_reset_angles", "workbench_isolate_chain", "workbench_save_blueprint", "workbench_load_blueprint", "character_play_clip", "character_queue_clips", "character_stop_clip", "character_set_loop", "character_set_speed", "character_get_animation_state", "character_play_reaction", "toggle_inhabitant_fov_debug", "workbench_set_load_field", "workbench_stage_contact"):
        payload["environment_effects"]["character_runtime_action"] = command
    elif command == "text_theater_set_view":
        payload["environment_effects"]["text_theater_action"] = command
    elif command == "workbench_set_scaffold":
        payload["environment_effects"]["character_runtime_action"] = command
    elif command in ("focus_surface", "inspect_surface", "open_surface", "close_surface", "surface_tab", "surface_scroll", "surface_action", "surface_click", "surface_input", "surface_submit", "close_inspector"):
        payload["environment_effects"]["surface_action"] = command
    elif command.startswith("capture_"):
        payload["environment_effects"]["capture_action"] = command
    return payload


def _env_bool_arg(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _env_cached_text_theater_snapshot(cached: dict | None) -> dict:
    if not isinstance(cached, dict):
        return {}
    live_state = cached.get("live_state") if isinstance(cached.get("live_state"), dict) else {}
    shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else {}
    text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    return snapshot


def _env_note_text_theater_read(
    query_name: str,
    cached: dict | None,
    snapshot: dict | None = None,
    extra: dict | None = None,
) -> None:
    cached = cached if isinstance(cached, dict) else {}
    snap = snapshot if isinstance(snapshot, dict) else _env_cached_text_theater_snapshot(cached)
    extra = extra if isinstance(extra, dict) else {}
    record = {
        "updated_ms": int(cached.get("updated_ms") or 0),
        "snapshot_timestamp": int((snap or {}).get("snapshot_timestamp") or 0),
        "query": str(query_name or "").strip().lower(),
        "observed_at_ms": int(time.time() * 1000),
    }
    view_mode = str(extra.get("view_mode") or "").strip().lower()
    section_key = str(extra.get("section_key") or "").strip().lower()
    if view_mode:
        record["view_mode"] = view_mode
    if section_key:
        record["section_key"] = section_key
    if "diagnostics" in extra:
        record["diagnostics"] = bool(extra.get("diagnostics"))
    if view_mode == "consult":
        record["consult_updated_ms"] = record["updated_ms"]
        record["consult_snapshot_timestamp"] = record["snapshot_timestamp"]
        record["consult_query"] = record["query"]
        record["consult_observed_at_ms"] = record["observed_at_ms"]
        record["consult_view_mode"] = view_mode
        record["consult_section_key"] = section_key or "theater"
        record["consult_diagnostics"] = bool(extra.get("diagnostics"))
    with _env_text_theater_read_gate_lock:
        _env_text_theater_read_gate.update(record)


def _env_note_visual_corroboration_read(
    query_name: str,
    cached: dict | None,
    capture_entry: dict | None = None,
) -> None:
    cached = cached if isinstance(cached, dict) else {}
    snapshot = _env_cached_text_theater_snapshot(cached)
    entry = capture_entry if isinstance(capture_entry, dict) else {}
    record = {
        "visual_updated_ms": int(cached.get("updated_ms") or 0),
        "visual_snapshot_timestamp": int((snapshot or {}).get("snapshot_timestamp") or 0),
        "visual_query": str(query_name or "").strip().lower(),
        "visual_capture_ts": int(entry.get("ts") or 0),
        "visual_observed_at_ms": int(time.time() * 1000),
    }
    with _env_text_theater_read_gate_lock:
        _env_text_theater_read_gate.update(record)


def _env_shared_state_prereq_payload(query_text: str, cached: dict | None) -> dict | None:
    query_lower = str(query_text or "").strip().lower()
    raw_state_queries = {"shared_state", "live", "contracts", "habitat_objects"}
    if query_lower not in raw_state_queries and query_lower != "env_report":
        return None
    require_query_work = query_lower in raw_state_queries
    require_visual_corroboration = True
    cached = cached if isinstance(cached, dict) else {}
    snapshot = _env_cached_text_theater_snapshot(cached)
    current_updated_ms = int(cached.get("updated_ms") or 0)
    current_snapshot_timestamp = int((snapshot or {}).get("snapshot_timestamp") or 0)
    with _env_text_theater_read_gate_lock:
        gate = dict(_env_text_theater_read_gate)
    last_updated_ms = int(gate.get("updated_ms") or 0)
    last_snapshot_timestamp = int(gate.get("snapshot_timestamp") or 0)
    consult_updated_ms = int(gate.get("consult_updated_ms") or 0)
    consult_snapshot_timestamp = int(gate.get("consult_snapshot_timestamp") or 0)
    visual_updated_ms = int(gate.get("visual_updated_ms") or 0)
    visual_snapshot_timestamp = int(gate.get("visual_snapshot_timestamp") or 0)
    satisfied = False
    if current_updated_ms and last_updated_ms >= current_updated_ms:
        satisfied = True
    elif current_snapshot_timestamp and last_snapshot_timestamp >= current_snapshot_timestamp:
        satisfied = True
    elif not current_updated_ms and not current_snapshot_timestamp and (last_updated_ms or last_snapshot_timestamp):
        satisfied = True
    consult_satisfied = False
    if current_updated_ms and consult_updated_ms >= current_updated_ms:
        consult_satisfied = True
    elif current_snapshot_timestamp and consult_snapshot_timestamp >= current_snapshot_timestamp:
        consult_satisfied = True
    elif not current_updated_ms and not current_snapshot_timestamp and (consult_updated_ms or consult_snapshot_timestamp):
        consult_satisfied = True
    visual_satisfied = False
    if current_updated_ms and visual_updated_ms >= current_updated_ms:
        visual_satisfied = True
    elif current_snapshot_timestamp and visual_snapshot_timestamp >= current_snapshot_timestamp:
        visual_satisfied = True
    elif not current_updated_ms and not current_snapshot_timestamp and (visual_updated_ms or visual_snapshot_timestamp):
        visual_satisfied = True
    if satisfied and (not require_visual_corroboration or visual_satisfied) and (not require_query_work or consult_satisfied):
        return None
    blocked_by = "text_theater_first"
    if satisfied and require_visual_corroboration and not visual_satisfied:
        blocked_by = "visual_corroboration"
    elif satisfied and require_query_work and not consult_satisfied:
        blocked_by = "text_theater_query_work"
    return {
        "tool": "env_read",
        "status": "error",
        "summary": "Visual corroboration required before deeper state"
        if blocked_by == "visual_corroboration"
        else "Text-theater query work required before raw state"
        if blocked_by == "text_theater_query_work"
        else "Text-theater read required before shared_state",
        "normalized_args": {"query": query_text},
        "delta": {
            "found": False,
            "blocked_by": blocked_by,
            "updated_ms": current_updated_ms,
            "snapshot_timestamp": current_snapshot_timestamp,
            "visual_updated_ms": visual_updated_ms,
            "visual_snapshot_timestamp": visual_snapshot_timestamp,
            "consult_updated_ms": consult_updated_ms,
            "consult_snapshot_timestamp": consult_snapshot_timestamp,
        },
        "operation": "env_read",
        "operation_status": "error",
        "query": query_text,
        "error": "visual_corroboration_required"
        if blocked_by == "visual_corroboration"
        else "text_theater_query_work_required" if blocked_by == "text_theater_query_work" else "text_theater_first_required",
        "message": (
            "Read a fresh text-theater frame, then bring in browser-visible corroboration for the same live frame before widening. "
            "Use text_theater_view(render) or text_theater_embodiment first, then capture_supercam and env_read(query='supercam') "
            "(and capture_probe/env_read(query='probe') when the local subject matters), then consult/blackboard, then snapshot, "
            "then env_report or contracts, and raw shared_state last."
            if blocked_by == "visual_corroboration"
            else
            "Read a fresh consult/query-work view for the current live frame before opening raw state. "
            "Use text_theater_view(render) or text_theater_embodiment first, then browser-visible corroboration, "
            "consult/blackboard after that, snapshot next, env_report for scoped diagnosis after that, and raw shared_state last."
            if blocked_by == "text_theater_query_work"
            else
            "Read a fresh text theater render for the current live frame before opening raw state. "
            "Use text_theater_view(render) or text_theater_embodiment first, then browser-visible corroboration, "
            "consult/blackboard after that, snapshot next, env_report for scoped diagnosis after that, and raw shared_state last."
        ),
        "required_sequence": [
            "env_read(query='text_theater_view', view='render', diagnostics=true) or env_read(query='text_theater_embodiment')",
            "env_control(command='capture_supercam')",
            "env_read(query='supercam')",
            "env_control(command='capture_probe', target_id='character_runtime::mounted_primary') when local/body detail matters",
            "env_read(query='probe') when a fresh probe capture was requested",
            "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
            "env_read(query='text_theater_snapshot')",
            "env_report(report_id='route_stability_diagnosis') when you need route/support reasoning",
            f"env_read(query='{query_lower}')",
        ],
        "last_text_theater_read": gate,
    }


_ENV_REPORT_DEFAULT_SIZE_BYTES = 8 * 1024
_ENV_REPORT_HARD_CAP_BYTES = 24 * 1024
_ENV_REPORT_IDS = ("route_stability_diagnosis", "paired_state_alignment")


def _env_help_builtin_topics() -> dict[str, dict]:
    return {
        "env_help": {
            "tool": "env_help",
            "entry_kind": "env_tool",
            "title": "Environment Help Registry",
            "category": "observation_query",
            "status": "live",
            "transport": {
                "local_proxy": True,
                "browser_surface": False,
                "ui_local_only": False,
                "implemented_verb": True,
            },
            "target_contract": {
                "shape": "json",
                "description": "JSON payload with topic/category/search fields. Use topic='env_help' or topic='index' for cold-start guidance.",
                "examples": [
                    "{}",
                    "{\"topic\":\"env_help\"}",
                    "{\"topic\":\"index\"}",
                    "{\"topic\":\"env_report\"}",
                    "{\"category\":\"builder_motion\"}",
                    "{\"search\":\"mounted asset floor\"}",
                ],
            },
            "summary": "Query the local environment/browser/runtime help registry. This is the richer server-side environment guide that cold agents should use to learn commands, query surfaces, categories, and playbooks.",
            "when_to_use": [
                "Use this first when you are cold to the server and need to discover the environment/browser/runtime surfaces before poking deeper state.",
                "Use this instead of guessing command names, command families, query names, or playbook ids from stale memory or transcript fragments.",
                "Use this after capsule get_help('environment') if you need the richer local registry, local builtin topics, and server-side sequencing guidance.",
            ],
            "what_it_changes": [
                "Nothing. env_help is read-only and only materializes the current registry, builtin topics, and search/index responses.",
            ],
            "mode_notes": [
                "env_help is the environment-side equivalent of targeted get_help(...), not a replacement for the entire capsule help system.",
                "Capsule get_help('environment') is the umbrella/capsule view; env_help(...) is the richer local registry exposed by this server for environment/browser/runtime surfaces.",
                "Cold start order: env_help(topic='env_help'), then env_help(topic='index'), then the specific topic/category/search you actually need.",
            ],
            "verification": [
                "env_help(topic='env_help')",
                "env_help(topic='index')",
                "env_help(topic='output_state')",
                "env_help(topic='env_report')",
                "env_help(topic='continuity_reacclimation')",
            ],
            "gotchas": [
                "If you only ask capsule get_help('environment') and stop there, you can miss local env_help topics, aliases, and sequencing notes.",
                "env_help returns structured reference and search/index responses; it does not mutate runtime state or bypass theater-first gates for deeper observation tools.",
                "Use topic/category/search intentionally; the goal is to resolve the next valid surface, not to dump raw shared_state.",
            ],
            "failure_modes": [
                "Environment registry unavailable or stale.",
                "Cold agent queries the capsule help only and never follows the bridge into env_help.",
                "Operator confuses env_help(topic='env_help') with get_help('env_help'); the first is local and rich, the second may be absent in the capsule registry.",
            ],
            "aliases": [
                "environment_help",
                "help:environment",
                "help:env_help",
                "envhelp",
            ],
            "surface_entrypoints": [],
            "bridges_to": [
                "commands",
                "queries",
                "families",
                "playbooks",
                "env_report",
                "continuity_restore",
            ],
            "related_commands": [
                "env_report",
                "continuity_restore",
                "text_theater_embodiment",
                "text_theater_snapshot",
            ],
        },
        "env_report": {
            "tool": "env_report",
            "entry_kind": "env_tool",
            "title": "Environment Report Broker",
            "category": "observation_query",
            "status": "live",
            "transport": {
                "local_proxy": True,
                "browser_surface": False,
                "ui_local_only": False,
                "implemented_verb": True,
            },
            "target_contract": {
                "shape": "json",
                "description": "JSON payload with required report_id and optional target/raw_slice fields.",
                "examples": [
                    "{\"report_id\":\"route_stability_diagnosis\"}",
                    "{\"report_id\":\"route_stability_diagnosis\",\"raw_slice\":true}",
                    "{\"report_id\":\"paired_state_alignment\"}",
                ],
            },
        "summary": "Build a small, auditable report over blackboard, text-theater snapshot, and workbench truth without dumping raw shared_state.",
        "when_to_use": [
            "Use this after reading text theater, then the consult/blackboard query-work surface, then text_theater_snapshot when you need scoped reasoning instead of rummaging through raw shared_state.",
            "Use route_stability_diagnosis when the question is about route status, support realization, blocker truth, next adjustment, or how bad the staged posture visibly is.",
            "Use paired_state_alignment when you need to compare recovered archive posture against the current live query thread on the same sequence spine.",
        ],
            "what_it_changes": [
            "Nothing. env_report is read-only and stateless.",
        ],
        "mode_notes": [
            "env_report is a stateless materializer over existing truth. It does not plan routes, mutate builder state, or become a second authority plane.",
            "The theater-first gate still applies. Read text_theater/text_theater_embodiment first, use consult/blackboard as the visible query-work lane, read snapshot second, then ask for a scoped report.",
            "The first recipe fuses text-theater embodiment evidence with blackboard/workbench truth so the report can tell you what the pose actually looks like, not just which rows are hot.",
        ],
            "verification": [
                "env_read(query='text_theater_embodiment')",
                "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
                "env_read(query='text_theater_snapshot')",
                "env_report(report_id='route_stability_diagnosis')",
                "capture_probe('character_runtime::mounted_primary')",
                "env_read(query='shared_state')",
            ],
            "gotchas": [
                "If no fresh text-theater read has been recorded for the current frame, env_report forwards the theater-first gate instead of bypassing it.",
                "Reports are intentionally small. If you need broader evidence, follow recommended_next_reads or request raw_slice explicitly.",
                "Recipes should stay additive and small; paired_state_alignment compares archive/live query posture and does not replace the live blackboard authority.",
            ],
            "failure_modes": [
                "Unknown report_id.",
                "Missing live fields for the requested recipe.",
                "Gate blocked because text-theater intake has not been satisfied.",
            ],
            "aliases": [
                "route_stability_diagnosis",
                "report:route_stability_diagnosis",
                "paired_state_alignment",
                "report:paired_state_alignment",
            ],
            "surface_entrypoints": [],
            "bridges_to": [
                "shared_state.blackboard",
                "shared_state.text_theater.snapshot",
                "shared_state.workbench or shared_state.mounted_character_runtime.workbench_surface",
            ],
            "related_commands": [
                "text_theater_embodiment",
                "text_theater_snapshot",
                "workbench_stage_contact",
                "workbench_assert_balance",
            ],
        },
        "dreamer_control_plane": {
            "tool": "dreamer_control_plane",
            "entry_kind": "operator_surface",
            "title": "Dreamer Outer Control Plane",
            "category": "dreamer",
            "status": "live",
            "transport": {
                "local_proxy": False,
                "browser_surface": True,
                "ui_local_only": False,
                "implemented_verb": False,
            },
            "target_contract": {
                "shape": "config sections",
                "description": "Operator-facing Dreamer settings persisted in the server layer. This does not mutate the inner capsule RSSM architecture.",
                "examples": [
                    "{\"control_plane\":{\"mode\":\"passive\",\"task\":\"half_kneel_l\",\"profile\":\"kneel_v1\"}}",
                    "{\"overlay\":{\"theater_hud\":true,\"show_grounding\":true,\"detail_level\":\"diagnostic\"}}",
                ],
            },
            "summary": "Orient the fixed capsule Dreamer through server-side config, mechanics observation, theater mirrors, and auditable trail surfaces.",
            "when_to_use": [
                "Use this when you need to understand which Dreamer settings are safe to adjust without touching champion_gen8.py or the capsule bundle.",
                "Use this before treating Dreamer as an environment facility so the operator settings, overlay behavior, and observational contract stay aligned.",
            ],
            "what_it_changes": [
                "Dreamer config sections served by /api/dreamer/config and /api/dreamer/config/effective.",
                "Browser-facing Dreamer behavior such as mode labels, selected task/profile, and overlay preferences.",
            ],
            "mode_notes": [
                "This is the outer control plane only. The capsule Dreamer remains fixed and should be treated as read-only infrastructure.",
                "mode/task/profile/obs_schema/action_schema_id/reward_profile belong here; RSSM action_dim and latent architecture do not.",
                "Environment association happens through env_help, the Dreamer tab, theater HUD work, blackboard/text-theater mirrors, and env_report recipes.",
            ],
            "verification": [
                "env_help(topic='dreamer_control_plane')",
                "env_help(topic='dreamer_mechanics_obs')",
                "env_read(query='text_theater_embodiment')",
                "env_read(query='text_theater_snapshot')",
                "env_report(report_id='route_stability_diagnosis')",
            ],
            "gotchas": [
                "Changing control-plane settings does not reconfigure the inner capsule Dreamer architecture.",
                "The current outer loop is observation-first. Proposal preview and episode stepping are future server actions, not implied by these settings alone.",
                "Do not treat this topic as permission to create a second proposal authority outside the existing mechanics/workbench substrate.",
            ],
            "failure_modes": [
                "Confusing editable operator settings with read-only runtime architecture.",
                "Assuming saved config implies live episode execution or proposal routing that has not been implemented yet.",
            ],
            "aliases": [
                "dreamer",
                "dreamer_config",
                "dreamer_outer_loop",
            ],
            "surface_entrypoints": [
                "Dreamer tab > Grounding Status",
                "Dreamer tab > Recent Dreamer Trail",
                "Dreamer tab > Dreamer Config",
            ],
            "bridges_to": [
                "/api/dreamer/config",
                "/api/dreamer/config/effective",
                "/api/dreamer/state",
                "/api/dreamer/mechanics_obs",
                "shared_state.blackboard",
                "shared_state.text_theater.snapshot",
            ],
            "related_commands": [
                "env_report",
                "text_theater_embodiment",
                "text_theater_snapshot",
            ],
        },
        "dreamer_mechanics_obs": {
            "tool": "dreamer_mechanics_obs",
            "entry_kind": "operator_surface",
            "title": "Dreamer Mechanics Observation",
            "category": "dreamer",
            "status": "live",
            "transport": {
                "local_proxy": False,
                "browser_surface": True,
                "ui_local_only": False,
                "implemented_verb": False,
            },
            "target_contract": {
                "shape": "json payload",
                "description": "Compact mechanics observation vector, grouped feature payload, and the current bounded correction vocabulary served by /api/dreamer/mechanics_obs.",
                "examples": [
                    "{\"schema_id\":\"dreamer_mechanics_v1\",\"target_task\":\"half_kneel_l\"}",
                ],
            },
            "summary": "Read the compact mechanics observation Dreamer uses at the server layer: route, balance, contact, pose, and the 8-action kneel correction vocabulary.",
            "when_to_use": [
                "Use this when Dreamer needs to be grounded against real workbench truth instead of generic reward/training counters.",
                "Use this before talking about kneel proposals, correction vocabularies, or environment-native Dreamer overlays.",
            ],
            "what_it_changes": [
                "Nothing by itself. This is a read-only observation and vocabulary surface.",
            ],
            "mode_notes": [
                "The current schema is dreamer_mechanics_v1 and is sourced from text_theater_snapshot/workbench truth at the server layer.",
                "This is the outer-layer observation contract. It does not mean the inner capsule obs_buffer is already mechanics-grounded.",
                "The correction table is bounded on purpose so Dreamer association stays inside the existing mechanics/workbench authority plane.",
            ],
            "verification": [
                "env_help(topic='dreamer_mechanics_obs')",
                "env_read(query='text_theater_snapshot')",
                "env_report(report_id='route_stability_diagnosis')",
            ],
            "gotchas": [
                "obs_buffer_size can still be zero even while this observation feed is live. That is expected until a separate episode/grounding bridge exists.",
                "Do not confuse the mechanics observation vector with text-theater rendering; the latter is a readable mirror, not the numeric schema itself.",
            ],
            "failure_modes": [
                "No fresh text_theater_snapshot available.",
                "Workbench/contact fields missing for the target task.",
            ],
            "aliases": [
                "dreamer_obs",
                "dreamer_mechanics",
                "mechanics_obs",
            ],
            "surface_entrypoints": [
                "Dreamer tab > Grounding Status",
                "Dreamer tab > Mechanics Snapshot",
                "Dreamer tab > Observation Vector",
            ],
            "bridges_to": [
                "/api/dreamer/mechanics_obs",
                "shared_state.workbench.route_report",
                "shared_state.workbench.motion_diagnostics",
                "shared_state.workbench.active_controller",
            ],
            "related_commands": [
                "env_report",
                "workbench_stage_contact",
                "workbench_assert_balance",
            ],
        },
        "dreamer_transform_relay": {
            "tool": "dreamer_transform_relay",
            "entry_kind": "operator_surface",
            "title": "Dreamer Transform Relay",
            "category": "dreamer",
            "status": "live",
            "transport": {
                "local_proxy": False,
                "browser_surface": False,
                "ui_local_only": False,
                "implemented_verb": False,
            },
            "target_contract": {
                "shape": "json payload",
                "description": "Calibration relay over the live text-theater snapshot: per-bone observed pose, active local transform, macro baseline, and balance/support geometry.",
                "examples": [
                    "/api/dreamer/transform_relay",
                    "/api/dreamer/transform_relay?task=half_kneel_l&bones=hips,spine,chest,lower_leg_l,foot_r",
                ],
            },
            "summary": "Read exact calibration-facing pose and support geometry for the current Dreamer task without bypassing the theater-first doctrine.",
            "when_to_use": [
                "Use this when compact mechanics observations are not enough and you need exact per-bone relay data for calibration or carrier-chain diagnosis.",
                "Use this before building bounded sweeps so the baseline local/world transform read is explicit and auditable.",
            ],
            "what_it_changes": [
                "Nothing. This is a read-only calibration relay.",
            ],
            "mode_notes": [
                "This surface is gated behind the same text-theater-first doctrine as deeper shared-state access.",
                "It is intended for calibration, relay, and ranker retuning work, not as a replacement for text_theater_embodiment or env_report.",
            ],
            "verification": [
                "env_read(query='text_theater_embodiment')",
                "env_read(query='text_theater_snapshot')",
                "env_help(topic='dreamer_transform_relay')",
                "/api/dreamer/transform_relay",
            ],
            "gotchas": [
                "If the theater-first gate has not been satisfied, the relay should be treated as blocked rather than worked around.",
                "Observed world pose and active local pose transform are different readings and should not be collapsed together.",
            ],
            "failure_modes": [
                "No fresh text_theater_snapshot available.",
                "Live workbench pose state missing for one or more target bones.",
            ],
            "aliases": [
                "transform_relay",
                "dreamer_calibration_relay",
            ],
            "surface_entrypoints": [
                "/api/dreamer/transform_relay",
                "Dreamer calibration workflow (planned)",
            ],
            "bridges_to": [
                "/api/dreamer/mechanics_obs",
                "text_theater_embodiment",
                "text_theater_snapshot",
                "env_report(route_stability_diagnosis)",
            ],
            "related_commands": [
                "dreamer_mechanics_obs",
                "env_report",
                "text_theater_embodiment",
                "text_theater_snapshot",
            ],
        },
    }


def _env_report_gate_state_snapshot() -> dict:
    with _env_text_theater_read_gate_lock:
        gate = dict(_env_text_theater_read_gate)
    return {
        "updated_ms": int(gate.get("updated_ms") or 0),
        "snapshot_timestamp": int(gate.get("snapshot_timestamp") or 0),
        "query": str(gate.get("query") or ""),
        "observed_at_ms": int(gate.get("observed_at_ms") or 0),
    }


def _env_report_trim_text(value, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _env_report_unique_strings(values, limit: int | None = None) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in values:
        text = str(entry or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _env_report_strip_ansi(text) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", str(text or ""))


def _env_report_extract_prefixed_lines(text, prefixes, *, limit: int = 6) -> list[str]:
    cleaned = _env_report_strip_ansi(text)
    if not cleaned:
        return []
    prefix_list = [str(prefix or "").strip().lower() for prefix in (prefixes or []) if str(prefix or "").strip()]
    if not prefix_list:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if not any(lower_line.startswith(prefix) for prefix in prefix_list):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= max(1, int(limit or 1)):
            break
    return out


def _env_report_normalize_target(value, shared_state: dict | None = None) -> dict:
    candidate = value
    if isinstance(candidate, str):
        text = candidate.strip()
        if text.startswith("{"):
            try:
                candidate = json.loads(text)
            except Exception:
                candidate = text
        elif "::" in text:
            kind, ident = text.split("::", 1)
            candidate = {"kind": kind, "id": ident}
        elif text:
            candidate = {"kind": "", "id": text}
    if isinstance(candidate, dict):
        kind = str(candidate.get("kind") or candidate.get("type") or "").strip()
        ident = str(candidate.get("id") or candidate.get("target_id") or candidate.get("value") or "").strip()
        if kind or ident:
            return {"kind": kind, "id": ident}
    state = shared_state if isinstance(shared_state, dict) else {}
    blackboard = state.get("blackboard") if isinstance(state.get("blackboard"), dict) else {}
    focus = blackboard.get("focus") if isinstance(blackboard.get("focus"), dict) else {}
    if not focus and isinstance(state.get("focus"), dict):
        focus = state.get("focus")
    return {
        "kind": str(focus.get("kind") or ""),
        "id": str(focus.get("id") or ""),
    }


def _env_report_build_session_thread(shared_state: dict | None = None) -> dict:
    state = shared_state if isinstance(shared_state, dict) else {}
    blackboard = state.get("blackboard") if isinstance(state.get("blackboard"), dict) else {}
    working_set = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working_set.get("query_thread") if isinstance(working_set.get("query_thread"), dict) else {}
    workbench = state.get("workbench") if isinstance(state.get("workbench"), dict) else {}
    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    active_controller = workbench.get("active_controller") if isinstance(workbench.get("active_controller"), dict) else {}
    session_thread = {
        "selected_bone_ids": _env_report_unique_strings(working_set.get("selected_bone_ids") or []),
        "supporting_joint_ids": _env_report_unique_strings(working_set.get("supporting_joint_ids") or []),
        "intended_support_set": _env_report_unique_strings(working_set.get("intended_support_set") or []),
        "missing_support_set": _env_report_unique_strings(working_set.get("missing_support_set") or []),
        "active_controller_id": str(
            working_set.get("active_controller_id")
            or active_controller.get("controller_id")
            or active_controller.get("label")
            or ""
        ),
        "active_route_id": str(
            working_set.get("active_route_id")
            or route_report.get("pose_macro_id")
            or route_report.get("support_topology_label")
            or ""
        ),
        "pinned_row_ids": _env_report_unique_strings(working_set.get("pinned_row_ids") or []),
        "lead_row_ids": _env_report_unique_strings(working_set.get("lead_row_ids") or [], limit=12),
    }
    if query_thread:
        session_thread["query_thread"] = {
            "sequence_id": str(query_thread.get("sequence_id") or ""),
            "segment_id": str(query_thread.get("segment_id") or ""),
            "session_id": str(query_thread.get("session_id") or ""),
            "subject_kind": str(query_thread.get("subject_kind") or ""),
            "subject_id": str(query_thread.get("subject_id") or ""),
            "subject_key": str(query_thread.get("subject_key") or ""),
            "status": str(query_thread.get("status") or ""),
            "current_pivot_id": str(query_thread.get("current_pivot_id") or ""),
            "objective_id": str(query_thread.get("objective_id") or ""),
            "objective_label": str(query_thread.get("objective_label") or ""),
            "visible_read": str(query_thread.get("visible_read") or ""),
            "anchor_row_ids": _env_report_unique_strings(query_thread.get("anchor_row_ids") or [], limit=8),
            "raw_state_guardrail": str(query_thread.get("raw_state_guardrail") or ""),
            "priority_pivots": [
                _json_clone(item)
                for item in list(query_thread.get("priority_pivots") or [])[:4]
                if isinstance(item, dict)
            ],
            "help_lane": [
                _json_clone(item)
                for item in list(query_thread.get("help_lane") or [])[:4]
                if isinstance(item, dict)
            ],
            "next_reads": [
                _json_clone(item)
                for item in list(query_thread.get("next_reads") or [])[:4]
                if isinstance(item, dict)
            ],
        }
    return session_thread


def _env_report_normalize_query_state(query_state: dict | None = None) -> dict:
    query = query_state if isinstance(query_state, dict) else {}
    return {
        "sequence_id": str(query.get("sequence_id") or ""),
        "segment_id": str(query.get("segment_id") or ""),
        "session_id": str(query.get("session_id") or ""),
        "subject_kind": str(query.get("subject_kind") or ""),
        "subject_id": str(query.get("subject_id") or ""),
        "subject_key": str(query.get("subject_key") or ""),
        "status": str(query.get("status") or ""),
        "current_pivot_id": str(query.get("current_pivot_id") or ""),
        "objective_id": str(query.get("objective_id") or ""),
        "objective_label": str(query.get("objective_label") or ""),
        "visible_read": str(query.get("visible_read") or ""),
        "anchor_row_ids": _env_report_unique_strings(query.get("anchor_row_ids") or [], limit=8),
        "priority_pivots": [
            _json_clone(item)
            for item in list(query.get("priority_pivots") or [])[:6]
            if isinstance(item, dict)
        ],
        "help_lane": [
            _json_clone(item)
            for item in list(query.get("help_lane") or [])[:6]
            if isinstance(item, dict)
        ],
        "next_reads": [
            _json_clone(item)
            for item in list(query.get("next_reads") or [])[:6]
            if isinstance(item, dict)
        ],
        "raw_state_guardrail": str(query.get("raw_state_guardrail") or ""),
        "archive_resume_only": bool(query.get("archive_resume_only")),
        "opened_at_ms": int(query.get("opened_at_ms") or 0),
        "last_seen_at_ms": int(query.get("last_seen_at_ms") or 0),
    }


def _env_report_normalize_output_state(output_state: dict | None = None) -> dict:
    state = output_state if isinstance(output_state, dict) else {}
    desired = state.get("desired") if isinstance(state.get("desired"), dict) else {}
    observed = state.get("observed") if isinstance(state.get("observed"), dict) else {}
    derived = state.get("derived") if isinstance(state.get("derived"), dict) else {}
    placement = state.get("placement") if isinstance(state.get("placement"), dict) else {}
    trajectory_correlator = state.get("trajectory_correlator") if isinstance(state.get("trajectory_correlator"), dict) else {}
    continuity_cue = state.get("continuity_cue") if isinstance(state.get("continuity_cue"), dict) else {}
    tinkerbell_attention = state.get("tinkerbell_attention") if isinstance(state.get("tinkerbell_attention"), dict) else {}
    technolit_distribution_packet = (
        state.get("technolit_distribution_packet")
        if isinstance(state.get("technolit_distribution_packet"), dict)
        else {}
    )
    technolit_treasury_bridge_packet = (
        state.get("technolit_treasury_bridge_packet")
        if isinstance(state.get("technolit_treasury_bridge_packet"), dict)
        else {}
    )
    holder_snapshot_packet = (
        state.get("holder_snapshot_packet")
        if isinstance(state.get("holder_snapshot_packet"), dict)
        else {}
    )
    raid_contribution_packet = (
        state.get("raid_contribution_packet")
        if isinstance(state.get("raid_contribution_packet"), dict)
        else {}
    )
    settlement_epoch_packet = (
        state.get("settlement_epoch_packet")
        if isinstance(state.get("settlement_epoch_packet"), dict)
        else {}
    )
    hold_door_raid_report_packet = (
        state.get("hold_door_raid_report_packet")
        if isinstance(state.get("hold_door_raid_report_packet"), dict)
        else {}
    )
    hold_door_comedia_packet = (
        state.get("hold_door_comedia_packet")
        if isinstance(state.get("hold_door_comedia_packet"), dict)
        else {}
    )
    threat_bounty_packet = (
        state.get("threat_bounty_packet")
        if isinstance(state.get("threat_bounty_packet"), dict)
        else {}
    )
    pan_probe = state.get("pan_probe") if isinstance(state.get("pan_probe"), dict) else {}
    equilibrium = state.get("equilibrium") if isinstance(state.get("equilibrium"), dict) else {}
    technolit_measure = (
        equilibrium.get("technolit_measure")
        if isinstance(equilibrium.get("technolit_measure"), dict)
        else {}
    )
    drift = state.get("drift") if isinstance(state.get("drift"), dict) else {}
    field_disposition = state.get("field_disposition") if isinstance(state.get("field_disposition"), dict) else {}
    watch_board = state.get("watch_board") if isinstance(state.get("watch_board"), dict) else {}
    receipts = state.get("receipts") if isinstance(state.get("receipts"), dict) else {}
    freshness = state.get("freshness") if isinstance(state.get("freshness"), dict) else {}
    confidence = state.get("confidence") if isinstance(state.get("confidence"), dict) else {}
    sources = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    return {
        "orientation_id": str(state.get("orientation_id") or ""),
        "summary": str(state.get("summary") or ""),
        "desired": {
            "sequence_id": str(desired.get("sequence_id") or ""),
            "segment_id": str(desired.get("segment_id") or ""),
            "session_id": str(desired.get("session_id") or ""),
            "current_pivot_id": str(desired.get("current_pivot_id") or ""),
            "objective_id": str(desired.get("objective_id") or ""),
            "objective_label": str(desired.get("objective_label") or ""),
            "subject_key": str(desired.get("subject_key") or ""),
            "anchor_row_ids": _env_report_unique_strings(desired.get("anchor_row_ids") or [], limit=8),
            "priority_pivots": _env_report_unique_strings(desired.get("priority_pivots") or [], limit=6),
        },
        "observed": {
            "theater_mode": str(observed.get("theater_mode") or ""),
            "visual_mode": str(observed.get("visual_mode") or ""),
            "focus_key": str(observed.get("focus_key") or ""),
            "docs_context_kind": str(observed.get("docs_context_kind") or ""),
            "parity_summary": str(observed.get("parity_summary") or ""),
            "render_last_tool_applied": str(observed.get("render_last_tool_applied") or ""),
            "render_last_tool_source": str(observed.get("render_last_tool_source") or ""),
            "health_tone": str(observed.get("health_tone") or ""),
            "last_action": str(observed.get("last_action") or ""),
            "last_sync_reason": str(observed.get("last_sync_reason") or ""),
        },
        "derived": {
            "fixed_points": _json_clone(derived.get("fixed_points") or {}),
            "active_bands": _json_clone(derived.get("active_bands") or {}),
            "source_ready": _env_report_unique_strings(derived.get("source_ready") or [], limit=8),
            "source_missing": _env_report_unique_strings(derived.get("source_missing") or [], limit=8),
        },
        "placement": {
            "subject": str(placement.get("subject") or ""),
            "objective": str(placement.get("objective") or ""),
            "seam": str(placement.get("seam") or ""),
            "evidence": _json_clone(placement.get("evidence") or {}),
            "drift": _json_clone(placement.get("drift") or {}),
            "next": _json_clone(placement.get("next") or {}),
        },
        "trajectory_correlator": {
            "intended": _json_clone(trajectory_correlator.get("intended") or {}),
            "actual": _json_clone(trajectory_correlator.get("actual") or {}),
            "correlation": _json_clone(trajectory_correlator.get("correlation") or {}),
            "grade": str(trajectory_correlator.get("grade") or ""),
            "return_path": _json_clone(trajectory_correlator.get("return_path") or {}),
        },
        "continuity_cue": {
            "needed": bool(continuity_cue.get("needed")),
            "severity": str(continuity_cue.get("severity") or ""),
            "reasons": _env_report_unique_strings(continuity_cue.get("reasons") or [], limit=8),
            "last_good_sequence": str(continuity_cue.get("last_good_sequence") or ""),
            "next_action": str(continuity_cue.get("next_action") or ""),
            "prompt": str(continuity_cue.get("prompt") or ""),
            "recommended_reads": _env_report_unique_strings(continuity_cue.get("recommended_reads") or [], limit=8),
        },
        "tinkerbell_attention": {
            "band": str(tinkerbell_attention.get("band") or ""),
            "summary": str(tinkerbell_attention.get("summary") or ""),
            "attention_kind": str(tinkerbell_attention.get("attention_kind") or ""),
            "attention_target": str(tinkerbell_attention.get("attention_target") or ""),
            "attention_confidence": tinkerbell_attention.get("attention_confidence"),
            "hold_candidate": bool(tinkerbell_attention.get("hold_candidate")),
            "active_pointer": _json_clone(tinkerbell_attention.get("active_pointer") or {}),
            "prospect_candidates": [
                _json_clone(item)
                for item in list(tinkerbell_attention.get("prospect_candidates") or [])[:8]
                if isinstance(item, dict)
            ],
        },
        "technolit_distribution_packet": {
            "active": bool(technolit_distribution_packet.get("active")),
            "coin_id": str(technolit_distribution_packet.get("coin_id") or ""),
            "symbol": str(technolit_distribution_packet.get("symbol") or ""),
            "packet_kind": str(technolit_distribution_packet.get("packet_kind") or ""),
            "policy_id": str(technolit_distribution_packet.get("policy_id") or ""),
            "stage": str(technolit_distribution_packet.get("stage") or ""),
            "intake_mode": str(technolit_distribution_packet.get("intake_mode") or ""),
            "body_mode": str(technolit_distribution_packet.get("body_mode") or ""),
            "raid_mode": str(technolit_distribution_packet.get("raid_mode") or ""),
            "shield_mode": str(technolit_distribution_packet.get("shield_mode") or ""),
            "forge_mode": str(technolit_distribution_packet.get("forge_mode") or ""),
            "tokenized_agent_mode": str(technolit_distribution_packet.get("tokenized_agent_mode") or ""),
            "routing_posture": str(technolit_distribution_packet.get("routing_posture") or ""),
            "next_contract": str(technolit_distribution_packet.get("next_contract") or ""),
            "public_line": str(technolit_distribution_packet.get("public_line") or ""),
            "macro_split_bps": _json_clone(technolit_distribution_packet.get("macro_split_bps") or {}),
            "settlement_clock": _json_clone(technolit_distribution_packet.get("settlement_clock") or {}),
            "summary": str(technolit_distribution_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(technolit_distribution_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(technolit_distribution_packet.get("issues") or [], limit=8),
        },
        "technolit_treasury_bridge_packet": {
            "active": bool(technolit_treasury_bridge_packet.get("active")),
            "coin_id": str(technolit_treasury_bridge_packet.get("coin_id") or ""),
            "symbol": str(technolit_treasury_bridge_packet.get("symbol") or ""),
            "packet_kind": str(technolit_treasury_bridge_packet.get("packet_kind") or ""),
            "bridge_id": str(technolit_treasury_bridge_packet.get("bridge_id") or ""),
            "settlement_asset": str(technolit_treasury_bridge_packet.get("settlement_asset") or ""),
            "treasury_mode": str(technolit_treasury_bridge_packet.get("treasury_mode") or ""),
            "treasury_wallet_mode": str(technolit_treasury_bridge_packet.get("treasury_wallet_mode") or ""),
            "settlement_style": str(technolit_treasury_bridge_packet.get("settlement_style") or ""),
            "redemption_mode": str(technolit_treasury_bridge_packet.get("redemption_mode") or ""),
            "reference_ratio_mode": str(technolit_treasury_bridge_packet.get("reference_ratio_mode") or ""),
            "reserve_floor_mode": str(technolit_treasury_bridge_packet.get("reserve_floor_mode") or ""),
            "stage": str(technolit_treasury_bridge_packet.get("stage") or ""),
            "next_contract": str(technolit_treasury_bridge_packet.get("next_contract") or ""),
            "source_policy_id": str(technolit_treasury_bridge_packet.get("source_policy_id") or ""),
            "epoch_clock": _json_clone(technolit_treasury_bridge_packet.get("epoch_clock") or {}),
            "public_line": str(technolit_treasury_bridge_packet.get("public_line") or ""),
            "summary": str(technolit_treasury_bridge_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(technolit_treasury_bridge_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(technolit_treasury_bridge_packet.get("issues") or [], limit=8),
        },
        "holder_snapshot_packet": {
            "active": bool(holder_snapshot_packet.get("active")),
            "coin_id": str(holder_snapshot_packet.get("coin_id") or ""),
            "symbol": str(holder_snapshot_packet.get("symbol") or ""),
            "packet_kind": str(holder_snapshot_packet.get("packet_kind") or ""),
            "snapshot_id": str(holder_snapshot_packet.get("snapshot_id") or ""),
            "camp_label": str(holder_snapshot_packet.get("camp_label") or ""),
            "qualification_mode": str(holder_snapshot_packet.get("qualification_mode") or ""),
            "qualification_window": str(holder_snapshot_packet.get("qualification_window") or ""),
            "anti_snipe_mode": str(holder_snapshot_packet.get("anti_snipe_mode") or ""),
            "body_split_bps": holder_snapshot_packet.get("body_split_bps"),
            "stage": str(holder_snapshot_packet.get("stage") or ""),
            "retention_band": str(holder_snapshot_packet.get("retention_band") or ""),
            "concentration_band": str(holder_snapshot_packet.get("concentration_band") or ""),
            "anti_snipe_band": str(holder_snapshot_packet.get("anti_snipe_band") or ""),
            "public_line": str(holder_snapshot_packet.get("public_line") or ""),
            "summary": str(holder_snapshot_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(holder_snapshot_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(holder_snapshot_packet.get("issues") or [], limit=8),
        },
        "raid_contribution_packet": {
            "active": bool(raid_contribution_packet.get("active")),
            "coin_id": str(raid_contribution_packet.get("coin_id") or ""),
            "symbol": str(raid_contribution_packet.get("symbol") or ""),
            "packet_kind": str(raid_contribution_packet.get("packet_kind") or ""),
            "raid_id": str(raid_contribution_packet.get("raid_id") or ""),
            "raid_label": str(raid_contribution_packet.get("raid_label") or ""),
            "evidence_mode": str(raid_contribution_packet.get("evidence_mode") or ""),
            "scoring_formula": str(raid_contribution_packet.get("scoring_formula") or ""),
            "role_families": _env_report_unique_strings(raid_contribution_packet.get("role_families") or [], limit=8),
            "common_pool_bps": raid_contribution_packet.get("common_pool_bps"),
            "jackpot_pool_bps": raid_contribution_packet.get("jackpot_pool_bps"),
            "carry_pool_bps": raid_contribution_packet.get("carry_pool_bps"),
            "raid_split_bps": raid_contribution_packet.get("raid_split_bps"),
            "stage": str(raid_contribution_packet.get("stage") or ""),
            "public_line": str(raid_contribution_packet.get("public_line") or ""),
            "summary": str(raid_contribution_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(raid_contribution_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(raid_contribution_packet.get("issues") or [], limit=8),
        },
        "settlement_epoch_packet": {
            "active": bool(settlement_epoch_packet.get("active")),
            "coin_id": str(settlement_epoch_packet.get("coin_id") or ""),
            "symbol": str(settlement_epoch_packet.get("symbol") or ""),
            "packet_kind": str(settlement_epoch_packet.get("packet_kind") or ""),
            "epoch_id": str(settlement_epoch_packet.get("epoch_id") or ""),
            "settlement_asset": str(settlement_epoch_packet.get("settlement_asset") or ""),
            "settlement_style": str(settlement_epoch_packet.get("settlement_style") or ""),
            "release_governance": str(settlement_epoch_packet.get("release_governance") or ""),
            "circuit_breaker_mode": str(settlement_epoch_packet.get("circuit_breaker_mode") or ""),
            "reserve_cover_target_epochs": settlement_epoch_packet.get("reserve_cover_target_epochs"),
            "macro_split_bps": _json_clone(settlement_epoch_packet.get("macro_split_bps") or {}),
            "epoch_clock": _json_clone(settlement_epoch_packet.get("epoch_clock") or {}),
            "game_clock": _json_clone(settlement_epoch_packet.get("game_clock") or {}),
            "failure_watches": _env_report_unique_strings(settlement_epoch_packet.get("failure_watches") or [], limit=8),
            "stage": str(settlement_epoch_packet.get("stage") or ""),
            "next_contract": str(settlement_epoch_packet.get("next_contract") or ""),
            "public_line": str(settlement_epoch_packet.get("public_line") or ""),
            "summary": str(settlement_epoch_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(settlement_epoch_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(settlement_epoch_packet.get("issues") or [], limit=8),
        },
        "hold_door_raid_report_packet": {
            "active": bool(hold_door_raid_report_packet.get("active")),
            "coin_id": str(hold_door_raid_report_packet.get("coin_id") or ""),
            "symbol": str(hold_door_raid_report_packet.get("symbol") or ""),
            "packet_kind": str(hold_door_raid_report_packet.get("packet_kind") or ""),
            "report_id": str(hold_door_raid_report_packet.get("report_id") or ""),
            "display_name": str(hold_door_raid_report_packet.get("display_name") or ""),
            "camp_label": str(hold_door_raid_report_packet.get("camp_label") or ""),
            "raid_label": str(hold_door_raid_report_packet.get("raid_label") or ""),
            "custody_asset": str(hold_door_raid_report_packet.get("custody_asset") or ""),
            "stage": str(hold_door_raid_report_packet.get("stage") or ""),
            "title_line": str(hold_door_raid_report_packet.get("title_line") or ""),
            "cadence_line": str(hold_door_raid_report_packet.get("cadence_line") or ""),
            "safety_line": str(hold_door_raid_report_packet.get("safety_line") or ""),
            "public_line": str(hold_door_raid_report_packet.get("public_line") or ""),
            "summary": str(hold_door_raid_report_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(hold_door_raid_report_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(hold_door_raid_report_packet.get("issues") or [], limit=8),
        },
        "hold_door_comedia_packet": {
            "active": bool(hold_door_comedia_packet.get("active")),
            "coin_id": str(hold_door_comedia_packet.get("coin_id") or ""),
            "symbol": str(hold_door_comedia_packet.get("symbol") or ""),
            "packet_kind": str(hold_door_comedia_packet.get("packet_kind") or ""),
            "engine_id": str(hold_door_comedia_packet.get("engine_id") or ""),
            "persona_id": str(hold_door_comedia_packet.get("persona_id") or ""),
            "stage": str(hold_door_comedia_packet.get("stage") or ""),
            "mood": str(hold_door_comedia_packet.get("mood") or ""),
            "reaction": str(hold_door_comedia_packet.get("reaction") or ""),
            "spam_level": hold_door_comedia_packet.get("spam_level"),
            "caption_mode": str(hold_door_comedia_packet.get("caption_mode") or ""),
            "caption_line": str(hold_door_comedia_packet.get("caption_line") or ""),
            "caption_tokens": _env_report_unique_strings(hold_door_comedia_packet.get("caption_tokens") or [], limit=8),
            "audio_mode": str(hold_door_comedia_packet.get("audio_mode") or ""),
            "tempo_bpm": hold_door_comedia_packet.get("tempo_bpm"),
            "utterance_gap_ms": hold_door_comedia_packet.get("utterance_gap_ms"),
            "trajectory_trigger": str(hold_door_comedia_packet.get("trajectory_trigger") or ""),
            "public_line": str(hold_door_comedia_packet.get("public_line") or ""),
            "summary": str(hold_door_comedia_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(hold_door_comedia_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(hold_door_comedia_packet.get("issues") or [], limit=8),
        },
        "threat_bounty_packet": {
            "active": bool(threat_bounty_packet.get("active")),
            "coin_id": str(threat_bounty_packet.get("coin_id") or ""),
            "symbol": str(threat_bounty_packet.get("symbol") or ""),
            "packet_kind": str(threat_bounty_packet.get("packet_kind") or ""),
            "bounty_id": str(threat_bounty_packet.get("bounty_id") or ""),
            "lane_family": str(threat_bounty_packet.get("lane_family") or ""),
            "jackpot_mode": str(threat_bounty_packet.get("jackpot_mode") or ""),
            "adjacent_reward_mode": str(threat_bounty_packet.get("adjacent_reward_mode") or ""),
            "verification_mode": str(threat_bounty_packet.get("verification_mode") or ""),
            "critical_trigger_mode": str(threat_bounty_packet.get("critical_trigger_mode") or ""),
            "panic_farming_penalty": str(threat_bounty_packet.get("panic_farming_penalty") or ""),
            "active_threats": _env_report_unique_strings(threat_bounty_packet.get("active_threats") or [], limit=8),
            "stage": str(threat_bounty_packet.get("stage") or ""),
            "public_line": str(threat_bounty_packet.get("public_line") or ""),
            "summary": str(threat_bounty_packet.get("summary") or ""),
            "signals": _env_report_unique_strings(threat_bounty_packet.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(threat_bounty_packet.get("issues") or [], limit=8),
        },
        "equilibrium": {
            "band": str(equilibrium.get("band") or ""),
            "score": equilibrium.get("score"),
            "summary": str(equilibrium.get("summary") or ""),
            "signals": _env_report_unique_strings(equilibrium.get("signals") or [], limit=8),
            "issues": _env_report_unique_strings(equilibrium.get("issues") or [], limit=8),
            "technolit_measure": {
                "active": bool(technolit_measure.get("active")),
                "coin_id": str(technolit_measure.get("coin_id") or ""),
                "symbol": str(technolit_measure.get("symbol") or ""),
                "label": str(technolit_measure.get("label") or ""),
                "band": str(technolit_measure.get("band") or ""),
                "score": technolit_measure.get("score"),
                "measurement_unit": str(technolit_measure.get("measurement_unit") or ""),
                "sequencing_bridge": str(technolit_measure.get("sequencing_bridge") or ""),
                "bridge_surface": str(technolit_measure.get("bridge_surface") or ""),
                "market_cap_usd": technolit_measure.get("market_cap_usd"),
                "liquidity_usd": technolit_measure.get("liquidity_usd"),
                "bonding_curve_pct": technolit_measure.get("bonding_curve_pct"),
                "creator_rewards_unclaimed_sol": technolit_measure.get("creator_rewards_unclaimed_sol"),
                "creator_rewards_unclaimed_usd": technolit_measure.get("creator_rewards_unclaimed_usd"),
                "flow_posture": str(technolit_measure.get("flow_posture") or ""),
                "distribution_posture": str(technolit_measure.get("distribution_posture") or ""),
                "burn_gate": str(technolit_measure.get("burn_gate") or ""),
                "summary": str(technolit_measure.get("summary") or ""),
                "signals": _env_report_unique_strings(technolit_measure.get("signals") or [], limit=8),
                "issues": _env_report_unique_strings(technolit_measure.get("issues") or [], limit=8),
            },
        },
        "field_disposition": {
            "medium_kind": str(field_disposition.get("medium_kind") or ""),
            "profile_family": str(field_disposition.get("profile_family") or ""),
            "profile_active": str(field_disposition.get("profile_active") or ""),
            "propagation_mode": str(field_disposition.get("propagation_mode") or ""),
            "settling_band": str(field_disposition.get("settling_band") or ""),
            "activation_threshold": field_disposition.get("activation_threshold"),
            "density": field_disposition.get("density"),
            "speed": field_disposition.get("speed"),
            "turbulence": field_disposition.get("turbulence"),
            "flow_bias": _json_clone(field_disposition.get("flow_bias") or {}),
            "drift_bias": _json_clone(field_disposition.get("drift_bias") or {}),
            "gravity_bias": _json_clone(field_disposition.get("gravity_bias") or {}),
            "support_bias": _json_clone(field_disposition.get("support_bias") or {}),
            "coupled_surfaces": _env_report_unique_strings(field_disposition.get("coupled_surfaces") or [], limit=8),
            "summary": str(field_disposition.get("summary") or ""),
            "signals": _env_report_unique_strings(field_disposition.get("signals") or [], limit=8),
            "risks": _env_report_unique_strings(field_disposition.get("risks") or [], limit=8),
        },
        "pan_probe": {
            "mode": str(pan_probe.get("mode") or ""),
            "band": str(pan_probe.get("band") or ""),
            "summary": str(pan_probe.get("summary") or ""),
            "selected_bone_id": str(pan_probe.get("selected_bone_id") or ""),
            "selected_contact_joint": str(pan_probe.get("selected_contact_joint") or ""),
            "selected_contact_state": str(pan_probe.get("selected_contact_state") or ""),
            "support_role": str(pan_probe.get("support_role") or ""),
            "contact_bias": str(pan_probe.get("contact_bias") or ""),
            "rotational_grounding": bool(pan_probe.get("rotational_grounding")),
            "planted_alignment": pan_probe.get("planted_alignment"),
            "normal_alignment": pan_probe.get("normal_alignment"),
            "toe_clearance": pan_probe.get("toe_clearance"),
            "heel_clearance": pan_probe.get("heel_clearance"),
            "support_phase": str(pan_probe.get("support_phase") or ""),
            "timeline": _json_clone(pan_probe.get("timeline") or {}),
            "motion_sample_time": pan_probe.get("motion_sample_time"),
            "support_surface": _json_clone(pan_probe.get("support_surface") or {}),
            "writer_identity": _json_clone(pan_probe.get("writer_identity") or {}),
            "association_surfaces": _env_report_unique_strings(pan_probe.get("association_surfaces") or [], limit=8),
            "capture_surfaces": [
                _json_clone(item)
                for item in list(pan_probe.get("capture_surfaces") or [])[:8]
                if isinstance(item, dict)
            ],
        },
        "drift": {
            "band": str(drift.get("band") or ""),
            "issues": _env_report_unique_strings(drift.get("issues") or [], limit=8),
            "contaminated_surfaces": _env_report_unique_strings(drift.get("contaminated_surfaces") or [], limit=8),
            "missing_surfaces": _env_report_unique_strings(drift.get("missing_surfaces") or [], limit=8),
            "expected_docs_context": str(drift.get("expected_docs_context") or ""),
            "actual_docs_context": str(drift.get("actual_docs_context") or ""),
        },
        "watch_board": {
            "band": str(watch_board.get("band") or ""),
            "tracked_events": [
                _json_clone(item)
                for item in list(watch_board.get("tracked_events") or [])[:8]
                if isinstance(item, dict)
            ],
            "intercept_candidates": _env_report_unique_strings(watch_board.get("intercept_candidates") or [], limit=8),
            "help_candidates": _env_report_unique_strings(watch_board.get("help_candidates") or [], limit=8),
            "current_front": _json_clone(watch_board.get("current_front") or {}),
            "queue_pressure": _json_clone(watch_board.get("queue_pressure") or {}),
            "signals": _env_report_unique_strings(watch_board.get("signals") or [], limit=8),
            "alerts": _env_report_unique_strings(watch_board.get("alerts") or [], limit=8),
        },
        "receipts": {
            "last_action": str(receipts.get("last_action") or ""),
            "last_sync_reason": str(receipts.get("last_sync_reason") or ""),
            "active_doc": str(receipts.get("active_doc") or ""),
            "latest_execution_id": str(receipts.get("latest_execution_id") or ""),
        },
        "freshness": {
            "snapshot_timestamp": int(freshness.get("snapshot_timestamp") or 0),
            "source_timestamp": int(freshness.get("source_timestamp") or 0),
            "age_ms": int(freshness.get("age_ms") or 0),
            "mirror_lag": bool(freshness.get("mirror_lag")),
            "bundle_mismatch": bool(freshness.get("bundle_mismatch")),
            "live_sync_status": str(freshness.get("live_sync_status") or ""),
            "live_sync_age_ms": int(freshness.get("live_sync_age_ms") or -1),
        },
        "confidence": {
            "band": str(confidence.get("band") or ""),
            "score": confidence.get("score"),
            "source_count": int(confidence.get("source_count") or 0),
            "missing_sources": _env_report_unique_strings(confidence.get("missing_sources") or [], limit=8),
        },
        "sources": {
            str(key): _json_clone(value)
            for key, value in list(sources.items())[:8]
            if isinstance(value, dict)
        },
    }


def _env_report_query_lane_key(entry: dict | None = None) -> str:
    row = entry if isinstance(entry, dict) else {}
    tool = str(row.get("tool") or "").strip()
    args = row.get("args") if isinstance(row.get("args"), dict) else {}
    if tool == "env_read":
        return "env_read:" + str(args.get("query") or "").strip()
    if tool == "env_report":
        return "env_report:" + str(args.get("report_id") or "").strip()
    if tool == "env_help":
        topic = str(args.get("topic") or "").strip()
        category = str(args.get("category") or "").strip()
        search = str(args.get("search") or "").strip()
        return "env_help:" + (topic or category or search)
    if tool:
        try:
            return tool + ":" + json.dumps(args, sort_keys=True, separators=(",", ":"))
        except Exception:
            return tool + ":" + str(args)
    return ""


def _env_report_merge_query_lanes(*lanes) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for lane in lanes:
        for entry in list(lane or []):
            if not isinstance(entry, dict):
                continue
            key = _env_report_query_lane_key(entry)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(_json_clone(entry))
    return merged


def _env_report_restore_archive_continuity(query_thread: dict | None = None) -> dict:
    query = query_thread if isinstance(query_thread, dict) else {}
    summary_parts = [
        str(query.get("objective_label") or query.get("objective_id") or "").strip(),
        str(query.get("subject_key") or "").strip(),
        str(query.get("current_pivot_id") or "").strip(),
    ]
    summary = " ".join(part for part in summary_parts if part).strip()
    payload = continuity_restore_payload(
        summary=summary or None,
        cwd=str(Path(__file__).resolve().parent),
        limit=1,
        since_days=365,
    )
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "error": "invalid_archive_payload",
            "archive_query_state": {},
            "archive_surface_prime": {},
            "archive_best_session": {},
        }
    continuity_packet = payload.get("continuity_packet") if isinstance(payload.get("continuity_packet"), dict) else {}
    return {
        "status": str(payload.get("status") or "error"),
        "summary": str((payload.get("query") if isinstance(payload.get("query"), dict) else {}).get("summary") or summary),
        "error": str(payload.get("error") or ""),
        "archive_query_state": _env_report_normalize_query_state(continuity_packet.get("query_state")),
        "archive_surface_prime": _json_clone(continuity_packet.get("surface_prime") or {}),
        "archive_paired_state": _json_clone(continuity_packet.get("paired_state_resource") or {}),
        "archive_best_session": _json_clone(payload.get("best_session") or {}),
        "archive_matched_sessions": [
            _json_clone(item)
            for item in list(payload.get("matched_sessions") or [])[:4]
            if isinstance(item, dict)
        ],
    }


def _env_report_build_live_mirror_context(shared_state: dict | None = None) -> dict:
    state = shared_state if isinstance(shared_state, dict) else {}
    text_theater = state.get("text_theater") if isinstance(state.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    return {
        "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
        "source_timestamp": int(snapshot.get("source_timestamp") or 0),
        "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
        "stale_flags": _json_clone(stale_flags),
        "mirror_lag": bool(stale_flags.get("mirror_lag")),
    }


def _env_report_build_paired_state(shared_state: dict | None = None, live_revision: int = 0) -> dict:
    session_thread = _env_report_build_session_thread(shared_state)
    live_query_state = _env_report_normalize_query_state(
        (session_thread.get("query_thread") if isinstance(session_thread.get("query_thread"), dict) else {})
    )
    archive_restore = _env_report_restore_archive_continuity(live_query_state)
    archive_query_state = archive_restore.get("archive_query_state") if isinstance(archive_restore.get("archive_query_state"), dict) else {}
    archive_surface_prime = archive_restore.get("archive_surface_prime") if isinstance(archive_restore.get("archive_surface_prime"), dict) else {}
    live_mirror_context = _env_report_build_live_mirror_context(shared_state)

    agreement_points: list[str] = []
    discrepancies: list[dict] = []

    def add_discrepancy(
        field: str,
        classification: str,
        archive_value,
        live_value,
        *,
        status: str = "open",
        note: str = "",
    ) -> None:
        discrepancies.append(
            {
                "field": str(field or ""),
                "classification": str(classification or "mismatch"),
                "archive_value": _json_clone(archive_value),
                "live_value": _json_clone(live_value),
                "status": str(status or "open"),
                "note": str(note or ""),
            }
        )

    archive_status = str(archive_restore.get("status") or "")
    if archive_status != "ok" or not archive_query_state:
        add_discrepancy(
            "archive_query_state",
            "no_archive_match",
            archive_restore.get("error") or "missing",
            "live_only",
            note="No matching continuity archive could be paired for the current live query thread.",
        )
    else:
        archive_objective = str(archive_query_state.get("objective_id") or "")
        live_objective = str(live_query_state.get("objective_id") or "")
        if archive_objective and live_objective and archive_objective == live_objective:
            agreement_points.append("objective_id")
        else:
            add_discrepancy(
                "objective_id",
                "truth",
                archive_objective,
                live_objective,
                note="Archive and live query posture disagree on the active objective.",
            )

        archive_subject = str(archive_query_state.get("subject_key") or "")
        live_subject = str(live_query_state.get("subject_key") or "")
        if archive_subject and live_subject and archive_subject == live_subject:
            agreement_points.append("subject_key")
        else:
            add_discrepancy(
                "subject_key",
                "truth",
                archive_subject,
                live_subject,
                note="Archive and live query posture disagree on the active subject.",
            )

        archive_pivot = str(archive_query_state.get("current_pivot_id") or "")
        live_pivot = str(live_query_state.get("current_pivot_id") or "")
        if archive_pivot and live_pivot and archive_pivot == live_pivot:
            agreement_points.append("current_pivot_id")
        else:
            add_discrepancy(
                "current_pivot_id",
                "contract",
                archive_pivot,
                live_pivot,
                note="Archive and live query posture disagree on the top pivot.",
            )

        archive_help = set(_env_report_query_lane_key(entry) for entry in archive_query_state.get("help_lane") or [])
        live_help = set(_env_report_query_lane_key(entry) for entry in live_query_state.get("help_lane") or [])
        archive_help.discard("")
        live_help.discard("")
        if archive_help and live_help and archive_help.intersection(live_help):
            agreement_points.append("help_lane_overlap")
        elif archive_help or live_help:
            add_discrepancy(
                "help_lane",
                "contract",
                sorted(archive_help),
                sorted(live_help),
                note="Archive and live help lanes are not yet aligned.",
            )

        archive_next = set(_env_report_query_lane_key(entry) for entry in archive_query_state.get("next_reads") or [])
        live_next = set(_env_report_query_lane_key(entry) for entry in live_query_state.get("next_reads") or [])
        archive_next.discard("")
        live_next.discard("")
        if archive_next and live_next and archive_next.intersection(live_next):
            agreement_points.append("next_reads_overlap")
        elif archive_next or live_next:
            add_discrepancy(
                "next_reads",
                "contract",
                sorted(archive_next),
                sorted(live_next),
                note="Archive and live next reads diverge.",
            )

    anchor_rows = _env_report_unique_strings(live_query_state.get("anchor_row_ids") or [], limit=8)
    if anchor_rows:
        agreement_points.append("anchor_row_ids_present")
    else:
        add_discrepancy(
            "anchor_row_ids",
            "contract",
            _env_report_unique_strings(archive_query_state.get("anchor_row_ids") or [], limit=8),
            [],
            note="The live query thread does not currently expose anchor rows.",
        )

    freshness = {
        "live_revision": int(live_revision or 0),
        "snapshot_timestamp": int(live_mirror_context.get("snapshot_timestamp") or 0),
        "source_timestamp": int(live_mirror_context.get("source_timestamp") or 0),
        "last_sync_reason": str(live_mirror_context.get("last_sync_reason") or ""),
        "mirror_lag": bool(live_mirror_context.get("mirror_lag")),
        "stale": bool(live_mirror_context.get("mirror_lag")),
        "archive_last_seen_at_ms": int(archive_query_state.get("last_seen_at_ms") or 0),
        "archive_opened_at_ms": int(archive_query_state.get("opened_at_ms") or 0),
        "reset_boundary_kind": str(
            (((archive_surface_prime.get("reset_boundary") if isinstance(archive_surface_prime.get("reset_boundary"), dict) else {}) or {}).get("boundary_kind") or "")
        ),
        "requires_fresh_live_read": bool(
            (((archive_surface_prime.get("reset_boundary") if isinstance(archive_surface_prime.get("reset_boundary"), dict) else {}) or {}).get("requires_fresh_live_read"))
        ),
    }
    if freshness["snapshot_timestamp"] and freshness["archive_last_seen_at_ms"] and freshness["snapshot_timestamp"] >= freshness["archive_last_seen_at_ms"]:
        agreement_points.append("snapshot_postdates_archive")
    if freshness["stale"]:
        add_discrepancy(
            "freshness",
            "freshness",
            {"archive_last_seen_at_ms": freshness["archive_last_seen_at_ms"]},
            {
                "snapshot_timestamp": freshness["snapshot_timestamp"],
                "mirror_lag": freshness["mirror_lag"],
            },
            note="The live text-theater mirror is stale or lagging, so the pair cannot be trusted yet.",
        )

    required_recorroboration = [
        str(item or "")
        for item in list(archive_surface_prime.get("corroboration_surfaces") or [])[:8]
        if str(item or "").strip()
    ]
    recommended_next_reads = _env_report_merge_query_lanes(
        archive_query_state.get("help_lane"),
        archive_query_state.get("next_reads"),
        live_query_state.get("help_lane"),
        live_query_state.get("next_reads"),
    )

    reset_boundary = _json_clone(archive_surface_prime.get("reset_boundary") or {})
    if not isinstance(reset_boundary, dict):
        reset_boundary = {}

    if discrepancies:
        if any(str(item.get("classification") or "") == "no_archive_match" for item in discrepancies):
            designation = "no_archive_match"
            severity = "watch"
        elif any(str(item.get("classification") or "") == "freshness" for item in discrepancies):
            designation = "stale_live_mirror"
            severity = "degraded"
        elif "objective_id" in agreement_points and ("subject_key" in agreement_points or "current_pivot_id" in agreement_points):
            designation = "partly_confirmed"
            severity = "watch"
        else:
            designation = "mismatch"
            severity = "degraded"
    else:
        designation = "confirmed"
        severity = "ok"

    decision = {
        "confirmed": "Archive and live posture align closely enough to continue on the shared query spine.",
        "partly_confirmed": "Archive and live posture overlap, but one or more comparison fields still need explicit corroboration.",
        "stale_live_mirror": "The archive match is usable, but the live mirror must be refreshed before trusting the pair.",
        "mismatch": "Archive and live posture diverge; continue through the live query thread and use the archive only as a recovery hint.",
        "no_archive_match": "No archive candidate matched the current live query thread; continue live and wait for a stronger archive seam.",
    }.get(designation, "Continue through the live query thread.")

    return {
        "archive_restore": archive_restore,
        "archive_query_state": archive_query_state,
        "live_query_state": live_query_state,
        "archive_surface_prime": archive_surface_prime,
        "live_mirror_context": live_mirror_context,
        "shared_query_identity": {
            "objective_id": str(live_query_state.get("objective_id") or archive_query_state.get("objective_id") or ""),
            "objective_label": str(live_query_state.get("objective_label") or archive_query_state.get("objective_label") or ""),
            "subject_key": str(live_query_state.get("subject_key") or archive_query_state.get("subject_key") or ""),
            "current_pivot_id": str(live_query_state.get("current_pivot_id") or archive_query_state.get("current_pivot_id") or ""),
        },
        "drift": {
            "status": designation,
            "agreement_points": agreement_points,
            "discrepancies": discrepancies,
            "decision": decision,
        },
        "freshness": freshness,
        "required_recorroboration": required_recorroboration,
        "recommended_next_reads": recommended_next_reads[:8],
        "reset_boundary": reset_boundary,
        "severity": severity,
        "designation": designation,
    }


def _env_report_error_payload(
    report_id: str,
    normalized_args: dict,
    *,
    live_revision: int = 0,
    summary: str,
    operation_status: str,
    error_code: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "tool": "env_report",
        "status": "error",
        "summary": _env_report_trim_text(summary, 140),
        "normalized_args": _json_clone(normalized_args if isinstance(normalized_args, dict) else {}),
        "delta": {
            "found": False,
            "report_id": str(report_id or ""),
            "live_revision": int(live_revision or 0),
        },
        "operation": "env_report",
        "operation_status": str(operation_status or "error"),
        "report_id": str(report_id or ""),
        "error": str(error_code or "error"),
    }
    if isinstance(extra, dict):
        delta_extra = extra.pop("delta", None)
        if isinstance(delta_extra, dict):
            payload["delta"].update(_json_clone(delta_extra))
        payload.update(_json_clone(extra))
    return payload


def _env_report_gate_blocked_payload(
    report_id: str,
    normalized_args: dict,
    gate_payload: dict,
    *,
    live_revision: int = 0,
) -> dict:
    gate = gate_payload if isinstance(gate_payload, dict) else {}
    extra = {
        "message": str(gate.get("message") or "Text-theater read required before env_report"),
        "required_sequence": _json_clone(gate.get("required_sequence") or []),
        "last_text_theater_read": _json_clone(gate.get("last_text_theater_read") or {}),
        "gate_state": _env_report_gate_state_snapshot(),
        "delta": _json_clone(gate.get("delta") or {}),
    }
    return _env_report_error_payload(
        report_id,
        normalized_args,
        live_revision=live_revision,
        summary=str(gate.get("summary") or "Text-theater read required before env_report"),
        operation_status="gate_blocked",
        error_code=str(gate.get("error") or "text_theater_first_required"),
        extra=extra,
    )


def _env_report_route_stability_diagnosis(
    shared_state: dict,
    target: dict,
    *,
    raw_slice: bool = False,
    live_revision: int = 0,
) -> dict:
    state = shared_state if isinstance(shared_state, dict) else {}
    blackboard = state.get("blackboard") if isinstance(state.get("blackboard"), dict) else None
    workbench = state.get("workbench") if isinstance(state.get("workbench"), dict) else None
    if not isinstance(workbench, dict):
        mounted_runtime = state.get("mounted_character_runtime") if isinstance(state.get("mounted_character_runtime"), dict) else {}
        fallback_workbench = mounted_runtime.get("workbench_surface") if isinstance(mounted_runtime.get("workbench_surface"), dict) else None
        if isinstance(fallback_workbench, dict):
            workbench = fallback_workbench
    text_theater = state.get("text_theater") if isinstance(state.get("text_theater"), dict) else None
    missing_paths: list[str] = []
    if not isinstance(blackboard, dict):
        missing_paths.append("shared_state.blackboard")
    if not isinstance((blackboard or {}).get("rows"), list):
        missing_paths.append("shared_state.blackboard.rows")
    if not isinstance((blackboard or {}).get("working_set"), dict):
        missing_paths.append("shared_state.blackboard.working_set")
    if not isinstance(workbench, dict):
        missing_paths.append("shared_state.workbench")
    if not isinstance((text_theater or {}).get("snapshot"), dict):
        missing_paths.append("shared_state.text_theater.snapshot")
    if missing_paths:
        return {
            "__error__": "missing",
            "missing_paths": missing_paths,
        }

    rows = blackboard.get("rows") if isinstance(blackboard.get("rows"), list) else []
    row_index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        if row_id and row_id not in row_index:
            row_index[row_id] = _json_clone(row)

    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    active_controller = workbench.get("active_controller") if isinstance(workbench.get("active_controller"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    embodiment_text = str(text_theater.get("embodiment") or "")
    session_thread = _env_report_build_session_thread(state)

    lead_rows: list[str] = []
    lead_seen: set[str] = set()
    lead_candidates = [
        "route.status",
        "route.phase",
        "route.blocker",
        "route.next_adjustment",
        "balance.stability_risk",
        "balance.stability_margin",
    ]
    for candidate in session_thread.get("lead_row_ids") or []:
        candidate = str(candidate or "").strip()
        if candidate in row_index and candidate in lead_candidates and candidate not in lead_seen:
            lead_rows.append(candidate)
            lead_seen.add(candidate)
    for candidate in lead_candidates:
        if candidate in row_index and candidate not in lead_seen:
            lead_rows.append(candidate)
            lead_seen.add(candidate)
        if len(lead_rows) >= 6:
            break

    supporting_rows: list[str] = []
    supporting_candidates = [
        "route.operational_state",
        "route.phase_gate",
        "controller.active",
        "controller.roles",
        "balance.load_imbalance",
        "balance.nearest_edge",
    ]
    supporting_seen = set(lead_rows)
    for candidate in supporting_candidates + list(session_thread.get("lead_row_ids") or []):
        candidate = str(candidate or "").strip()
        if candidate in row_index and candidate not in supporting_seen:
            supporting_rows.append(candidate)
            supporting_seen.add(candidate)
        if len(supporting_rows) >= 12:
            break

    def _row_value(row_id: str, default: str = "") -> str:
        row = row_index.get(row_id) if isinstance(row_index.get(row_id), dict) else {}
        value = row.get("value")
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value)
            except Exception:
                return str(value)
        return str(value)

    def _row_number(row_id: str):
        row = row_index.get(row_id) if isinstance(row_index.get(row_id), dict) else {}
        value = row.get("value")
        try:
            return float(value)
        except Exception:
            return None

    route_status = _row_value("route.status", str(route_report.get("support_topology_label") or route_report.get("pose_macro_id") or "none"))
    route_phase = _row_value("route.phase", str(route_report.get("active_phase_label") or "none"))
    route_blocker = _row_value("route.blocker", str(route_report.get("blocker_summary") or ""))
    route_gate = _row_value("route.phase_gate", str(route_report.get("phase_gate_summary") or ""))
    route_next = _row_value("route.next_adjustment", str(route_report.get("next_suggested_adjustment") or ""))
    operational_state = _row_value("route.operational_state", str(route_report.get("operational_state_label") or ""))
    stability_risk = _row_number("balance.stability_risk")
    stability_margin = _row_number("balance.stability_margin")
    observed_support = _env_report_unique_strings(session_thread.get("supporting_joint_ids") or [])
    intended_support = _env_report_unique_strings(session_thread.get("intended_support_set") or [])
    missing_support = _env_report_unique_strings(session_thread.get("missing_support_set") or [])
    has_active_route = str(route_status or "").strip().lower() not in {"", "none"}
    has_residual_support_posture = bool(observed_support or session_thread.get("active_controller_id") or active_controller)

    severity = "ok"
    if route_blocker or missing_support:
        severity = "critical"
    elif stability_margin is not None and stability_margin < 0:
        severity = "critical" if (has_active_route or has_residual_support_posture) else "degraded"
    elif stability_risk is not None and stability_risk >= 0.84:
        severity = "critical" if (has_active_route or has_residual_support_posture) else "degraded"
    elif stability_risk is not None and stability_risk >= 0.64:
        severity = "degraded"
    elif stability_risk is not None and stability_risk >= 0.4:
        severity = "watch"

    designation = "no_active_route"
    if has_active_route and missing_support and len(observed_support) == 1 and len(intended_support) >= 2:
        designation = "single_brace_collapse"
    elif has_active_route and missing_support:
        designation = "partial_support_realization"
    elif has_active_route and route_blocker:
        designation = "blocked_route"
    elif has_active_route and severity in {"critical", "degraded"}:
        designation = "unstable_route_realization"
    elif has_active_route:
        designation = "route_realized"
    elif has_residual_support_posture and severity == "critical":
        designation = "residual_braced_support"
    elif has_residual_support_posture and severity in {"degraded", "watch"}:
        designation = "residual_support_posture"

    expected_vs_observed_read = "Expected support " + (", ".join(intended_support) if intended_support else "none")
    expected_vs_observed_read += "; observed support " + (", ".join(observed_support) if observed_support else "none")
    if missing_support:
        expected_vs_observed_read += "; missing " + ", ".join(missing_support)
    expected_vs_observed_read = _env_report_trim_text(expected_vs_observed_read + ".", 220)

    if designation == "single_brace_collapse":
        failure_character = _env_report_trim_text(
            "Body has collapsed into a "
            + (", ".join(observed_support) if observed_support else "single-contact")
            + " brace while the intended "
            + (", ".join(missing_support) if missing_support else "support")
            + " never realized.",
            180,
        )
    elif designation == "partial_support_realization":
        failure_character = _env_report_trim_text(
            "Only part of the intended support topology realized; the requested route is still missing "
            + (", ".join(missing_support) if missing_support else "support")
            + ".",
            180,
        )
    elif designation == "blocked_route":
        failure_character = "Route logic is active, but the intended support transition is blocked."
    elif designation == "unstable_route_realization":
        failure_character = "Support topology is active, but the body remains mechanically unstable."
    elif designation == "route_realized":
        failure_character = "The intended support topology appears realized."
    elif designation == "residual_braced_support":
        failure_character = _env_report_trim_text(
            "No active route is running, but the body is still parked in a badly loaded braced support posture.",
            180,
        )
    elif designation == "residual_support_posture":
        failure_character = _env_report_trim_text(
            "No active route is running, but the body is still carrying a residual support posture.",
            180,
        )
    else:
        failure_character = "No active route is currently being diagnosed."

    contact_prefixes = [f"{contact_id}:" for contact_id in observed_support + missing_support]
    embodiment_lines = _env_report_extract_prefixed_lines(
        embodiment_text,
        ["WORKBENCH:", "BALANCE:", "SUMMARY:"] + contact_prefixes,
        limit=6,
    )
    if designation == "single_brace_collapse":
        visual_read = _env_report_trim_text(
            "The embodiment read shows "
            + (", ".join(observed_support) if observed_support else "one remaining support")
            + " carrying the body while "
            + (", ".join(missing_support) if missing_support else "the intended support")
            + " is still off the floor; it reads like a failed support transition, not a completed kneel.",
            240,
        )
    elif designation == "partial_support_realization":
        visual_read = _env_report_trim_text(
            "The embodiment read shows a partial support transition: some requested contacts landed, but the full intended posture has not realized.",
            240,
        )
    elif designation == "unstable_route_realization":
        visual_read = _env_report_trim_text(
            "The embodiment read shows the route posture shape, but the body still reads as unstable and badly loaded.",
            240,
        )
    elif designation == "residual_braced_support":
        visual_read = _env_report_trim_text(
            "The embodiment read shows no active route, but the body is still visibly parked in a braced support pose with bad loading and support geometry.",
            240,
        )
    elif designation == "residual_support_posture":
        visual_read = _env_report_trim_text(
            "The embodiment read shows no active route, but the body has not returned to a neutral support posture.",
            240,
        )
    elif embodiment_lines:
        summary_line = next((line for line in embodiment_lines if line.startswith("SUMMARY:")), "")
        visual_read = _env_report_trim_text(summary_line.replace("SUMMARY:", "", 1).strip() or failure_character, 240)
    else:
        visual_read = _env_report_trim_text(failure_character, 240)

    summary_head = operational_state or route_status or "No route"
    if designation == "residual_braced_support":
        summary_head = "Residual Braced Support"
    elif designation == "residual_support_posture":
        summary_head = "Residual Support Posture"
    summary_parts = [summary_head, route_phase or "no phase"]
    if route_blocker:
        summary_parts.append("blocker " + route_blocker)
    elif route_gate:
        summary_parts.append(route_gate)
    summary = _env_report_trim_text(" / ".join(part for part in summary_parts if part), 140)

    why_parts = [
        f"The active route is {route_status or 'none'}",
        f"phase {route_phase or 'none'}",
    ]
    if intended_support:
        why_parts.append("intended support " + ", ".join(intended_support))
    if missing_support:
        why_parts.append("missing support " + ", ".join(missing_support))
    if stability_risk is not None:
        why_parts.append(f"stability risk {stability_risk:.2f}")
    if stability_margin is not None:
        why_parts.append(f"margin {stability_margin:.3f} m")
    if route_blocker:
        why_parts.append("blocker " + route_blocker)
    if route_next:
        why_parts.append("next adjustment " + route_next)
    why_this_matters = _env_report_trim_text(". ".join(part.rstrip(".") for part in why_parts if part) + ".", 400)

    capture_target = "character_runtime::mounted_primary"
    target_kind = str((target or {}).get("kind") or "").strip()
    target_id = str((target or {}).get("id") or "").strip()
    if target_kind and target_id:
        capture_target = f"{target_kind}::{target_id}"
    elif target_id:
        capture_target = target_id

    report = {
        "report_id": "route_stability_diagnosis",
        "intent": _env_report_trim_text("Explain current route/support stability state and next adjustment", 120),
        "target": {
            "kind": target_kind,
            "id": target_id,
        },
        "summary": summary,
        "lead_rows": lead_rows[:6],
        "supporting_rows": supporting_rows[:12],
        "why_this_matters": why_this_matters,
        "severity": severity,
        "designation": designation,
        "visual_read": visual_read,
        "expected_vs_observed": {
            "expected_support": intended_support,
            "observed_support": observed_support,
            "missing_support": missing_support,
            "topology_read": expected_vs_observed_read,
        },
        "failure_character": failure_character,
        "embodied_evidence_lines": embodiment_lines,
        "recommended_next_reads": [
            {
                "tool": "env_read",
                "args": {"query": "text_theater_embodiment"},
                "reason": "Compare the broker's visual read against the current embodiment render",
            },
            {
                "tool": "env_read",
                "args": {"query": "text_theater_snapshot"},
                "reason": "Verify snapshot freshness and the structured rows that anchor the designation",
            },
            {
                "tool": "env_read",
                "args": {"query": "probe"},
                "reason": "Review the latest probe capture if the blocker persists after the next adjustment",
            },
        ],
        "recommended_captures": [
            {
                "tool": "env_control",
                "args": {"command": "capture_probe", "target_id": capture_target, "actor": "assistant"},
                "reason": "Get a fresh probe capture for the current route blocker",
            },
            {
                "tool": "env_control",
                "args": {"command": "capture_supercam", "target_id": capture_target, "actor": "assistant"},
                "reason": "Get a higher-level corroborating camera view of the active support topology",
            },
        ],
        "evidence_paths": [
            "shared_state.blackboard.rows",
            "shared_state.blackboard.working_set.lead_row_ids",
            "shared_state.blackboard.working_set.intended_support_set",
            "shared_state.blackboard.working_set.missing_support_set",
            "shared_state.workbench.route_report or shared_state.mounted_character_runtime.workbench_surface.route_report",
            "shared_state.workbench.active_controller or shared_state.mounted_character_runtime.workbench_surface.active_controller",
            "shared_state.text_theater.embodiment",
            "shared_state.text_theater.snapshot",
        ],
        "capture_ids": [],
        "live_revision": int(live_revision or 0),
        "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
        "text_theater_anchor": "text_theater.embodiment" if embodiment_lines else None,
        "gate_state": _env_report_gate_state_snapshot(),
        "session_thread": session_thread,
    }
    if raw_slice:
        scoped_rows = {}
        for row_id in lead_rows + supporting_rows:
            if row_id in row_index and row_id not in scoped_rows:
                scoped_rows[row_id] = _json_clone(row_index[row_id])
        report["raw_slice"] = {
            "blackboard_rows": scoped_rows,
            "working_set": _json_clone((blackboard or {}).get("working_set") or {}),
            "route_report": _json_clone(route_report),
            "active_controller": _json_clone(active_controller),
            "text_theater_snapshot": {
                "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
                "source_timestamp": int(snapshot.get("source_timestamp") or 0),
                "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
            },
            "text_theater_embodiment_lines": embodiment_lines,
        }
    return report


def _env_report_paired_state_alignment(
    shared_state: dict,
    target: dict,
    *,
    raw_slice: bool = False,
    live_revision: int = 0,
) -> dict:
    state = shared_state if isinstance(shared_state, dict) else {}
    blackboard = state.get("blackboard") if isinstance(state.get("blackboard"), dict) else {}
    working_set = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working_set.get("query_thread") if isinstance(working_set.get("query_thread"), dict) else {}
    text_theater = state.get("text_theater") if isinstance(state.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    missing_paths: list[str] = []
    if not isinstance(blackboard, dict):
        missing_paths.append("shared_state.blackboard")
    if not isinstance(working_set, dict):
        missing_paths.append("shared_state.blackboard.working_set")
    if not isinstance(query_thread, dict):
        missing_paths.append("shared_state.blackboard.working_set.query_thread")
    if not isinstance(snapshot, dict):
        missing_paths.append("shared_state.text_theater.snapshot")
    if missing_paths:
        return {
            "__error__": "missing",
            "missing_paths": missing_paths,
        }

    paired_state = _env_report_build_paired_state(state, live_revision=live_revision)
    archive_restore = paired_state.get("archive_restore") if isinstance(paired_state.get("archive_restore"), dict) else {}
    archive_best_session = archive_restore.get("archive_best_session") if isinstance(archive_restore.get("archive_best_session"), dict) else {}
    archive_query_state = paired_state.get("archive_query_state") if isinstance(paired_state.get("archive_query_state"), dict) else {}
    live_query_state = paired_state.get("live_query_state") if isinstance(paired_state.get("live_query_state"), dict) else {}
    live_output_state = _env_report_normalize_output_state(state.get("output_state"))
    drift = paired_state.get("drift") if isinstance(paired_state.get("drift"), dict) else {}
    designation = str(paired_state.get("designation") or "partly_confirmed")
    severity = str(paired_state.get("severity") or "watch")
    objective = str(
        (paired_state.get("shared_query_identity") if isinstance(paired_state.get("shared_query_identity"), dict) else {}).get("objective_label")
        or live_query_state.get("objective_label")
        or live_query_state.get("objective_id")
        or archive_query_state.get("objective_label")
        or archive_query_state.get("objective_id")
        or "Query posture"
    )
    subject_key = str(
        (paired_state.get("shared_query_identity") if isinstance(paired_state.get("shared_query_identity"), dict) else {}).get("subject_key")
        or live_query_state.get("subject_key")
        or archive_query_state.get("subject_key")
        or "n/a"
    )
    summary = _env_report_trim_text(objective + " / " + subject_key + " / " + designation, 140)

    why_parts = [
        "This report pairs archive continuity posture with the live blackboard query thread.",
        "Archive status " + str(archive_restore.get("status") or "error") + ".",
        "Drift decision " + str(drift.get("decision") or "continue through live query thread") + ".",
    ]
    if archive_best_session:
        why_parts.append(
            "Best archive session "
            + str(archive_best_session.get("session_id") or archive_best_session.get("session_path") or "")
            + "."
        )
    why_this_matters = _env_report_trim_text(" ".join(part for part in why_parts if part), 400)

    report = {
        "report_id": "paired_state_alignment",
        "intent": _env_report_trim_text("Pair archived continuity posture with the live query thread on one authoring surface", 120),
        "target": {
            "kind": str((target or {}).get("kind") or ""),
            "id": str((target or {}).get("id") or ""),
        },
        "summary": summary,
        "lead_rows": _env_report_unique_strings(live_query_state.get("anchor_row_ids") or [], limit=8),
        "supporting_rows": _env_report_unique_strings((working_set.get("lead_row_ids") or []), limit=12),
        "why_this_matters": why_this_matters,
        "severity": severity,
        "designation": designation,
        "shared_query_identity": _json_clone(paired_state.get("shared_query_identity") or {}),
        "output_state": _json_clone(live_output_state),
        "paired_state": {
            "archive_query_state": _json_clone(archive_query_state),
            "live_query_state": _json_clone(live_query_state),
            "live_output_state": _json_clone(live_output_state),
            "archive_surface_prime": _json_clone(paired_state.get("archive_surface_prime") or {}),
            "live_mirror_context": _json_clone(paired_state.get("live_mirror_context") or {}),
            "drift": _json_clone(drift),
            "freshness": _json_clone(paired_state.get("freshness") or {}),
            "required_recorroboration": _json_clone(paired_state.get("required_recorroboration") or []),
            "recommended_next_reads": _json_clone(paired_state.get("recommended_next_reads") or []),
            "reset_boundary": _json_clone(paired_state.get("reset_boundary") or {}),
        },
        "archive_match": {
            "status": str(archive_restore.get("status") or ""),
            "summary": str(archive_restore.get("summary") or ""),
            "best_session": _json_clone(archive_best_session),
            "matched_sessions": _json_clone(archive_restore.get("archive_matched_sessions") or []),
        },
        "recommended_next_reads": _json_clone(paired_state.get("recommended_next_reads") or []),
        "evidence_paths": [
            "continuity_restore(summary=<live objective + subject + pivot>, cwd=<repo>)",
            "shared_state.blackboard.working_set.query_thread",
            "shared_state.text_theater.snapshot",
            "shared_state.blackboard.working_set.lead_row_ids",
        ],
        "capture_ids": [],
        "live_revision": int(live_revision or 0),
        "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
        "text_theater_anchor": "text_theater.snapshot",
        "gate_state": _env_report_gate_state_snapshot(),
        "session_thread": _env_report_build_session_thread(state),
    }
    if raw_slice:
        report["raw_slice"] = {
            "archive_restore": _json_clone(archive_restore),
            "live_query_thread": _json_clone(query_thread),
            "text_theater_snapshot": {
                "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
                "source_timestamp": int(snapshot.get("source_timestamp") or 0),
                "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
                "stale_flags": _json_clone(snapshot.get("stale_flags") or {}),
            },
        }
    return report


def _env_report_local_proxy_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    report_id = str(args.get("report_id", "") or "").strip()
    target = args.get("target")
    raw_slice = _env_bool_arg(args.get("raw_slice", False))
    normalized_args = {
        "report_id": report_id,
        "target": _env_report_normalize_target(target),
        "raw_slice": bool(raw_slice),
    }
    if not report_id:
        return _env_report_error_payload(
            report_id,
            normalized_args,
            summary="Missing report_id",
            operation_status="unknown_report",
            error_code="unknown_report",
            extra={"available_reports": list(_ENV_REPORT_IDS)},
        )
    if report_id not in _ENV_REPORT_IDS:
        return _env_report_error_payload(
            report_id,
            normalized_args,
            summary=f"Unknown env_report recipe {report_id}",
            operation_status="unknown_report",
            error_code="unknown_report",
            extra={"available_reports": list(_ENV_REPORT_IDS)},
        )

    cached = _env_live_cache_snapshot()
    live_revision = int((cached or {}).get("updated_ms") or 0)
    gate_payload = _env_shared_state_prereq_payload("env_report", cached)
    if gate_payload is not None:
        return _env_report_gate_blocked_payload(report_id, normalized_args, gate_payload, live_revision=live_revision)

    live_state = (cached or {}).get("live_state") if isinstance(cached, dict) else None
    if not isinstance(live_state, dict):
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary="Live cache unavailable for env_report",
            operation_status="unavailable",
            error_code="unavailable",
            extra={"reason": "No live_state available in live cache", "cache_age_ms": 0},
        )

    shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else None
    if not isinstance(shared_state, dict):
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary="shared_state unavailable for env_report",
            operation_status="unavailable",
            error_code="unavailable",
            extra={"reason": "No shared_state available in live cache", "cache_age_ms": 0},
        )

    normalized_args["target"] = _env_report_normalize_target(target, shared_state)
    try:
        if report_id == "paired_state_alignment":
            report = _env_report_paired_state_alignment(
                shared_state,
                normalized_args["target"],
                raw_slice=raw_slice,
                live_revision=live_revision,
            )
        else:
            report = _env_report_route_stability_diagnosis(
                shared_state,
                normalized_args["target"],
                raw_slice=raw_slice,
                live_revision=live_revision,
            )
    except Exception as exc:
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary=f"env_report recipe {report_id} failed",
            operation_status="recipe_error",
            error_code="recipe_error",
            extra={
                "recipe": report_id,
                "exception_class": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    if isinstance(report, dict) and report.get("__error__") == "missing":
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary=f"env_report recipe {report_id} is missing live fields",
            operation_status="missing",
            error_code="missing",
            extra={"missing_paths": _json_clone(report.get("missing_paths") or [])},
        )

    if not isinstance(report, dict):
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary=f"env_report recipe {report_id} returned no report",
            operation_status="recipe_error",
            error_code="recipe_error",
            extra={
                "recipe": report_id,
                "exception_class": "InvalidReport",
                "message": "Recipe did not return a report dictionary",
            },
        )

    report_bytes = len(json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if report_bytes > _ENV_REPORT_DEFAULT_SIZE_BYTES and report.get("raw_slice") is not None:
        report.pop("raw_slice", None)
        report_bytes = len(json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    if report_bytes > _ENV_REPORT_HARD_CAP_BYTES:
        return _env_report_error_payload(
            report_id,
            normalized_args,
            live_revision=live_revision,
            summary=f"env_report recipe {report_id} exceeded size budget",
            operation_status="recipe_error",
            error_code="recipe_error",
            extra={
                "recipe": report_id,
                "exception_class": "ReportTooLarge",
                "message": f"Serialized report size {report_bytes} exceeds hard cap {_ENV_REPORT_HARD_CAP_BYTES}",
            },
        )

    return {
        "tool": "env_report",
        "status": "ok",
        "summary": _env_report_trim_text(report.get("summary") or f"Built {report_id}", 140),
        "normalized_args": _json_clone(normalized_args),
        "delta": {
            "found": True,
            "report_id": report_id,
            "live_revision": live_revision,
            "report_bytes": report_bytes,
        },
        "operation": "env_report",
        "operation_status": "ok",
        "report": _json_clone(report),
    }


def _env_next_control_sync_token(command: str) -> str:
    global _env_control_command_seq
    with _env_control_command_seq_lock:
        _env_control_command_seq += 1
        seq = int(_env_control_command_seq)
    safe_command = re.sub(r"[^a-z0-9_]+", "_", str(command or "").strip().lower()).strip("_") or "env_control"
    return f"{safe_command}:{int(time.time() * 1000)}:{seq}"


def _env_live_cache_matches_env_control(command: str, cached: dict | None, command_sync_token: str = "") -> bool:
    cmd = str(command or "").strip().lower()
    if not cmd:
        return False
    snapshot = _env_cached_text_theater_snapshot(cached)
    expected_token = str(command_sync_token or "").strip()
    observed_token = str(snapshot.get("command_sync_token", "") or "").strip()
    if expected_token:
        return bool(observed_token) and observed_token == expected_token
    last_reason = str(snapshot.get("last_sync_reason", "") or "").strip().lower()
    if not last_reason:
        return False
    if cmd in last_reason:
        return True
    if cmd.startswith("camera_") and last_reason.startswith("camera:"):
        return True
    if cmd.startswith("capture_") and last_reason.startswith("capture:"):
        return True
    if cmd.startswith("character_") and (last_reason.startswith("character:") or last_reason.startswith("character_runtime:")):
        return True
    if cmd.startswith("workbench_") and last_reason.startswith("workbench_"):
        return True
    if cmd.startswith("focus_") and last_reason.startswith("focus:"):
        return True
    if cmd.startswith("set_") and (last_reason.startswith("theater_mode:") or last_reason.startswith("camera:")):
        return True
    return False


async def _env_wait_for_live_cache_after_env_control(
    command: str,
    before_updated_ms: int = 0,
    command_sync_token: str = "",
    timeout_s: float = 1.8,
    poll_s: float = 0.05,
) -> tuple[dict | None, bool, int]:
    before_updated_ms = int(before_updated_ms or 0)
    deadline = time.time() + max(0.1, float(timeout_s or 0.1))
    latest = _env_live_cache_snapshot()
    matched = False
    while time.time() < deadline:
        current = _env_live_cache_snapshot()
        if isinstance(current, dict):
            latest = current
            current_updated_ms = int(current.get("updated_ms") or 0)
            if current_updated_ms > before_updated_ms:
                matched = _env_live_cache_matches_env_control(command, current, command_sync_token)
                if matched:
                    break
        await asyncio.sleep(max(0.01, float(poll_s or 0.01)))
    waited_ms = int(max(0.0, (time.time() - (deadline - max(0.1, float(timeout_s or 0.1)))) * 1000.0))
    return latest, matched, waited_ms


def _env_build_text_theater_observation(
    cached: dict | None,
    include_full: bool = True,
) -> dict | None:
    if not isinstance(cached, dict):
        return None
    live_state = cached.get("live_state") if isinstance(cached.get("live_state"), dict) else {}
    shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else {}
    if not isinstance(shared_state, dict) or not shared_state:
        return None
    text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    browser_theater = str(text_theater.get("theater") or "").strip()
    browser_embodiment = str(text_theater.get("embodiment") or "").strip()
    current_compact = browser_theater
    current_full = ""
    if browser_theater and browser_embodiment:
        current_full = browser_theater + "\n\n" + browser_embodiment
    elif browser_theater:
        current_full = browser_theater
    elif browser_embodiment:
        current_full = browser_embodiment

    if not isinstance(snapshot, dict) or not snapshot or not current_compact:
        module = _load_text_theater_module()
        synced_at = live_state.get("synced_at")
        compact_render = module.render_text_theater_shared_state(
            shared_state=shared_state,
            synced_at=synced_at,
            view_mode="consult",
            width=100,
            height=18,
            diagnostics_visible=False,
            section_key="theater",
        )
        snapshot = compact_render.get("snapshot") if isinstance(compact_render.get("snapshot"), dict) else {}
        current_compact = str(compact_render.get("frame") or "")
        if include_full:
            full_render = module.render_text_theater_shared_state(
                shared_state=shared_state,
                synced_at=synced_at,
                view_mode="split",
                width=140,
                height=44,
                diagnostics_visible=False,
                section_key="theater",
            )
            current_full = str(full_render.get("frame") or "")

    stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    payload = {
        "mode": "current",
        "current_compact": current_compact,
        "snapshot": _json_clone(snapshot),
        "freshness": {
            "stale": bool(stale_flags.get("mirror_lag")),
            "mirror_lag": bool(stale_flags.get("mirror_lag")),
            "cache_updated_ms": int(cached.get("updated_ms") or 0),
            "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
            "source_timestamp": int(snapshot.get("source_timestamp") or 0),
            "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
        },
    }
    if include_full:
        payload["current_full"] = current_full
    return payload


async def _env_control_attach_text_theater_observation(
    payload: dict,
    args: dict | None = None,
    before_updated_ms: int = 0,
) -> dict:
    args = args or {}
    out = dict(payload or {})
    command = str(out.get("command", "") or "").strip()
    command_sync_token = str(out.get("command_sync_token", "") or "").strip()
    include_full = _env_bool_arg(args.get("include_full"), True)
    cached, matched_command_sync, waited_ms = await _env_wait_for_live_cache_after_env_control(
        command=command,
        before_updated_ms=before_updated_ms,
        command_sync_token=command_sync_token,
    )
    observation = _env_build_text_theater_observation(cached, include_full=include_full)
    if observation:
        freshness = observation.get("freshness") if isinstance(observation.get("freshness"), dict) else {}
        cache_updated_ms = int((cached or {}).get("updated_ms") or 0)
        cache_advanced = cache_updated_ms > int(before_updated_ms or 0)
        snapshot = observation.get("snapshot") if isinstance(observation.get("snapshot"), dict) else {}
        freshness["cache_advanced_after_command"] = bool(cache_advanced)
        freshness["matched_command_sync"] = bool(matched_command_sync)
        freshness["expected_command_sync_token"] = command_sync_token
        freshness["observed_command_sync_token"] = str(snapshot.get("command_sync_token", "") or "")
        freshness["waited_ms"] = int(waited_ms or 0)
        freshness["stale"] = bool(freshness.get("stale") or not cache_advanced)
        observation["freshness"] = freshness
        out["text_theater"] = observation
        delta = out.get("delta") if isinstance(out.get("delta"), dict) else {}
        delta["text_theater_attached"] = True
        delta["text_theater_waited_ms"] = int(waited_ms or 0)
        delta["text_theater_cache_advanced"] = bool(cache_advanced)
        delta["text_theater_matched_command_sync"] = bool(matched_command_sync)
        out["delta"] = delta
    return out


def _env_help_load_registry() -> dict:
    path = _ENV_HELP_DATA_PATH
    if not path.exists():
        return {
            "error": f"Environment help registry not found at {path.as_posix()}",
            "hint": "Run `node scripts/generate-env-help-registry.js` to build the environment help registry.",
        }
    try:
        stat = path.stat()
        with _env_help_cache_lock:
            cached_mtime = _env_help_cache.get("mtime_ns")
            cached_data = _env_help_cache.get("data")
            if cached_mtime == stat.st_mtime_ns and isinstance(cached_data, dict):
                return cached_data
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                "error": f"Environment help registry is invalid at {path.as_posix()}",
                "hint": "Rebuild the registry with `node scripts/generate-env-help-registry.js`.",
            }
        data = _env_help_apply_registry_overrides(data)
        with _env_help_cache_lock:
            _env_help_cache["mtime_ns"] = stat.st_mtime_ns
            _env_help_cache["data"] = data
        return data
    except Exception as exc:
        return {
            "error": f"Failed to load environment help registry: {exc}",
            "hint": "Rebuild the registry with `node scripts/generate-env-help-registry.js`.",
        }


def _env_help_stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_env_help_stringify(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_env_help_stringify(item) for item in value.values())
    return str(value)


def _env_help_extra_topics() -> dict[str, dict]:
    return {
        "continuity_reacclimation": {
            "tool": "continuity_restore",
            "entry_kind": "resume_playbook",
            "title": "Continuity Reacclimation",
            "category": "observation_query",
            "status": "live",
            "transport": {
                "local_proxy": True,
                "browser_surface": False,
                "ui_local_only": False,
                "implemented_verb": True,
            },
            "target_contract": {
                "shape": "json payload",
                "description": "Use continuity_restore with summary/cwd hints to recover archived operational continuity, then re-open live corroboration surfaces in theater-first order.",
                "examples": [
                    "{\"summary\":\"context compression continuity restore\",\"cwd\":\"D:\\\\End-Game\\\\champion_councl\"}",
                    "{\"summary\":\"surface alignment review rain parity\",\"cwd\":\"D:\\\\End-Game\\\\champion_councl\",\"limit\":1}",
                ],
            },
            "summary": "Recover archive-backed continuity after context compression, then restore the next valid evidence posture through text theater, blackboard, help, and scoped broker surfaces.",
            "when_to_use": [
                "Use this immediately after a context reset, compaction, or long-thread interruption when the real loss is working posture rather than just missing text.",
                "Use this before inventing a fresh plan when a recent rollout already contains the hot files, tools, objective pressure, and last stable answer.",
            ],
            "what_it_changes": [
                "Nothing by itself. continuity_restore is read-only and returns a reacclimation packet over archived session artifacts.",
            ],
            "mode_notes": [
                "Archive continuity is not live truth. Recover sequence first, then reacquire live corroboration through text theater, browser-visible capture, consult/blackboard, snapshot, and only then contracts/env_report.",
                "The continuity packet now carries query_state, resume_focus, and surface_prime metadata so restore can recover posture instead of just a recap.",
                "This topic keeps continuity recovery inside the existing env_help / blackboard / env_report doctrine rather than spinning up a second authority plane.",
            ],
            "verification": [
                "continuity_restore(summary='...', cwd='D:\\\\End-Game\\\\champion_councl')",
                "env_read(query='text_theater_embodiment')",
                "capture_supercam",
                "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
                "env_read(query='text_theater_snapshot')",
                "env_help(topic='env_report')",
            ],
            "gotchas": [
                "continuity_restore does not recover hidden chain-of-thought; it recovers operational continuity from session artifacts.",
                "Do not treat archive continuity as permission to skip the fresh live read order.",
                "If the resumed seam is route/support diagnosis, use env_report only after the fresh theater and snapshot intake is satisfied.",
            ],
            "failure_modes": [
                "No matching session archive found.",
                "Recovered packet is stale because no fresh live corroboration was performed after restore.",
                "Operator treats archive summary as authority instead of using it to seed the next valid reads.",
            ],
            "aliases": [
                "continuity_restore_reacclimation",
                "reacclimation",
                "context_compression_resume",
            ],
            "surface_entrypoints": [],
            "bridges_to": [
                "continuity_restore",
                "shared_state.text_theater",
                "shared_state.blackboard",
                "env_help",
                "env_report",
            ],
            "related_commands": [
                "text_theater_embodiment",
                "text_theater_snapshot",
                "env_report",
                "capture_supercam",
            ],
        },
        "output_state": {
            "tool": "env_read",
            "entry_kind": "derived_surface",
            "title": "Output State",
            "category": "observation_query",
            "status": "live",
            "transport": {
                "local_proxy": True,
                "browser_surface": True,
                "ui_local_only": False,
                "implemented_verb": True,
            },
            "target_contract": {
                "shape": "shared_state.text_theater.snapshot.output_state",
                "description": "Use the derived orienting surface to read current sequence, placement, equilibrium, drift, freshness, and next-read posture without inventing a second authority plane.",
                "examples": [
                    "{\"query\":\"text_theater_snapshot\"}",
                    "{\"query\":\"text_theater_view\",\"view\":\"consult\",\"section\":\"blackboard\",\"diagnostics\":true}",
                    "{\"report_id\":\"paired_state_alignment\"}",
                ],
            },
            "summary": "Read the derived orienting surface that normalizes query posture, equilibrium, drift, freshness, and next reads across blackboard, mirror, docs, and corroboration.",
            "when_to_use": [
                "Use this when you need one compact read of where the system stands right now instead of mentally merging blackboard rows, mirror freshness, docs context, and snapshot posture yourself.",
                "Use this after continuity restore or during route/support diagnosis when the next action should follow the current carried sequence instead of improvising from raw state.",
                "Use this when you need the trajectory correlator to tell you whether the current operations are matching, widening, drifting, or breaking the carried sequence.",
            ],
            "what_it_changes": [
                "Nothing. output_state is read-only and is derived from existing live surfaces.",
            ],
            "mode_notes": [
                "output_state is a crane, not a controller: it orients the read across surfaces but does not replace blackboard, mirror, docs, or runtime authority.",
                "The placement block is the relational summary handle: subject, objective, seam, evidence, drift, and next lanes on one carried surface.",
                "trajectory_correlator interviews the current operation against the intended sequence and gives a smallest honest return path instead of silently letting drift accumulate.",
                "continuity_cue rings the bell when a continuity drill is warranted; it should alert the operator, not secretly mutate the system.",
                "Treat freshness as the current currency gauge for this surface; if freshness is stale or mirror_lag is true, corroborate before escalating conclusions.",
            ],
            "verification": [
                "env_read(query='text_theater_snapshot')",
                "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
                "env_report(report_id='paired_state_alignment')",
            ],
            "gotchas": [
                "output_state summarizes live surfaces; it is not permission to skip the theater-first read order.",
                "If output_state disagrees with visible theater, trust the freshness fields and re-run corroboration before treating it as a contradiction.",
            ],
            "failure_modes": [
                "Sequence is live but placement is empty because the query thread was never seeded.",
                "Freshness is lagged, so the orienting read is behind the current visible runtime.",
                "Consumers expect legacy field names instead of the canonical band/placement contract.",
                "trajectory_correlator can only grade what the live surfaces expose; if receipts or visible_read are absent, it will correctly stay conservative.",
            ],
            "aliases": [
                "derived_orienting_surface",
                "placement_lattice",
                "equilibrium_surface",
                "trajectory_correlator",
                "continuity_cue",
            ],
            "surface_entrypoints": [],
            "bridges_to": [
                "shared_state.output_state",
                "shared_state.text_theater.snapshot.output_state",
                "shared_state.blackboard.working_set.query_thread",
                "env_report",
                "dreamer_state",
            ],
            "related_commands": [
                "text_theater_snapshot",
                "text_theater_view",
                "paired_state_alignment",
                "continuity_reacclimation",
            ],
        },
        "paired_state_alignment": {
            "tool": "env_report",
            "entry_kind": "comparison_report",
            "title": "Paired-State Alignment",
            "category": "observation_query",
            "status": "live",
            "transport": {
                "local_proxy": True,
                "browser_surface": False,
                "ui_local_only": False,
                "implemented_verb": True,
            },
            "target_contract": {
                "shape": "json payload",
                "description": "Use env_report(report_id='paired_state_alignment') after theater-first intake to compare archive continuity posture against the live blackboard query thread.",
                "examples": [
                    "{\"report_id\":\"paired_state_alignment\"}",
                    "{\"report_id\":\"paired_state_alignment\",\"raw_slice\":true}",
                ],
            },
            "summary": "Compare archive query posture and live query posture on one carried sequence without creating a second authority plane.",
            "when_to_use": [
                "Use this after continuity restore when you need to know whether the recovered archive seam still matches the live query thread.",
                "Use this when reset-aware reacclimation needs an explicit drift/freshness classification instead of intuition.",
            ],
            "what_it_changes": [
                "Nothing. paired_state_alignment is a read-only env_report recipe.",
            ],
            "mode_notes": [
                "The archive side seeds the comparison, but the live blackboard query thread remains the live authority.",
                "This report depends on theater-first intake and current text-theater snapshot freshness.",
            ],
            "verification": [
                "continuity_restore(summary='...', cwd='D:\\\\End-Game\\\\champion_councl')",
                "env_read(query='text_theater_embodiment')",
                "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
                "env_read(query='text_theater_snapshot')",
                "env_report(report_id='paired_state_alignment')",
            ],
            "gotchas": [
                "This does not recover hidden chain-of-thought; it compares carried posture fields only.",
                "Do not let the archive side outrank the live blackboard query thread after the comparison is built.",
            ],
            "failure_modes": [
                "No matching archive seam found for the live query thread.",
                "Live mirror is stale, so the pair is not trustworthy yet.",
                "Objective or subject drifted across the reset boundary.",
            ],
            "aliases": [
                "report:paired_state_alignment",
                "paired_state",
                "archive_live_pair",
            ],
            "surface_entrypoints": [],
            "bridges_to": [
                "continuity_restore",
                "shared_state.blackboard",
                "shared_state.text_theater.snapshot",
                "env_report",
            ],
            "related_commands": [
                "continuity_restore",
                "text_theater_embodiment",
                "text_theater_snapshot",
                "env_report",
            ],
        }
    }


def _env_help_search_entries(registry: dict, search_text: str, limit: int = 12) -> list[dict]:
    query = str(search_text or "").strip().lower()
    if not query:
        return []
    query_tokens = [token for token in re.split(r"[^a-z0-9_]+", query) if token]
    rows: list[dict] = []

    def add_rows(kind: str, items: dict | None):
        if not isinstance(items, dict):
            return
        for key, value in items.items():
            if not isinstance(value, dict):
                continue
            haystack = f"{str(key or '')} {_env_help_stringify(value)}".lower().strip()
            if not haystack:
                continue
            score = 0
            if query == str(key).lower():
                score += 120
            if query in str(key).lower():
                score += 80
            if query in str(value.get("title") or "").lower():
                score += 40
            score += haystack.count(query) * 8
            if query_tokens:
                matched_tokens = 0
                for token in query_tokens:
                    if token in haystack:
                        matched_tokens += 1
                        score += 12
                        if token == str(key).lower():
                            score += 20
                if matched_tokens == len(query_tokens):
                    score += 30
                elif matched_tokens > 0:
                    score += matched_tokens * 4
            if score <= 0:
                continue
            rows.append({
                "kind": kind,
                "id": str(key),
                "title": str(value.get("title") or key),
                "summary": str(value.get("summary") or value.get("description") or ""),
                "score": score,
            })

    add_rows("command", registry.get("commands"))
    add_rows("query", registry.get("queries"))
    add_rows("family", registry.get("families"))
    add_rows("playbook", registry.get("playbooks"))
    rows.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("kind", "")), str(item.get("id", ""))))
    return rows[: max(1, int(limit or 12))]


def _env_help_index_payload(registry: dict, normalized_args: dict) -> dict:
    commands = registry.get("commands") if isinstance(registry.get("commands"), dict) else {}
    queries = registry.get("queries") if isinstance(registry.get("queries"), dict) else {}
    families = registry.get("families") if isinstance(registry.get("families"), dict) else {}
    playbooks = registry.get("playbooks") if isinstance(registry.get("playbooks"), dict) else {}
    builtin_topics = dict(_env_help_builtin_topics())
    builtin_topics.update(_env_help_extra_topics())
    ui_action_count = sum(1 for value in commands.values() if isinstance(value, dict) and str(value.get("entry_kind") or "") == "ui_action")
    env_command_count = max(0, len(commands) - ui_action_count)
    family_rows = []
    for key, value in sorted(families.items()):
        if not isinstance(value, dict):
            continue
        family_rows.append({
            "category": key,
            "title": str(value.get("title") or key),
            "count": int(value.get("count") or 0),
            "description": str(value.get("description") or ""),
        })
    playbook_rows = []
    for key, value in sorted(playbooks.items()):
        if not isinstance(value, dict):
            continue
        playbook_rows.append({
            "id": key,
            "title": str(value.get("title") or key),
            "step_count": len(value.get("steps") or []) if isinstance(value.get("steps"), list) else 0,
        })
    return {
        "tool": "env_help",
        "category": "environment",
        "purpose": "Query the generated environment/browser command registry, command families, and operator playbooks.",
        "status": "ok",
        "summary": "Read environment help index",
        "normalized_args": normalized_args,
        "operation": "env_help",
        "operation_status": "ok",
        "entry_type": "index",
        "index": {
            "meta": registry.get("meta") if isinstance(registry.get("meta"), dict) else {},
            "families": family_rows,
            "playbooks": playbook_rows,
            "entry_count": len(commands) + len(queries) + len(builtin_topics),
            "query_count": len(queries),
            "tool_topic_count": len(builtin_topics),
            "env_command_count": env_command_count,
            "ui_action_count": ui_action_count,
            "cold_start": {
                "summary": "Cold agents should learn the local environment registry through env_help itself before guessing commands or falling back to reset advice.",
                "sequence": [
                    "env_help(topic='env_help')",
                    "env_help(topic='index')",
                    "env_help(topic='output_state')",
                    "env_help(topic='env_report')",
                    "env_help(topic='continuity_reacclimation')",
                    "env_help(category='builder_motion') or env_help(search='mounted asset floor')",
                ],
                "capsule_bridge": [
                    "Capsule get_help('environment') is the umbrella help view.",
                    "env_help(...) is the richer server-local registry for environment/browser/runtime surfaces.",
                    "If you only read get_help('environment') and never query env_help(...), you can miss live local topics, aliases, and sequencing guidance.",
                ],
            },
            "examples": [
                "env_help(topic='env_help')",
                "env_help(topic='index')",
                "env_help(topic='output_state')",
                "env_help(topic='env_report')",
                "env_help(topic='dreamer_control_plane')",
                "env_help(topic='dreamer_mechanics_obs')",
                "env_help(topic='continuity_reacclimation')",
                "env_help(topic='workbench_set_timeline_cursor')",
                "env_help(topic='workbench_stage_contact')",
                "env_help(topic='workbench-toggle-turntable')",
                "env_help(topic='text_theater_embodiment')",
                "env_help(topic='playbook:theater_first_route_diagnosis')",
                "env_help(category='builder_motion')",
                "env_help(topic='capture_time_strip')",
                "env_help(search='mounted asset floor')",
            ],
        },
    }


def _get_help_environment_bridge_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    topic = str(args.get("topic", "") or "").strip().lower()
    if topic not in ("environment", "env_help", "environment_help", "help:environment", "help:env_help"):
        return None
    return {
        "tool": "get_help",
        "status": "ok",
        "summary": "Read environment help bridge",
        "normalized_args": {
            "topic": str(args.get("topic", "") or ""),
        },
        "operation": "get_help",
        "operation_status": "ok",
        "entry_type": "bridge",
        "bridge_help": {
            "title": "Environment Help Bridge",
            "summary": "Capsule get_help('environment') is the umbrella help surface. Use env_help(...) to query the richer local environment/browser/runtime registry exposed by this server.",
            "why_this_exists": [
                "Cold agents often find the capsule environment category but miss the richer local env_help registry.",
                "The local env_help registry carries server-side builtin topics, aliases, playbooks, and sequencing guidance that are not guaranteed to exist in the capsule help registry.",
            ],
            "next_calls": [
                "env_help(topic='env_help')",
                "env_help(topic='index')",
                "env_help(topic='output_state')",
                "env_help(topic='env_report')",
                "env_help(topic='continuity_reacclimation')",
            ],
            "gotchas": [
                "Do not stop at get_help('environment') if the task is environment/browser/runtime-specific.",
                "get_help('env_help') may be absent in the capsule help registry; env_help(topic='env_help') is the local self-documenting entrypoint.",
            ],
        },
    }


def _env_help_local_proxy_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    topic = str(args.get("topic", "") or args.get("command", "") or "").strip()
    search = str(args.get("search", "") or "").strip()
    category = str(args.get("category", "") or "").strip()
    registry = _env_help_load_registry()
    if not isinstance(registry, dict):
        return None
    if registry.get("error"):
        return {
            "tool": "env_help",
            "status": "error",
            "summary": str(registry.get("error") or "Environment help unavailable"),
            "normalized_args": {
                "topic": topic,
                "search": search,
                "category": category,
            },
            "operation": "env_help",
            "operation_status": "error",
            "error": str(registry.get("error") or "Environment help unavailable"),
            "hint": str(registry.get("hint") or ""),
        }
    commands = registry.get("commands") if isinstance(registry.get("commands"), dict) else {}
    queries = registry.get("queries") if isinstance(registry.get("queries"), dict) else {}
    families = registry.get("families") if isinstance(registry.get("families"), dict) else {}
    playbooks = registry.get("playbooks") if isinstance(registry.get("playbooks"), dict) else {}
    builtin_topics = dict(_env_help_builtin_topics())
    builtin_topics.update(_env_help_extra_topics())
    builtin_topic_aliases = {
        "environment_help": "env_help",
        "help:environment": "env_help",
        "help:env_help": "env_help",
        "envhelp": "env_help",
        "environment": "env_help",
        "continuity_restore_reacclimation": "continuity_reacclimation",
        "reacclimation": "continuity_reacclimation",
        "context_compression_resume": "continuity_reacclimation",
    }
    alias_map: dict[str, str] = {}
    for key, value in commands.items():
        if not isinstance(value, dict):
            continue
        for alias in value.get("aliases") or []:
            alias_key = str(alias or "").strip()
            if alias_key and alias_key not in alias_map:
                alias_map[alias_key] = str(key)
        for alias in value.get("surface_entrypoints") or []:
            alias_key = str(alias or "").strip()
            if alias_key and alias_key not in alias_map:
                alias_map[alias_key] = str(key)
    normalized_args = {
        "topic": topic,
        "search": search,
        "category": category,
    }
    if topic in builtin_topic_aliases:
        topic = builtin_topic_aliases.get(topic) or topic
        normalized_args["topic"] = topic
    retired_topics = {
        "workbench_apply_motion_preset": {
            "title": "Retired Motion Preset Command",
            "status": "retired",
            "summary": "Removed from the current runtime surface when the motion-preset lane was deleted from the rebuild baseline.",
            "why_retired": [
                "The current builder/runtime lane no longer exposes motion preset application as a live command surface.",
                "Current motion authoring truth lives in explicit pose, timeline, and authored clip surfaces instead."
            ],
            "replacement_topics": [
                "workbench_set_pose",
                "workbench_set_timeline_cursor",
                "workbench_compile_clip",
                "workbench_play_authored_clip",
                "capture_time_strip"
            ],
        },
        "playbook:motion_preset_validation": {
            "title": "Retired Motion Preset Validation Playbook",
            "status": "retired",
            "summary": "Retired with the motion-preset lane removal. Use explicit builder authoring and capture validation instead of preset playback checks.",
            "why_retired": [
                "The motion-preset validation path no longer matches the current runtime surface.",
                "Validation should now target explicit pose/timeline/clip authoring plus mirrored shared-state and capture corroboration."
            ],
            "replacement_topics": [
                "workbench_set_pose",
                "workbench_set_timeline_cursor",
                "workbench_compile_clip",
                "workbench_play_authored_clip",
                "builder_helper_strip_review"
            ],
        },
        "motion_preset_validation": {
            "title": "Retired Motion Preset Validation Playbook",
            "status": "retired",
            "summary": "Retired with the motion-preset lane removal. Use explicit builder authoring and capture validation instead of preset playback checks.",
            "why_retired": [
                "The motion-preset validation path no longer matches the current runtime surface.",
                "Validation should now target explicit pose/timeline/clip authoring plus mirrored shared-state and capture corroboration."
            ],
            "replacement_topics": [
                "workbench_set_pose",
                "workbench_set_timeline_cursor",
                "workbench_compile_clip",
                "workbench_play_authored_clip",
                "builder_helper_strip_review"
            ],
        },
        "workbench_preview_settle": {
            "title": "Retired Builder Settle Preview Command",
            "status": "retired",
            "summary": "Removed on 2026-04-10 when the settle workflow was deleted from the rebuild baseline.",
            "why_retired": [
                "Settle was removed as a first-class builder workflow because it kept fighting manual pose editing and added more friction than value.",
                "The underlying balance/load/support substrate remains; future recovery behavior will return later as a runtime controller, not as settle preview/commit."
            ],
            "replacement_topics": [
                "workbench_assert_balance",
                "workbench_set_pose",
                "workbench_set_timeline_cursor",
                "workbench_compile_clip",
                "capture_time_strip"
            ],
        },
        "workbench_commit_settle": {
            "title": "Retired Builder Settle Commit Command",
            "status": "retired",
            "summary": "Removed on 2026-04-10 with the rest of the settle workflow.",
            "why_retired": [
                "The settle preview/commit authoring path was deleted instead of patched.",
                "Future rebalance, stumble, brace, and fall behavior will be rebuilt later as runtime movement logic that consumes the same balance substrate."
            ],
            "replacement_topics": [
                "workbench_assert_balance",
                "workbench_compile_clip",
                "capture_time_strip",
                "text_theater_snapshot"
            ],
        },
    }
    topic_key = topic.lower()
    if not topic and not search and not category:
        return _env_help_index_payload(registry, normalized_args)
    if topic_key in ("index", "overview", "help"):
        return _env_help_index_payload(registry, normalized_args)
    if topic in retired_topics:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read retired environment help topic {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "retired",
            "retired_help": retired_topics.get(topic),
        }
    if topic in builtin_topics:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help for tool {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "tool",
            "tool_help": builtin_topics.get(topic),
        }
    if topic in ("route_stability_diagnosis", "report:route_stability_diagnosis"):
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": "Read environment help for tool env_report via recipe alias",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "tool",
            "resolved_from_alias": topic,
            "tool_help": builtin_topics.get("env_report"),
        }
    if category and category in families:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help family {category}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "family",
            "family": families.get(category),
        }
    if topic.startswith("playbook:"):
        playbook_id = topic.split(":", 1)[1].strip()
        if playbook_id in playbooks:
            return {
                "tool": "env_help",
                "status": "ok",
                "summary": f"Read environment help playbook {playbook_id}",
                "normalized_args": normalized_args,
                "operation": "env_help",
                "operation_status": "ok",
                "entry_type": "playbook",
                "playbook": playbooks.get(playbook_id),
            }
    if topic in commands:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help for command {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "command",
            "command_help": commands.get(topic),
        }
    if topic in queries:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help for query {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "query",
            "query_help": queries.get(topic),
        }
    if topic in alias_map and alias_map.get(topic) in commands:
        resolved_key = alias_map.get(topic)
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help for command {resolved_key} via alias {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "command",
            "resolved_from_alias": topic,
            "command_help": commands.get(resolved_key),
        }
    if topic in families:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help family {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "family",
            "family": families.get(topic),
        }
    if topic in playbooks:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help playbook {topic}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "playbook",
            "playbook": playbooks.get(topic),
        }
    search_text = search or topic
    results = _env_help_search_entries(registry, search_text)
    builtin_results: list[dict] = []
    search_terms = [term for term in str(search_text or "").lower().split() if term]
    for key, value in builtin_topics.items():
        haystack = f"{str(key or '')} {_env_help_stringify(value)}".lower().strip()
        if search_terms and all(term in haystack for term in search_terms):
            builtin_results.append({
                "id": key,
                "title": str(value.get("title") or key),
                "entry_type": "tool",
                "summary": str(value.get("summary") or ""),
            })
    if builtin_results:
        results = builtin_results + results
    if results:
        return {
            "tool": "env_help",
            "status": "ok",
            "summary": f"Read environment help search results for {search_text}",
            "normalized_args": normalized_args,
            "operation": "env_help",
            "operation_status": "ok",
            "entry_type": "search",
            "results": results,
        }
    return {
        "tool": "env_help",
        "status": "partial",
        "summary": f"No environment help found for {topic or search or category}",
        "normalized_args": normalized_args,
        "operation": "env_help",
        "operation_status": "partial",
        "error": f"No environment help found for '{topic or search or category}'",
        "hint": "Try topic='env_report', topic='index', category='builder_motion', or search='mounted asset floor'.",
    }


def _env_capture_safe_token(text: str) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text or ""))
    token = token.strip("_")
    return token[:48] or "capture"


def _env_capture_ensure_dir() -> Path:
    _ENV_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    return _ENV_CAPTURE_DIR


def _env_capture_entry_files(value) -> list[str]:
    files: list[str] = []
    if isinstance(value, dict):
        file_path = value.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            files.append(file_path.strip())
        for child in value.values():
            files.extend(_env_capture_entry_files(child))
    elif isinstance(value, list):
        for child in value:
            files.extend(_env_capture_entry_files(child))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in files:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _env_capture_delete_files(entry: dict | None) -> None:
    for file_path in _env_capture_entry_files(entry or {}):
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
        except Exception:
            pass


def _env_capture_save_index() -> None:
    _env_capture_ensure_dir()
    with _env_capture_lock:
        snapshot = json.loads(json.dumps(_env_capture_history, default=str))
    _ENV_CAPTURE_INDEX_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _env_capture_load_index() -> None:
    global _env_capture_history
    try:
        if not _ENV_CAPTURE_INDEX_PATH.exists():
            return
        data = json.loads(_ENV_CAPTURE_INDEX_PATH.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else []
        cleaned = [row for row in rows if isinstance(row, dict)]
        with _env_capture_lock:
            _env_capture_history = cleaned[-_ENV_CAPTURE_LIMIT:]
    except Exception:
        _env_capture_history = []


def _save_b64_jpeg(data_url: str, path: Path) -> None:
    raw = str(data_url or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    path.write_bytes(base64.b64decode(raw))


def _env_capture_materialize(value, prefix: str, ts: int, files_saved: list[str]):
    if isinstance(value, dict):
        out: dict = {}
        image_b64 = value.get("image_b64")
        if isinstance(image_b64, str) and image_b64.strip():
            filename = f"{_env_capture_safe_token(prefix)}_{ts}.jpg"
            path = (_env_capture_ensure_dir() / filename).resolve()
            _save_b64_jpeg(image_b64, path)
            files_saved.append(str(path))
            out["file_path"] = str(path)
            out["file_url"] = f"/static/captures/{path.name}"
        for key, child in value.items():
            if key == "image_b64":
                continue
            child_prefix = f"{prefix}_{_env_capture_safe_token(key)}"
            out[key] = _env_capture_materialize(child, child_prefix, ts, files_saved)
        return out
    if isinstance(value, list):
        rows = []
        for idx, child in enumerate(value):
            rows.append(_env_capture_materialize(child, f"{prefix}_{idx}", ts, files_saved))
        return rows
    return value


def _env_capture_append(capture_type: str, result: dict) -> dict:
    ts = int(time.time() * 1000)
    files_saved: list[str] = []
    safe_type = _env_capture_safe_token(capture_type or "frame")
    materialized = _env_capture_materialize(
        json.loads(json.dumps(result or {}, default=str)),
        safe_type,
        ts,
        files_saved,
    )
    entry = {
        "type": safe_type,
        "ts": ts,
        "result": materialized,
    }
    with _env_capture_lock:
        _env_capture_history.append(entry)
        while len(_env_capture_history) > _ENV_CAPTURE_LIMIT:
            old = _env_capture_history.pop(0)
            _env_capture_delete_files(old)
    _env_capture_save_index()
    return {
        "status": "ok",
        "type": safe_type,
        "ts": ts,
        "files": files_saved,
        "capture": entry,
    }


def _env_capture_latest(capture_type: str) -> dict | None:
    target = _env_capture_safe_token(capture_type or "frame")
    with _env_capture_lock:
        for entry in reversed(_env_capture_history):
            if isinstance(entry, dict) and str(entry.get("type") or "") == target:
                return json.loads(json.dumps(entry, default=str))
    return None


def _env_capture_recent(capture_type: str, limit: int = 2) -> list[dict]:
    target = _env_capture_safe_token(capture_type or "frame")
    limit = max(1, min(10, int(limit or 2)))
    rows: list[dict] = []
    with _env_capture_lock:
        for entry in reversed(_env_capture_history):
            if isinstance(entry, dict) and str(entry.get("type") or "") == target:
                rows.append(json.loads(json.dumps(entry, default=str)))
                if len(rows) >= limit:
                    break
    return rows


def _env_projection_lookup(result: dict | None) -> dict[tuple[str, str], dict]:
    lookup: dict[tuple[str, str], dict] = {}
    if not isinstance(result, dict):
        return lookup
    for tile in result.get("tiles") or []:
        if not isinstance(tile, dict):
            continue
        label = str(tile.get("label") or "")
        observation = tile.get("observation") if isinstance(tile.get("observation"), dict) else {}
        for proj in observation.get("projections") or []:
            if not isinstance(proj, dict):
                continue
            object_key = str(proj.get("object_key") or "")
            if not object_key:
                continue
            lookup[(label, object_key)] = proj
    return lookup


def _debug_activity_detail(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return ""
    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    detail = str(args.get("detail") or result.get("message") or "").strip()
    return detail


def _is_debug_activity_entry(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("source") == "agent-debug" or entry.get("tool") == "agent_debug":
        return True
    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    detail = _debug_activity_detail(entry)
    if re.match(r"^debug\b", detail, re.IGNORECASE):
        return True
    signal_type = str(args.get("signal_type") or "").lower()
    if "agent_debug" in signal_type:
        return True
    reason = str(args.get("reason") or "").lower()
    if "agent_debug" in reason:
        return True
    event_type = str(args.get("event_type") or "").lower()
    if "agent_debug" in event_type:
        return True
    return False


def _debug_state_payload(query_text: str) -> dict:
    with _activity_log_lock:
        try:
            activity_rows = json.loads(json.dumps(_activity_log, default=str))
        except Exception:
            activity_rows = list(_activity_log)
    debug_rows = [entry for entry in activity_rows if _is_debug_activity_entry(entry)]
    recent_rows = debug_rows[-15:]
    mirrored_rows = 0
    loop_rows = 0
    error_rows = 0
    source_counts: dict[str, int] = {}
    for entry in debug_rows:
        args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
        source = str(entry.get("source") or "unknown")
        source_counts[source] = int(source_counts.get(source, 0)) + 1
        if args.get("mirror") is not None:
            mirrored_rows += 1
        else:
            loop_rows += 1
        if entry.get("error"):
            error_rows += 1
    compact_rows = []
    for entry in reversed(recent_rows):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
        mirror = args.get("mirror") if isinstance(args.get("mirror"), dict) else {}
        compact_rows.append({
            "id": str(entry.get("id") or ""),
            "tool": str(entry.get("tool") or ""),
            "source": str(entry.get("source") or ""),
            "client_id": str(entry.get("clientId") or ""),
            "timestamp_ms": _coerce_int(entry.get("timestamp"), 0),
            "duration_ms": _coerce_int(entry.get("durationMs"), 0),
            "error": entry.get("error"),
            "detail": _debug_activity_detail(entry),
            "signal_type": str(args.get("signal_type") or ""),
            "has_mirror_payload": bool(mirror),
            "mirrored_tool": str(mirror.get("tool") or ""),
            "mirrored_source": str(mirror.get("source") or ""),
        })
    latest_row = compact_rows[0] if compact_rows else None
    debug_state = {
        "mirror": {
            "enabled": bool(_DEBUG_FEED_MIRROR_ENABLED),
            "max_chars": int(_DEBUG_FEED_MIRROR_MAX_CHARS),
            "excluded_tools": sorted(_DEBUG_FEED_MIRROR_EXCLUDED_TOOLS),
        },
        "counts": {
            "activity_rows_total": len(activity_rows),
            "debug_rows_total": len(debug_rows),
            "mirrored_tool_rows": mirrored_rows,
            "agent_loop_rows": loop_rows,
            "error_rows": error_rows,
            "sse_subscribers": len(_activity_subscribers),
            "source_counts": source_counts,
        },
        "latest": latest_row,
        "recent_rows": compact_rows,
        "guidance": {
            "default_path": [
                "trigger the real tool/action",
                "read env_read(query='live'|'shared_state'|'contracts'|'habitat_objects')",
                "read feed(n=...)",
                "use the Debug tab as a filtered browser surface rather than the sole source of truth",
            ],
            "notes": [
                "trace_root_causes mutates the default causal graph when given a free-form description",
                "get_help('debug') is not currently exposed by the capsule help registry",
                "debug_state is a local env_read summary over the existing activity/debug mirror",
            ],
        },
    }
    return {
        "tool": "env_read",
        "status": "ok",
        "summary": "Read local debug state summary",
        "normalized_args": {"query": query_text},
        "delta": {
            "found": True,
            "type": "debug_state",
            "debug_rows": len(debug_rows),
            "mirrored_tool_rows": mirrored_rows,
            "agent_loop_rows": loop_rows,
        },
        "operation": "env_read",
        "operation_status": "ok",
        "query": query_text,
        "debug_state": debug_state,
    }


def _env_probe_compare_payload() -> dict:
    rows = _env_capture_recent("probe", 2)
    latest = rows[0] if rows else None
    previous = rows[1] if len(rows) > 1 else None
    if latest is None:
        return {
            "tool": "env_read",
            "status": "partial",
            "summary": "No probe capture is available yet",
            "normalized_args": {"query": "probe_compare"},
            "delta": {"found": False},
            "operation": "env_read",
            "operation_status": "partial",
            "query": "probe_compare",
            "probe_compare": None,
        }
    latest_result = latest.get("result") if isinstance(latest.get("result"), dict) else {}
    previous_result = previous.get("result") if isinstance(previous, dict) and isinstance(previous.get("result"), dict) else {}
    latest_target = latest_result.get("target") if isinstance(latest_result.get("target"), dict) else {}
    previous_target = previous_result.get("target") if isinstance(previous_result.get("target"), dict) else {}
    latest_key = str(latest_target.get("object_key") or "")
    previous_key = str(previous_target.get("object_key") or "")
    latest_neighbors = {str(item.get("object_key") or "") for item in (latest_result.get("neighbors") or []) if isinstance(item, dict)}
    previous_neighbors = {str(item.get("object_key") or "") for item in (previous_result.get("neighbors") or []) if isinstance(item, dict)}
    latest_lookup = _env_projection_lookup(latest_result)
    previous_lookup = _env_projection_lookup(previous_result)
    tile_deltas: list[dict] = []
    if latest_key and latest_key == previous_key:
        for (label, object_key), latest_proj in latest_lookup.items():
            if object_key != latest_key:
                continue
            previous_proj = previous_lookup.get((label, object_key))
            if not isinstance(previous_proj, dict):
                continue
            latest_screen = latest_proj.get("screen") if isinstance(latest_proj.get("screen"), dict) else {}
            previous_screen = previous_proj.get("screen") if isinstance(previous_proj.get("screen"), dict) else {}
            try:
                dx = float(latest_screen.get("x", 0)) - float(previous_screen.get("x", 0))
                dy = float(latest_screen.get("y", 0)) - float(previous_screen.get("y", 0))
                depth_delta = float(latest_screen.get("depth", 0)) - float(previous_screen.get("depth", 0))
            except Exception:
                continue
            tile_deltas.append({
                "label": label,
                "dx": round(dx, 2),
                "dy": round(dy, 2),
                "depth_delta": round(depth_delta, 4),
            })
    latest_pos = latest_target.get("position") if isinstance(latest_target.get("position"), dict) else {}
    previous_pos = previous_target.get("position") if isinstance(previous_target.get("position"), dict) else {}
    world_delta = None
    if latest_key and latest_key == previous_key and latest_pos and previous_pos:
        try:
            world_delta = {
                "dx": round(float(latest_pos.get("x", 0)) - float(previous_pos.get("x", 0)), 4),
                "dy": round(float(latest_pos.get("y", 0)) - float(previous_pos.get("y", 0)), 4),
                "dz": round(float(latest_pos.get("z", 0)) - float(previous_pos.get("z", 0)), 4),
            }
        except Exception:
            world_delta = None
    compare = {
        "latest_ts": latest.get("ts"),
        "previous_ts": previous.get("ts") if previous else None,
        "latest_target_key": latest_key,
        "previous_target_key": previous_key or None,
        "same_target": bool(latest_key and latest_key == previous_key),
        "world_delta": world_delta,
        "tile_deltas": tile_deltas,
        "neighbor_added": sorted(key for key in latest_neighbors if key and key not in previous_neighbors),
        "neighbor_removed": sorted(key for key in previous_neighbors if key and key not in latest_neighbors),
        "latest": latest,
        "previous": previous,
    }
    return {
        "tool": "env_read",
        "status": "ok",
        "summary": "Read latest probe comparison",
        "normalized_args": {"query": "probe_compare"},
        "delta": {"found": True, "type": "probe_compare", "same_target": compare["same_target"]},
        "operation": "env_read",
        "operation_status": "ok",
        "query": "probe_compare",
        "probe_compare": compare,
        "capture": latest,
    }


def _env_sync_live_params_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    if str(args.get("operation", "") or "").strip().lower() != "sync_live":
        return None
    params_raw = args.get("params")
    params_obj = {}
    if isinstance(params_raw, dict):
        params_obj = params_raw
    elif isinstance(params_raw, str):
        try:
            parsed = json.loads(params_raw)
            if isinstance(parsed, dict):
                params_obj = parsed
        except Exception:
            params_obj = {}
    payload = params_obj.get("payload")
    return payload if isinstance(payload, dict) else None


def _env_merge_json(base, patch):
    if not isinstance(patch, dict):
        return _json_clone(patch)
    seed = base if isinstance(base, dict) else {}
    out = _json_clone(seed) if seed is not None else {}
    if not isinstance(out, dict):
        out = {}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _env_merge_json(out.get(key), value)
        else:
            out[key] = _json_clone(value)
    return out


def _env_live_cache_store(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    live_state = _json_clone(payload) if payload is not None else None
    if not isinstance(live_state, dict):
        return None
    with _env_live_cache_lock:
        current = _env_live_cache.get("live_state")
        is_camera_partial = bool(live_state.get("partial")) and str(live_state.get("partial_kind") or "").strip().lower() == "camera3d"
        incoming_sync = 0
        current_sync = 0
        try:
            incoming_sync = int((((live_state.get("shared_state") or {}).get("live_sync") or {}).get("camera_pulse_seq")) or 0)
        except Exception:
            incoming_sync = 0
        try:
            current_sync = int((((current or {}).get("shared_state") or {}).get("live_sync") or {}).get("camera_pulse_seq")) or 0
        except Exception:
            current_sync = 0
        if is_camera_partial and current_sync > 0 and incoming_sync > 0 and incoming_sync <= current_sync:
            return {
                "live_state": _json_clone(current) if isinstance(current, dict) else {},
                "updated_ms": int(_env_live_cache.get("updated_ms") or 0),
            }
        merged_state = _env_merge_json(current if isinstance(current, dict) else {}, live_state)
        if not isinstance(merged_state, dict):
            return None
        merged_state["synced_at"] = float(time.time())
        record = {
            "live_state": merged_state,
            "updated_ms": int(time.time() * 1000),
        }
        _env_live_cache["live_state"] = record["live_state"]
        _env_live_cache["updated_ms"] = record["updated_ms"]
    return _json_clone(record)


def _env_live_cache_snapshot() -> dict | None:
    with _env_live_cache_lock:
        live_state = _env_live_cache.get("live_state")
        updated_ms = _env_live_cache.get("updated_ms", 0)
        if not isinstance(live_state, dict):
            return None
        return {
            "live_state": _json_clone(live_state),
            "updated_ms": int(updated_ms or 0),
        }


def _env_persist_local_proxy_payload(args: dict | None = None) -> dict | None:
    payload = _env_sync_live_params_payload(args)
    if not isinstance(payload, dict):
        return None
    cached = _env_live_cache_store(payload)
    response = {
        "tool": "env_persist",
        "status": "ok",
        "summary": "Updated server-local live mirror cache",
        "normalized_args": {"operation": "sync_live"},
        "delta": {
            "updated": True,
            "source": "server_live_cache",
            "updated_ms": (cached or {}).get("updated_ms", 0),
        },
        "operation": "env_persist",
        "operation_status": "ok",
    }
    if isinstance(payload.get("shared_state"), dict):
        response["shared_state"] = _json_clone(payload.get("shared_state"))
    if isinstance(payload.get("render_truth"), dict):
        response["render_truth"] = _json_clone(payload.get("render_truth"))
    if isinstance(payload.get("layout_snapshot"), dict):
        response["layout_snapshot"] = _json_clone(payload.get("layout_snapshot"))
    if payload.get("latest_capture") is not None:
        response["latest_capture"] = _json_clone(payload.get("latest_capture"))
    if payload.get("contracts") is not None:
        response["contracts"] = _json_clone(payload.get("contracts"))
    if payload.get("habitat_objects") is not None:
        response["habitat_objects"] = _json_clone(payload.get("habitat_objects"))
    return response


def _env_read_live_cache_payload(query_text: str) -> dict | None:
    query_lower = str(query_text or "").strip().lower()
    if query_lower not in {
        "live",
        "live_sync",
        "shared_state",
        "contracts",
        "habitat_objects",
        "text_theater_snapshot",
        "text_theater",
        "text_theater_embodiment",
    }:
        return None
    cached = _env_live_cache_snapshot()
    live_state = (cached or {}).get("live_state") if isinstance(cached, dict) else None
    if not isinstance(live_state, dict):
        return None
    shared_state = live_state.get("shared_state") if isinstance(live_state.get("shared_state"), dict) else {}
    text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
    prereq_payload = _env_shared_state_prereq_payload(query_text, cached)
    if prereq_payload is not None:
        return prereq_payload
    if query_lower == "live_sync":
        live_sync = shared_state.get("live_sync")
        if not isinstance(live_sync, dict):
            return None
        return {
            "tool": "env_read",
            "status": "ok",
            "summary": "Read live_sync from server live cache",
            "normalized_args": {"query": query_text},
            "delta": {"found": True, "type": "live_sync", "updated_ms": (cached or {}).get("updated_ms", 0)},
            "operation": "env_read",
            "operation_status": "ok",
            "query": query_text,
            "live_sync": _json_clone(live_sync),
        }
    field_map = {
        "text_theater_snapshot": "snapshot",
        "text_theater": "theater",
        "text_theater_embodiment": "embodiment",
    }
    if query_lower in field_map:
        value = text_theater.get(field_map[query_lower])
        rendered_snapshot = None
        rendered_theater = None
        rendered_embodiment = None
        try:
            if isinstance(shared_state, dict) and shared_state:
                module = _load_text_theater_module()
                rendered = module.render_text_theater_shared_state(
                    shared_state=shared_state,
                    synced_at=live_state.get("synced_at"),
                    view_mode="split",
                    width=140,
                    height=44,
                    diagnostics_visible=False,
                    section_key="theater",
                )
                rendered_snapshot = rendered.get("snapshot") if isinstance(rendered.get("snapshot"), dict) else None
                rendered_theater = str(rendered.get("theater_text") or "") if rendered.get("theater_text") is not None else None
                rendered_embodiment = str(rendered.get("embodiment_text") or "") if rendered.get("embodiment_text") is not None else None
        except Exception:
            rendered_snapshot = None
            rendered_theater = None
            rendered_embodiment = None
        if query_lower == "text_theater_snapshot" and isinstance(rendered_snapshot, dict) and rendered_snapshot:
            value = rendered_snapshot
        elif query_lower == "text_theater" and isinstance(rendered_theater, str) and rendered_theater:
            value = rendered_theater
        elif query_lower == "text_theater_embodiment" and isinstance(rendered_embodiment, str) and rendered_embodiment:
            value = rendered_embodiment
        if value in (None, "", {}):
            return None
        gate_snapshot = rendered_snapshot if isinstance(rendered_snapshot, dict) and rendered_snapshot else _env_cached_text_theater_snapshot(cached)
        _env_note_text_theater_read(query_lower, cached, gate_snapshot)
        return {
            "tool": "env_read",
            "status": "ok",
            "summary": f"Read {query_lower} from server live cache",
            "normalized_args": {"query": query_text},
            "delta": {"found": True, "type": query_lower, "updated_ms": (cached or {}).get("updated_ms", 0)},
            "operation": "env_read",
            "operation_status": "ok",
            "query": query_text,
            query_lower: _json_clone(value),
        }
    payload = {
        "tool": "env_read",
        "status": "ok",
        "summary": f"Read {query_lower} from server live cache",
        "normalized_args": {"query": query_text},
        "delta": {"found": True, "type": query_lower, "updated_ms": (cached or {}).get("updated_ms", 0)},
        "operation": "env_read",
        "operation_status": "ok",
        "query": query_text,
    }
    if query_lower == "live":
        payload["live_state"] = _json_clone(live_state)
    elif query_lower == "shared_state":
        payload["shared_state"] = _json_clone(shared_state)
    elif query_lower == "contracts":
        payload["contracts"] = live_state.get("contracts") or {}
    elif query_lower == "habitat_objects":
        payload["habitat_objects"] = live_state.get("habitat_objects") or []
    return payload


def _load_text_theater_module():
    global _text_theater_module, _text_theater_module_mtime_ns
    module_path = Path(__file__).resolve().parent / "scripts" / "text_theater.py"
    try:
        module_mtime_ns = module_path.stat().st_mtime_ns
    except OSError:
        module_mtime_ns = None
    if _text_theater_module is not None and _text_theater_module_mtime_ns == module_mtime_ns:
        return _text_theater_module
    with _text_theater_module_lock:
        if _text_theater_module is not None and _text_theater_module_mtime_ns == module_mtime_ns:
            return _text_theater_module
        spec = importlib.util.spec_from_file_location("champion_text_theater", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load text theater module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _text_theater_module = module
        _text_theater_module_mtime_ns = module_mtime_ns
        return module


def _env_text_theater_view_payload(args: dict | None = None) -> dict:
    args = args or {}
    query_text = str(args.get("query", "text_theater_view") or "text_theater_view").strip() or "text_theater_view"
    query_lower = query_text.lower()
    alias_defaults = {}
    if query_lower in {"text_theater_blackboard", "text_theater_query_work"}:
        alias_defaults = {
            "view": "consult",
            "section": "blackboard",
            "diagnostics": True,
        }
    view_mode = str(args.get("view", alias_defaults.get("view", "consult")) or "consult").strip().lower() or "consult"
    section_key = str(args.get("section", alias_defaults.get("section", "theater")) or "theater").strip().lower() or "theater"
    try:
        width = max(80, int(args.get("width", 140) or 140))
    except Exception:
        width = 140
    try:
        height = max(24, int(args.get("height", 44) or 44))
    except Exception:
        height = 44
    try:
        timeout = max(0.5, float(args.get("timeout", 5.0) or 5.0))
    except Exception:
        timeout = 5.0
    diagnostics_value = args.get("diagnostics", alias_defaults.get("diagnostics", False))
    diagnostics = diagnostics_value if isinstance(diagnostics_value, bool) else str(diagnostics_value or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        cached = _env_live_cache_snapshot()
        live_state = (cached or {}).get("live_state") if isinstance(cached, dict) else None
        shared_state = live_state.get("shared_state") if isinstance((live_state or {}).get("shared_state"), dict) else None
        if not isinstance(shared_state, dict):
            raise RuntimeError("No shared_state available in live cache")
        module = _load_text_theater_module()
        rendered = module.render_text_theater_shared_state(
            shared_state=shared_state,
            synced_at=(live_state or {}).get("synced_at"),
            view_mode=view_mode,
            width=width,
            height=height,
            diagnostics_visible=diagnostics,
            section_key=section_key,
        )
    except Exception as exc:
        return {
            "tool": "env_read",
            "status": "error",
            "summary": "Failed to render on-demand text theater view",
            "normalized_args": {"query": query_text, "view": view_mode, "section": section_key, "width": width, "height": height},
            "delta": {"found": False},
            "operation": "env_read",
            "operation_status": "error",
            "query": query_text,
            "error": str(exc),
            "text_theater_view": None,
        }
    snapshot = rendered.get("snapshot") if isinstance(rendered.get("snapshot"), dict) else {}
    _env_note_text_theater_read(
        query_text,
        cached,
        snapshot,
        {
            "view_mode": rendered.get("view_mode"),
            "section_key": rendered.get("section_key"),
            "diagnostics": rendered.get("diagnostics"),
        },
    )
    return {
        "tool": "env_read",
        "status": "ok",
        "summary": "Rendered on-demand text theater view",
        "normalized_args": {
            "query": query_text,
            "view": rendered.get("view_mode"),
            "section": rendered.get("section_key"),
            "width": rendered.get("width"),
            "height": rendered.get("height"),
            "diagnostics": rendered.get("diagnostics"),
        },
        "delta": {
            "found": True,
            "type": "text_theater_view",
            "snapshot_timestamp": snapshot.get("snapshot_timestamp", 0),
            "last_sync_reason": snapshot.get("last_sync_reason", ""),
        },
        "operation": "env_read",
        "operation_status": "ok",
        "query": query_text,
        "text_theater_view": {
            "frame": rendered.get("frame", ""),
            "ansi_frame": rendered.get("ansi_frame", ""),
            "snapshot": snapshot,
            "theater_text": rendered.get("theater_text", ""),
            "embodiment_text": rendered.get("embodiment_text", ""),
            "view_mode": rendered.get("view_mode"),
            "section_key": rendered.get("section_key"),
            "width": rendered.get("width"),
            "height": rendered.get("height"),
            "diagnostics": rendered.get("diagnostics"),
            "snapshot_timestamp": snapshot.get("snapshot_timestamp", 0),
            "last_sync_reason": snapshot.get("last_sync_reason", ""),
        },
    }


def _env_text_theater_live_payload(args: dict | None = None) -> dict:
    args = args or {}
    query_text = str(args.get("query", "text_theater_live") or "text_theater_live").strip() or "text_theater_live"
    try:
        cached = _env_live_cache_snapshot()
        live_state = (cached or {}).get("live_state") if isinstance(cached, dict) else None
        shared_state = live_state.get("shared_state") if isinstance((live_state or {}).get("shared_state"), dict) else None
        if not isinstance(shared_state, dict):
            raise RuntimeError("No shared_state available in live cache")
        text_theater = shared_state.get("text_theater") if isinstance(shared_state.get("text_theater"), dict) else {}
        snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
        theater_text = str(text_theater.get("theater") or "")
        embodiment_text = str(text_theater.get("embodiment") or "")
        if not isinstance(snapshot, dict) or not snapshot or (not theater_text and not embodiment_text):
            raise RuntimeError("Live cache does not include text_theater payload")
        stale_flags = snapshot.get("stale_flags") if isinstance(snapshot.get("stale_flags"), dict) else {}
    except Exception as exc:
        return {
            "tool": "env_read",
            "status": "error",
            "summary": "Failed to read lightweight live text theater payload",
            "normalized_args": {"query": query_text},
            "delta": {"found": False},
            "operation": "env_read",
            "operation_status": "error",
            "query": query_text,
            "error": str(exc),
            "text_theater_live": None,
        }
    _env_note_text_theater_read(query_text, cached, snapshot)
    return {
        "tool": "env_read",
        "status": "ok",
        "summary": "Read lightweight live text theater payload from server live cache",
        "normalized_args": {"query": query_text},
        "delta": {
            "found": True,
            "type": "text_theater_live",
            "updated_ms": int((cached or {}).get("updated_ms") or 0),
            "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
            "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
        },
        "operation": "env_read",
        "operation_status": "ok",
        "query": query_text,
        "text_theater_live": {
            "snapshot": _json_clone(snapshot),
            "theater_text": theater_text,
            "embodiment_text": embodiment_text,
            "freshness": {
                "stale": bool(stale_flags.get("mirror_lag")),
                "mirror_lag": bool(stale_flags.get("mirror_lag")),
                "cache_updated_ms": int((cached or {}).get("updated_ms") or 0),
                "snapshot_timestamp": int(snapshot.get("snapshot_timestamp") or 0),
                "source_timestamp": int(snapshot.get("source_timestamp") or 0),
                "last_sync_reason": str(snapshot.get("last_sync_reason") or ""),
            },
        },
    }


def _env_read_local_proxy_payload(args: dict | None = None) -> dict | None:
    args = args or {}
    query_text = str(args.get("query", "list") or "list").strip() or "list"
    query_lower = query_text.lower()
    if query_lower == "debug_state":
        return _debug_state_payload(query_text)
    if query_lower == "probe_compare":
        return _env_probe_compare_payload()
    if query_lower in {"text_theater_view", "text_theater_blackboard", "text_theater_query_work"}:
        return _env_text_theater_view_payload(args)
    if query_lower == "text_theater_live":
        return _env_text_theater_live_payload(args)
    cached_payload = _env_read_live_cache_payload(query_text)
    if cached_payload is not None:
        return cached_payload
    query_map = {
        "frame": ("frame", "frame"),
        "frame_strip": ("strip", "frame_strip"),
        "time_strip": ("time_strip", "time_strip"),
        "supercam": ("supercam", "supercam"),
        "probe": ("probe", "probe"),
    }
    mapped = query_map.get(query_lower)
    if not mapped:
        return None
    capture_type, response_key = mapped
    entry = _env_capture_latest(capture_type)
    if entry is None:
        payload = {
            "tool": "env_read",
            "status": "partial",
            "summary": f"No {response_key} capture is available yet",
            "normalized_args": {"query": query_text},
            "delta": {"found": False},
            "operation": "env_read",
            "operation_status": "partial",
            "query": query_text,
            response_key: None,
        }
        return payload
    payload = {
        "tool": "env_read",
        "status": "ok",
        "summary": f"Read latest {response_key} capture",
        "normalized_args": {"query": query_text},
        "delta": {"found": True, "type": capture_type, "ts": entry.get("ts")},
        "operation": "env_read",
        "operation_status": "ok",
        "query": query_text,
        response_key: entry,
        "capture": entry,
    }
    _env_note_visual_corroboration_read(query_text, _env_live_cache_snapshot(), entry)
    return payload


async def _env_read_local_proxy_payload_async(args: dict | None = None) -> dict | None:
    return _env_read_local_proxy_payload(args)


async def _env_report_local_proxy_payload_async(args: dict | None = None) -> dict | None:
    return _env_report_local_proxy_payload(args)


_env_capture_load_index()


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
        req_prefix_raw = str(args.get("prefix", args.get("path", "")) or "")
        req_prefix = _doc_decode_key(req_prefix_raw) if req_prefix_raw else ""
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
                if tool_name == "file_tree":
                    parsed["path"] = req_prefix
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
    if tool_name == "continuity_status":
        try:
            limit = int(args.get("limit", 10) or 10)
        except Exception:
            limit = 10
        return continuity_status_payload(
            limit=max(1, min(limit, 50)),
            codex_home=str(args.get("codex_home", "") or "").strip() or None,
        )
    if tool_name == "continuity_restore":
        try:
            limit = int(args.get("limit", 3) or 3)
        except Exception:
            limit = 3
        try:
            since_days = int(args.get("since_days", 30) or 30)
        except Exception:
            since_days = 30
        return continuity_restore_payload(
            summary=str(args.get("summary", "") or ""),
            cwd=str(args.get("cwd", "") or ""),
            limit=max(1, min(limit, 10)),
            since_days=max(1, min(since_days, 3650)),
            session_path=str(args.get("session_path", "") or "").strip() or None,
            codex_home=str(args.get("codex_home", "") or "").strip() or None,
        )
    product_bundle_payload = await _product_bundle_local_tool(tool_name, args)
    if product_bundle_payload is not None:
        return product_bundle_payload
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

    if tool_name == "continuity_status":
        args = body if isinstance(body, dict) else {}
        try:
            limit = int(args.get("limit", 10) or 10)
        except Exception:
            limit = 10
        payload = continuity_status_payload(
            limit=max(1, min(limit, 50)),
            codex_home=str(args.get("codex_home", "") or "").strip() or None,
        )
        _broadcast_activity(tool_name, args, payload, 0, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "continuity_restore":
        args = body if isinstance(body, dict) else {}
        try:
            limit = int(args.get("limit", 3) or 3)
        except Exception:
            limit = 3
        try:
            since_days = int(args.get("since_days", 30) or 30)
        except Exception:
            since_days = 30
        payload = continuity_restore_payload(
            summary=str(args.get("summary", "") or ""),
            cwd=str(args.get("cwd", "") or ""),
            limit=max(1, min(limit, 10)),
            since_days=max(1, min(since_days, 3650)),
            session_path=str(args.get("session_path", "") or "").strip() or None,
            codex_home=str(args.get("codex_home", "") or "").strip() or None,
        )
        err_msg = payload.get("error") if isinstance(payload, dict) else None
        _broadcast_activity(tool_name, args, payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg:
            return JSONResponse(status_code=404, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    get_help_bridge_payload = _get_help_environment_bridge_payload(body if isinstance(body, dict) else {}) if tool_name == "get_help" else None
    if tool_name == "get_help" and get_help_bridge_payload is not None:
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, get_help_bridge_payload, 0, None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(get_help_bridge_payload)}], "isError": False}}

    env_help_proxy_payload = _env_help_local_proxy_payload(body if isinstance(body, dict) else {}) if tool_name == "env_help" else None
    if tool_name == "env_help" and env_help_proxy_payload is not None:
        err_msg = env_help_proxy_payload.get("error") if isinstance(env_help_proxy_payload, dict) else None
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, env_help_proxy_payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg and str(env_help_proxy_payload.get("status") or "").lower() == "error":
            return JSONResponse(status_code=404, content=env_help_proxy_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(env_help_proxy_payload)}], "isError": False}}

    env_control_args = body if isinstance(body, dict) else {}
    env_control_proxy_payload = _env_control_local_proxy_payload(env_control_args)
    if env_control_proxy_payload is not None:
        before_live_cache = _env_live_cache_snapshot()
        before_updated_ms = int((before_live_cache or {}).get("updated_ms") or 0)
        err_msg = env_control_proxy_payload.get("error") if isinstance(env_control_proxy_payload, dict) else None
        _broadcast_activity(tool_name, env_control_args, env_control_proxy_payload, 0, err_msg, source=source, client_id=client_id)
        env_control_proxy_payload = await _env_control_attach_text_theater_observation(
            env_control_proxy_payload,
            args=env_control_args,
            before_updated_ms=before_updated_ms,
        )
        if err_msg:
            return JSONResponse(status_code=400, content=env_control_proxy_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(env_control_proxy_payload)}], "isError": False}}

    env_persist_proxy_payload = _env_persist_local_proxy_payload(body if isinstance(body, dict) else {}) if tool_name == "env_persist" else None
    if tool_name == "env_persist" and env_persist_proxy_payload is not None:
        err_msg = env_persist_proxy_payload.get("error") if isinstance(env_persist_proxy_payload, dict) else None
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, env_persist_proxy_payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg:
            return JSONResponse(status_code=400, content=env_persist_proxy_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(env_persist_proxy_payload)}], "isError": False}}

    env_read_proxy_payload = await _env_read_local_proxy_payload_async(body if isinstance(body, dict) else {})
    if tool_name == "env_read" and env_read_proxy_payload is not None:
        err_msg = env_read_proxy_payload.get("error") if isinstance(env_read_proxy_payload, dict) else None
        if err_msg:
            return JSONResponse(status_code=400, content=env_read_proxy_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(env_read_proxy_payload)}], "isError": False}}

    env_report_proxy_payload = await _env_report_local_proxy_payload_async(body if isinstance(body, dict) else {})
    if tool_name == "env_report" and env_report_proxy_payload is not None:
        err_msg = env_report_proxy_payload.get("error") if isinstance(env_report_proxy_payload, dict) else None
        if err_msg:
            return JSONResponse(status_code=400, content=env_report_proxy_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(env_report_proxy_payload)}], "isError": False}}

    product_bundle_payload = await _product_bundle_local_tool(tool_name, body if isinstance(body, dict) else {})
    if product_bundle_payload is not None:
        err_msg = product_bundle_payload.get("error") if isinstance(product_bundle_payload, dict) else None
        _broadcast_activity(tool_name, body if isinstance(body, dict) else {}, product_bundle_payload, 0, err_msg, source=source, client_id=client_id)
        if err_msg:
            return JSONResponse(status_code=400, content=product_bundle_payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(product_bundle_payload)}], "isError": False}}

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

    plug_claim, plug_busy_guard = await _claim_plug_execution(tool_name, call_args, source, client_id)
    if plug_busy_guard:
        error_msg = plug_busy_guard.get("error") or f"Duplicate model load in progress while calling {tool_name}"
        payload = {"error": error_msg, "plug_busy": plug_busy_guard}
        _broadcast_activity(tool_name, call_args, payload, 0, error_msg, source=source, client_id=client_id)
        await _release_slot_execution(claim)
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
        await _release_plug_execution(plug_claim)
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
        "app_mode": APP_MODE,
        "mcp_external_policy": MCP_EXTERNAL_POLICY,
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
_dreamer_fetch_lock = asyncio.Lock()
_dreamer_sampler_task: asyncio.Task | None = None
_dreamer_config_defaults = {
    "control_plane": {
        "mode": "passive",
        "task": "half_kneel_l",
        "profile": "kneel_v1",
        "obs_schema": "dreamer_mechanics_v1",
        "action_schema_id": "kneel_v1_8",
        "reward_profile": "mechanics_v1",
    },
    "overlay": {
        "theater_hud": True,
        "show_grounding": True,
        "show_trail": True,
        "detail_level": "operator",
        "mirror_to_blackboard": True,
        "mirror_to_text_theater": True,
    },
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
    "mechanics_rewards": [],  # list of {ts, total_reward, action_key}
    "episode_steps": [],      # list of bounded outer-loop step summaries
}
_dreamer_last_cycle = 0

_DREAMER_MECHANICS_SCHEMA_ID = "dreamer_mechanics_v1"
_DREAMER_CONFIG_SCHEMA_VERSION = 1
_DREAMER_CONFIG_READ_ONLY_SECTIONS = ("architecture",)
_DREAMER_CONTROL_PLANE_MODES = [
    "off",
    "passive",
    "advisory",
    "active",
    "autonomous_eval",
]
_DREAMER_CONTROL_PLANE_PROFILES = [
    "kneel_v1",
    "passive_observer",
    "gravity_balance_v1",
]
_DREAMER_ACTION_SCHEMAS = [
    "kneel_v1_8",
]
_DREAMER_REWARD_PROFILES = [
    "mechanics_v1",
    "legacy_generic",
]
_DREAMER_OVERLAY_DETAIL_LEVELS = [
    "compact",
    "operator",
    "diagnostic",
]
_DREAMER_CONFIG_EDITABLE_SCHEMA = {
    "control_plane": {
        "mode": {"type": "enum", "options": _DREAMER_CONTROL_PLANE_MODES},
        "task": {"type": "string", "max_len": 64},
        "profile": {"type": "enum", "options": _DREAMER_CONTROL_PLANE_PROFILES},
        "obs_schema": {"type": "enum", "options": [_DREAMER_MECHANICS_SCHEMA_ID]},
        "action_schema_id": {"type": "enum", "options": _DREAMER_ACTION_SCHEMAS},
        "reward_profile": {"type": "enum", "options": _DREAMER_REWARD_PROFILES},
    },
    "overlay": {
        "theater_hud": {"type": "bool"},
        "show_grounding": {"type": "bool"},
        "show_trail": {"type": "bool"},
        "detail_level": {"type": "enum", "options": _DREAMER_OVERLAY_DETAIL_LEVELS},
        "mirror_to_blackboard": {"type": "bool"},
        "mirror_to_text_theater": {"type": "bool"},
    },
    "rewards": {
        "hold_accept": {"type": "float", "min": -5.0, "max": 5.0},
        "hold_override": {"type": "float", "min": -5.0, "max": 5.0},
        "bag_induct": {"type": "float", "min": -5.0, "max": 5.0},
        "bag_forget": {"type": "float", "min": -5.0, "max": 5.0},
        "workflow_save": {"type": "float", "min": -5.0, "max": 5.0},
        "workflow_success": {"type": "float", "min": -5.0, "max": 5.0},
        "workflow_failure": {"type": "float", "min": -5.0, "max": 5.0},
        "tool_success": {"type": "float", "min": -5.0, "max": 5.0},
        "tool_error": {"type": "float", "min": -5.0, "max": 5.0},
        "mutation_kept": {"type": "float", "min": -5.0, "max": 5.0},
        "mutation_reverted": {"type": "float", "min": -5.0, "max": 5.0},
        "normalize": {"type": "bool"},
    },
    "training": {
        "enabled": {"type": "bool"},
        "auto_train": {"type": "bool"},
        "world_model_frequency": {"type": "int", "min": 8, "max": 512},
        "critic_frequency": {"type": "int", "min": 8, "max": 512},
        "full_cycle_frequency": {"type": "int", "min": 16, "max": 1024},
        "batch_size": {"type": "int", "min": 8, "max": 256},
        "noise_scale": {"type": "float", "min": 0.0001, "max": 0.25},
        "gamma": {"type": "float", "min": 0.5, "max": 0.9999},
        "lambda": {"type": "float", "min": 0.5, "max": 0.9999},
        "critic_target_tau": {"type": "float", "min": 0.0001, "max": 0.5},
        "timeout_budget_seconds": {"type": "int", "min": 1, "max": 300},
    },
    "imagination": {
        "horizon": {"type": "int", "min": 1, "max": 128},
        "n_actions": {"type": "int", "min": 1, "max": 64},
        "auto_imagine_on_train": {"type": "bool"},
    },
    "buffers": {
        "reward_buffer_max": {"type": "int", "min": 100, "max": 50000},
        "obs_buffer_max": {"type": "int", "min": 100, "max": 20000},
        "value_history_max": {"type": "int", "min": 10, "max": 5000},
        "reward_rate_window": {"type": "int", "min": 5, "max": 5000},
    },
}
_DREAMER_MECHANICS_FIELDS = [
    "route.realized_support_count",
    "route.missing_support_count",
    "route.intended_support_count",
    "route.phase_index",
    "route.stage_blocked",
    "route.has_active_route",
    "balance.stability_risk",
    "balance.stability_margin",
    "balance.normalized_margin",
    "balance.nearest_edge_distance",
    "balance.support_count",
    "balance.balance_mode_code",
    "controller.present",
    "controller.leader_count",
    "controller.anchor_count",
    "controller.carrier_count",
    "contact.lower_leg_l.gap",
    "contact.lower_leg_l.manifold_points",
    "contact.lower_leg_l.load_share",
    "contact.lower_leg_l.supporting",
    "contact.foot_r.gap",
    "contact.foot_r.manifold_points",
    "contact.foot_r.load_share",
    "contact.foot_r.supporting",
    "pose.hips_pitch_deg",
    "pose.hips_world_y",
    "pose.hips_world_z",
    "pose.spine_pitch_deg",
    "pose.chest_pitch_deg",
    "pose.lower_leg_l_pitch_deg",
    "pose.foot_r_yaw_deg",
]
_DREAMER_TRANSFORM_RELAY_SCHEMA_ID = "dreamer_transform_relay_v1"
_DREAMER_BOUNDED_SWEEP_SCHEMA_ID = "dreamer_bounded_sweep_v1"
_DREAMER_CALIBRATION_DEFAULT_BONES = {
    "half_kneel_l": ["hips", "spine", "chest", "upper_leg_l", "lower_leg_l", "foot_r"],
}
_DREAMER_BALANCE_MODE_CODES = {
    "none": 0,
    "balanced": 1,
    "stable": 1,
    "single_support_left": 2,
    "single_support_right": 3,
    "braced": 4,
    "braced_support": 4,
    "double_support": 5,
    "falling": 6,
}
_DREAMER_KNEEL_CORRECTIONS = [
    {
        "action_id": 0,
        "action_key": "drop_hips",
        "label": "Drop Hips",
        "summary": "Lower the carrier to bring the knee closer to contact.",
        "task_scope": ["half_kneel_l"],
        "targets": ["hips"],
        "pose_delta": {"offset": {"hips": {"y": -0.12}}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "hips", "offset": {"x": 0.0, "y": -0.24, "z": 0.05}}
            ]
        },
    },
    {
        "action_id": 1,
        "action_key": "raise_hips",
        "label": "Raise Hips",
        "summary": "Lift the carrier slightly if the kneel over-compresses or scrapes.",
        "task_scope": ["half_kneel_l"],
        "targets": ["hips"],
        "pose_delta": {"offset": {"hips": {"y": 0.02}}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "hips", "offset": {"x": 0.0, "y": -0.10, "z": 0.05}}
            ]
        },
    },
    {
        "action_id": 2,
        "action_key": "shift_hips_fore",
        "label": "Shift Hips Forward",
        "summary": "Move the carrier forward to project load toward the kneel lane.",
        "task_scope": ["half_kneel_l"],
        "targets": ["hips"],
        "pose_delta": {"offset": {"hips": {"z": 0.02}}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "hips", "offset": {"x": 0.0, "y": -0.12, "z": 0.07}}
            ]
        },
    },
    {
        "action_id": 3,
        "action_key": "shift_hips_aft",
        "label": "Shift Hips Aft",
        "summary": "Move the carrier backward to recover the support polygon when overloaded forward.",
        "task_scope": ["half_kneel_l"],
        "targets": ["hips"],
        "pose_delta": {"offset": {"hips": {"z": -0.02}}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "hips", "offset": {"x": 0.0, "y": -0.12, "z": 0.03}}
            ]
        },
    },
    {
        "action_id": 4,
        "action_key": "counter_rotate_spine",
        "label": "Counter-Rotate Spine",
        "summary": "Tilt the spine back to counter forward collapse during kneel contact.",
        "task_scope": ["half_kneel_l"],
        "targets": ["spine"],
        "pose_delta": {"rotation_deg": {"spine": [-3, 0, 0]}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "spine", "rotation_deg": [-9, 0, 0]}
            ]
        },
    },
    {
        "action_id": 5,
        "action_key": "counter_rotate_chest",
        "label": "Counter-Rotate Chest",
        "summary": "Shift the chest back to keep the upper body from pitching into the route.",
        "task_scope": ["half_kneel_l"],
        "targets": ["chest"],
        "pose_delta": {"rotation_deg": {"chest": [-3, 0, 0]}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "chest", "rotation_deg": [-11, 0, 0]}
            ]
        },
    },
    {
        "action_id": 6,
        "action_key": "tuck_lead_knee",
        "label": "Tuck Lead Knee",
        "summary": "Increase knee flexion to reduce the left knee contact gap.",
        "task_scope": ["half_kneel_l"],
        "targets": ["lower_leg_l"],
        "pose_delta": {"rotation_deg": {"lower_leg_l": [20, 0, 0]}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "lower_leg_l", "rotation_deg": [140, 0, 0]}
            ]
        },
    },
    {
        "action_id": 7,
        "action_key": "widen_anchor_foot",
        "label": "Widen Anchor Foot",
        "summary": "Yaw the planted right foot outward to improve the support polygon.",
        "task_scope": ["half_kneel_l"],
        "targets": ["foot_r"],
        "pose_delta": {"rotation_deg": {"foot_r": [0, 8, 0]}},
        "workbench_set_pose_batch_template": {
            "poses": [
                {"bone": "foot_r", "rotation_deg": [-25, 14, 0]}
            ]
        },
    },
]


def _dreamer_mechanics_number(value, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if numeric != numeric:
        return float(fallback)
    return float(numeric)


def _dreamer_mechanics_flag(value) -> float:
    return 1.0 if bool(value) else 0.0


def _dreamer_mechanics_live_snapshot() -> tuple[dict | None, int]:
    payload = _env_read_live_cache_payload("text_theater_snapshot")
    if not isinstance(payload, dict):
        return None, 0
    snapshot = payload.get("text_theater_snapshot")
    if not isinstance(snapshot, dict):
        return None, 0
    delta = payload.get("delta") if isinstance(payload.get("delta"), dict) else {}
    updated_ms = int(delta.get("updated_ms") or 0)
    return snapshot, updated_ms


def _dreamer_snapshot_blackboard_context(snapshot: dict) -> dict:
    blackboard = snapshot.get("blackboard") if isinstance(snapshot.get("blackboard"), dict) else {}
    working_set = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    focus = blackboard.get("focus") if isinstance(blackboard.get("focus"), dict) else {}
    return {
        "row_count": int(blackboard.get("row_count") or 0),
        "families": [str(item or "") for item in list(blackboard.get("families") or [])[:8]],
        "lead_row_ids": [str(item or "") for item in list(working_set.get("lead_row_ids") or [])[:8]],
        "intended_support_set": [str(item or "") for item in list(working_set.get("intended_support_set") or [])[:8]],
        "missing_support_set": [str(item or "") for item in list(working_set.get("missing_support_set") or [])[:8]],
        "focus": {
            "kind": str(focus.get("kind") or ""),
            "id": str(focus.get("id") or ""),
            "label": str(focus.get("label") or ""),
        },
    }


def _dreamer_snapshot_query_thread(snapshot: dict) -> dict:
    blackboard = snapshot.get("blackboard") if isinstance(snapshot.get("blackboard"), dict) else {}
    working_set = blackboard.get("working_set") if isinstance(blackboard.get("working_set"), dict) else {}
    query_thread = working_set.get("query_thread") if isinstance(working_set.get("query_thread"), dict) else {}
    if not isinstance(query_thread, dict) or not query_thread:
        return {}
    return {
        "sequence_id": str(query_thread.get("sequence_id") or ""),
        "segment_id": str(query_thread.get("segment_id") or ""),
        "session_id": str(query_thread.get("session_id") or ""),
        "subject_key": str(query_thread.get("subject_key") or ""),
        "status": str(query_thread.get("status") or ""),
        "current_pivot_id": str(query_thread.get("current_pivot_id") or ""),
        "objective_id": str(query_thread.get("objective_id") or ""),
        "objective_label": str(query_thread.get("objective_label") or ""),
        "visible_read": str(query_thread.get("visible_read") or ""),
        "anchor_row_ids": [str(item or "") for item in list(query_thread.get("anchor_row_ids") or [])[:8]],
        "priority_pivots": [
            {
                "pivot_id": str((item or {}).get("pivot_id") or ""),
                "status": str((item or {}).get("status") or ""),
            }
            for item in list(query_thread.get("priority_pivots") or [])[:4]
            if isinstance(item, dict)
        ],
        "next_reads": [
            {
                "step": str((item or {}).get("step") or ""),
                "reason": str((item or {}).get("reason") or ""),
            }
            for item in list(query_thread.get("next_reads") or [])[:4]
            if isinstance(item, dict)
        ],
        "help_lane": [
            {
                "topic": str((item or {}).get("topic") or ""),
                "reason": str((item or {}).get("reason") or ""),
            }
            for item in list(query_thread.get("help_lane") or [])[:4]
            if isinstance(item, dict)
        ],
        "raw_state_guardrail": str(query_thread.get("raw_state_guardrail") or ""),
    }


def _dreamer_snapshot_oracle_context(snapshot: dict) -> dict:
    output_state = snapshot.get("output_state") if isinstance(snapshot.get("output_state"), dict) else {}
    placement = output_state.get("placement") if isinstance(output_state.get("placement"), dict) else {}
    equilibrium = output_state.get("equilibrium") if isinstance(output_state.get("equilibrium"), dict) else {}
    technolit_measure = (
        equilibrium.get("technolit_measure")
        if isinstance(equilibrium.get("technolit_measure"), dict)
        else {}
    )
    drift = output_state.get("drift") if isinstance(output_state.get("drift"), dict) else {}
    watch_board = output_state.get("watch_board") if isinstance(output_state.get("watch_board"), dict) else {}
    tinkerbell_attention = output_state.get("tinkerbell_attention") if isinstance(output_state.get("tinkerbell_attention"), dict) else {}
    technolit_distribution_packet = (
        output_state.get("technolit_distribution_packet")
        if isinstance(output_state.get("technolit_distribution_packet"), dict)
        else {}
    )
    technolit_treasury_bridge_packet = (
        output_state.get("technolit_treasury_bridge_packet")
        if isinstance(output_state.get("technolit_treasury_bridge_packet"), dict)
        else {}
    )
    holder_snapshot_packet = (
        output_state.get("holder_snapshot_packet")
        if isinstance(output_state.get("holder_snapshot_packet"), dict)
        else {}
    )
    raid_contribution_packet = (
        output_state.get("raid_contribution_packet")
        if isinstance(output_state.get("raid_contribution_packet"), dict)
        else {}
    )
    settlement_epoch_packet = (
        output_state.get("settlement_epoch_packet")
        if isinstance(output_state.get("settlement_epoch_packet"), dict)
        else {}
    )
    hold_door_raid_report_packet = (
        output_state.get("hold_door_raid_report_packet")
        if isinstance(output_state.get("hold_door_raid_report_packet"), dict)
        else {}
    )
    hold_door_comedia_packet = (
        output_state.get("hold_door_comedia_packet")
        if isinstance(output_state.get("hold_door_comedia_packet"), dict)
        else {}
    )
    threat_bounty_packet = (
        output_state.get("threat_bounty_packet")
        if isinstance(output_state.get("threat_bounty_packet"), dict)
        else {}
    )
    active_pointer = tinkerbell_attention.get("active_pointer") if isinstance(tinkerbell_attention.get("active_pointer"), dict) else {}
    field_disposition = output_state.get("field_disposition") if isinstance(output_state.get("field_disposition"), dict) else {}
    pan_probe = output_state.get("pan_probe") if isinstance(output_state.get("pan_probe"), dict) else {}
    writer_identity = pan_probe.get("writer_identity") if isinstance(pan_probe.get("writer_identity"), dict) else {}
    equilibrium_band = str(equilibrium.get("band") or equilibrium.get("state") or "")
    drift_band = str(drift.get("band") or drift.get("level") or "")
    watch_band = str(watch_board.get("band") or watch_board.get("status") or "")
    field_settling_band = str(field_disposition.get("settling_band") or field_disposition.get("settle_band") or "")
    return {
        "summary": str(output_state.get("summary") or ""),
        "equilibrium_band": equilibrium_band,
        "equilibrium_state": equilibrium_band,
        "equilibrium_summary": str(equilibrium.get("summary") or ""),
        "equilibrium_signals": [str(item or "") for item in list(equilibrium.get("signals") or [])[:6]],
        "technolit_band": str(technolit_measure.get("band") or ""),
        "technolit_symbol": str(technolit_measure.get("symbol") or ""),
        "technolit_coin_id": str(technolit_measure.get("coin_id") or ""),
        "technolit_summary": str(technolit_measure.get("summary") or ""),
        "technolit_flow_posture": str(technolit_measure.get("flow_posture") or ""),
        "technolit_distribution_posture": str(technolit_measure.get("distribution_posture") or ""),
        "technolit_burn_gate": str(technolit_measure.get("burn_gate") or ""),
        "technolit_creator_rewards_unclaimed_sol": _dreamer_mechanics_number(
            technolit_measure.get("creator_rewards_unclaimed_sol"),
            0.0,
        ),
        "technolit_distribution_stage": str(technolit_distribution_packet.get("stage") or ""),
        "technolit_distribution_next_contract": str(technolit_distribution_packet.get("next_contract") or ""),
        "technolit_distribution_public_line": str(technolit_distribution_packet.get("public_line") or ""),
        "technolit_distribution_summary": str(technolit_distribution_packet.get("summary") or ""),
        "technolit_treasury_bridge_stage": str(technolit_treasury_bridge_packet.get("stage") or ""),
        "technolit_treasury_bridge_next_contract": str(technolit_treasury_bridge_packet.get("next_contract") or ""),
        "technolit_treasury_bridge_settlement_asset": str(technolit_treasury_bridge_packet.get("settlement_asset") or ""),
        "technolit_treasury_bridge_summary": str(technolit_treasury_bridge_packet.get("summary") or ""),
        "holder_snapshot_stage": str(holder_snapshot_packet.get("stage") or ""),
        "holder_snapshot_camp_label": str(holder_snapshot_packet.get("camp_label") or ""),
        "holder_snapshot_summary": str(holder_snapshot_packet.get("summary") or ""),
        "raid_contribution_stage": str(raid_contribution_packet.get("stage") or ""),
        "raid_contribution_label": str(raid_contribution_packet.get("raid_label") or ""),
        "raid_contribution_summary": str(raid_contribution_packet.get("summary") or ""),
        "settlement_epoch_stage": str(settlement_epoch_packet.get("stage") or ""),
        "settlement_epoch_asset": str(settlement_epoch_packet.get("settlement_asset") or ""),
        "settlement_epoch_summary": str(settlement_epoch_packet.get("summary") or ""),
        "settlement_epoch_hourly": str(((settlement_epoch_packet.get("game_clock") or {}).get("hourly")) or ""),
        "settlement_epoch_weekly": str(((settlement_epoch_packet.get("game_clock") or {}).get("weekly")) or ""),
        "settlement_epoch_circuit_breaker": str(settlement_epoch_packet.get("circuit_breaker_mode") or ""),
        "hold_door_raid_report_stage": str(hold_door_raid_report_packet.get("stage") or ""),
        "hold_door_raid_report_name": str(hold_door_raid_report_packet.get("display_name") or ""),
        "hold_door_raid_report_summary": str(hold_door_raid_report_packet.get("summary") or ""),
        "hold_door_comedia_stage": str(hold_door_comedia_packet.get("stage") or ""),
        "hold_door_comedia_mood": str(hold_door_comedia_packet.get("mood") or ""),
        "hold_door_comedia_reaction": str(hold_door_comedia_packet.get("reaction") or ""),
        "hold_door_comedia_caption_line": str(hold_door_comedia_packet.get("caption_line") or ""),
        "hold_door_comedia_tempo_bpm": _dreamer_mechanics_number(
            hold_door_comedia_packet.get("tempo_bpm"),
            0.0,
        ),
        "hold_door_comedia_trigger": str(hold_door_comedia_packet.get("trajectory_trigger") or ""),
        "threat_bounty_stage": str(threat_bounty_packet.get("stage") or ""),
        "threat_bounty_summary": str(threat_bounty_packet.get("summary") or ""),
        "threat_bounty_active_threats": [str(item or "") for item in list(threat_bounty_packet.get("active_threats") or [])[:6]],
        "drift_band": drift_band,
        "drift_level": drift_band,
        "watch_band": watch_band,
        "watch_status": watch_band,
        "watch_priority": str(watch_board.get("priority") or watch_band),
        "watch_alerts": [str(item or "") for item in list(watch_board.get("alerts") or [])[:6]],
        "attention_band": str(tinkerbell_attention.get("band") or ""),
        "attention_summary": str(tinkerbell_attention.get("summary") or ""),
        "attention_kind": str(active_pointer.get("target_kind") or tinkerbell_attention.get("attention_kind") or ""),
        "attention_target": str(active_pointer.get("target") or tinkerbell_attention.get("attention_target") or ""),
        "attention_confidence": _dreamer_mechanics_number(
            active_pointer.get("confidence", tinkerbell_attention.get("attention_confidence")),
            0.0,
        ),
        "attention_why_now": str(active_pointer.get("why_now") or active_pointer.get("why_this_spot") or ""),
        "attention_expected_read": str(active_pointer.get("expected_read") or ""),
        "attention_hold_candidate": bool(active_pointer.get("hold_candidate", tinkerbell_attention.get("hold_candidate"))),
        "attention_source_ripples": [str(item or "") for item in list(active_pointer.get("source_ripples") or [])[:6]],
        "attention_candidate_kinds": [
            str((item or {}).get("target_kind") or "")
            for item in list(tinkerbell_attention.get("prospect_candidates") or [])[:4]
            if isinstance(item, dict)
        ],
        "field_medium_kind": str(field_disposition.get("medium_kind") or ""),
        "field_propagation_mode": str(field_disposition.get("propagation_mode") or ""),
        "field_settling_band": field_settling_band,
        "field_settle_band": field_settling_band,
        "pan_band": str(pan_probe.get("band") or ""),
        "pan_summary": str(pan_probe.get("summary") or ""),
        "rotational_grounding": bool(pan_probe.get("rotational_grounding")),
        "contact_bias": str(pan_probe.get("contact_bias") or ""),
        "support_role": str(pan_probe.get("support_role") or ""),
        "selected_bone_id": str(pan_probe.get("selected_bone_id") or ""),
        "selected_contact_joint": str(pan_probe.get("selected_contact_joint") or ""),
        "placement_subject": str(placement.get("subject") or ""),
        "placement_objective": str(placement.get("objective") or ""),
        "placement_seam": str(placement.get("seam") or ""),
        "placement_evidence": _json_clone(placement.get("evidence") or {}),
        "placement_drift": _json_clone(placement.get("drift") or {}),
        "placement_next": _json_clone(placement.get("next") or {}),
        "writer_last_sync_reason": str(writer_identity.get("last_sync_reason") or ""),
        "writer_tool": str(writer_identity.get("render_last_tool_applied") or ""),
        "writer_source": str(writer_identity.get("render_last_tool_source") or ""),
    }


def _dreamer_mechanics_contact_row(contacts: list[dict], joint_id: str) -> dict:
    target = str(joint_id or "").strip().lower()
    if not target:
        return {}
    aliases = {target}
    if "_" in target:
        left, right = target.split("_", 1)
        aliases.add(f"{right}_{left}")
    for row in contacts:
        if not isinstance(row, dict):
            continue
        row_joint = str(row.get("joint") or "").strip().lower()
        row_group = str(row.get("group") or "").strip().lower()
        row_side = str(row.get("side") or "").strip().lower()
        row_aliases = {row_joint}
        if row_group and row_side:
            row_aliases.add(f"{row_group}_{row_side}")
            row_aliases.add(f"{row_side}_{row_group}")
        if aliases & row_aliases:
            return row
    return {}


def _dreamer_mechanics_load_share(load_field: dict, target_id: str) -> float:
    loads = load_field.get("support_loads") if isinstance(load_field.get("support_loads"), dict) else {}
    target = str(target_id or "").strip().lower()
    if not target or not loads:
        return 0.0
    aliases = {target}
    if "_" in target:
        left, right = target.split("_", 1)
        aliases.add(f"{right}_{left}")
    best = 0.0
    for key, value in loads.items():
        key_lower = str(key or "").strip().lower()
        key_aliases = {key_lower}
        if "_" in key_lower:
            left, right = key_lower.split("_", 1)
            key_aliases.add(f"{right}_{left}")
        if aliases & key_aliases:
            best = max(best, _dreamer_mechanics_number(value, 0.0))
    return best


def _dreamer_mechanics_bone_row(snapshot: dict, bone_id: str) -> dict:
    embodiment = snapshot.get("embodiment") if isinstance(snapshot.get("embodiment"), dict) else {}
    bones = embodiment.get("bones") if isinstance(embodiment.get("bones"), list) else []
    target = str(bone_id or "").strip().lower()
    for row in bones:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "").strip().lower() == target:
            return row
    return {}


def _dreamer_mechanics_bone_rotation(snapshot: dict, bone_id: str, axis_index: int) -> float:
    row = _dreamer_mechanics_bone_row(snapshot, bone_id)
    rotation = row.get("rotation_deg") if isinstance(row.get("rotation_deg"), list) else []
    return _dreamer_mechanics_number(rotation[axis_index] if axis_index < len(rotation) else 0.0, 0.0)


def _dreamer_mechanics_bone_world(snapshot: dict, bone_id: str, axis_index: int) -> float:
    row = _dreamer_mechanics_bone_row(snapshot, bone_id)
    world_pos = row.get("world_pos") if isinstance(row.get("world_pos"), list) else []
    return _dreamer_mechanics_number(world_pos[axis_index] if axis_index < len(world_pos) else 0.0, 0.0)


def _dreamer_transform_relay_bones(task_name: str = "", requested_bones=None) -> list[str]:
    explicit = []
    if isinstance(requested_bones, str):
        explicit = [part.strip() for part in requested_bones.split(",") if str(part or "").strip()]
    elif isinstance(requested_bones, list):
        explicit = [str(part or "").strip() for part in requested_bones if str(part or "").strip()]
    if explicit:
        seen = set()
        ordered = []
        for bone_id in explicit:
            if bone_id in seen:
                continue
            seen.add(bone_id)
            ordered.append(bone_id)
        return ordered
    task_key = str(task_name or "").strip() or "half_kneel_l"
    return list(_DREAMER_CALIBRATION_DEFAULT_BONES.get(task_key) or _DREAMER_CALIBRATION_DEFAULT_BONES["half_kneel_l"])


def _dreamer_pose_triplet(value, fallback: list[float] | None = None) -> list[float]:
    base = list(fallback) if isinstance(fallback, list) and len(fallback) >= 3 else [0.0, 0.0, 0.0]
    if isinstance(value, list):
        seq = value[:3]
    elif isinstance(value, tuple):
        seq = list(value[:3])
    elif isinstance(value, dict):
        seq = [value.get("x", base[0]), value.get("y", base[1]), value.get("z", base[2])]
    else:
        seq = base
    out = []
    for index in range(3):
        seed = base[index] if index < len(base) else 0.0
        raw = seq[index] if index < len(seq) else seed
        out.append(_dreamer_mechanics_number(raw, seed))
    return out


def _dreamer_mechanics_pose_transform(snapshot: dict, bone_id: str) -> dict:
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    pose = workbench.get("pose") if isinstance(workbench.get("pose"), dict) else {}
    transforms = pose.get("transforms") if isinstance(pose.get("transforms"), dict) else {}
    return transforms.get(str(bone_id or "").strip()) if isinstance(transforms.get(str(bone_id or "").strip()), dict) else {}


def _dreamer_mechanics_macro_pose_entry(snapshot: dict, task_name: str, bone_id: str) -> dict:
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    registry = workbench.get("pose_macro_registry")
    target_task = str(task_name or "").strip()
    target_bone = str(bone_id or "").strip()
    if not target_task or not target_bone:
        return {}
    candidates = []
    if isinstance(registry, dict):
        direct = registry.get(target_task)
        if isinstance(direct, dict):
            candidates.append(direct)
        for value in registry.values():
            if isinstance(value, dict):
                candidates.append(value)
    elif isinstance(registry, list):
        candidates = [row for row in registry if isinstance(row, dict)]
    for candidate in candidates:
        macro_id = str(candidate.get("macro_id") or candidate.get("id") or "").strip()
        if macro_id and macro_id != target_task:
            continue
        batch = candidate.get("batch") if isinstance(candidate.get("batch"), list) else []
        for entry in batch:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("bone") or entry.get("bone_id") or "").strip() == target_bone:
                return entry
    return {}


def _dreamer_calibration_root_for_bone(snapshot: dict, task_name: str, bone_id: str) -> dict:
    bone_row = _dreamer_mechanics_bone_row(snapshot, bone_id)
    current_transform = _dreamer_mechanics_pose_transform(snapshot, bone_id)
    macro_row = _dreamer_mechanics_macro_pose_entry(snapshot, task_name, bone_id)
    observed_rotation = _dreamer_pose_triplet(bone_row.get("rotation_deg"))
    observed_local_offset = _dreamer_pose_triplet(bone_row.get("local_offset"))
    current_offset = _dreamer_pose_triplet(current_transform.get("offset"), observed_local_offset)
    macro_offset = _dreamer_pose_triplet(macro_row.get("offset"))
    macro_rotation = _dreamer_pose_triplet(macro_row.get("rotation_deg"))
    return {
        "bone_id": str(bone_id or "").strip(),
        "rotation_deg": observed_rotation,
        "offset": {"x": current_offset[0], "y": current_offset[1], "z": current_offset[2]},
        "macro_offset": {"x": macro_offset[0], "y": macro_offset[1], "z": macro_offset[2]},
        "macro_rotation_deg": macro_rotation,
        "sources": {
            "bone_row_present": bool(bone_row),
            "current_pose_transform_present": bool(current_transform),
            "macro_pose_entry_present": bool(macro_row),
        },
    }


def _dreamer_calibration_root(snapshot: dict, task_name: str, bones: list[str] | None = None) -> dict:
    rows = []
    for bone_id in bones if isinstance(bones, list) else _dreamer_transform_relay_bones(task_name):
        bone = str(bone_id or "").strip()
        if not bone:
            continue
        rows.append(_dreamer_calibration_root_for_bone(snapshot, task_name, bone))
    return {
        "task": str(task_name or "").strip() or "half_kneel_l",
        "bones": rows,
        "bone_map": {str((row or {}).get("bone_id") or ""): row for row in rows if isinstance(row, dict) and str((row or {}).get("bone_id") or "")},
    }


def _dreamer_transform_relay_bone_entry(snapshot: dict, task_name: str, bone_id: str) -> dict:
    bone_row = _dreamer_mechanics_bone_row(snapshot, bone_id)
    current_transform = _dreamer_mechanics_pose_transform(snapshot, bone_id)
    macro_row = _dreamer_mechanics_macro_pose_entry(snapshot, task_name, bone_id)
    observed_rotation = _dreamer_pose_triplet(bone_row.get("rotation_deg"))
    observed_world = _dreamer_pose_triplet(bone_row.get("world_pos"))
    observed_local_offset = _dreamer_pose_triplet(bone_row.get("local_offset"))
    current_offset = _dreamer_pose_triplet(
        current_transform.get("offset"),
        _dreamer_pose_triplet(macro_row.get("offset"), observed_local_offset),
    )
    macro_offset = _dreamer_pose_triplet(macro_row.get("offset"))
    return {
        "bone_id": str(bone_id or "").strip(),
        "posed": bool(bone_row.get("posed") or current_transform),
        "observed": {
            "rotation_deg": observed_rotation,
            "world_pos": observed_world,
            "local_offset": observed_local_offset,
        },
        "current_pose_transform": {
            "rotation_quat": _json_clone(current_transform.get("rotation")),
            "offset": {"x": current_offset[0], "y": current_offset[1], "z": current_offset[2]},
        },
        "macro_pose_entry": {
            "rotation_deg": _dreamer_pose_triplet(macro_row.get("rotation_deg")),
            "offset": {"x": macro_offset[0], "y": macro_offset[1], "z": macro_offset[2]},
        },
        "sources": {
            "bone_row_present": bool(bone_row),
            "current_pose_transform_present": bool(current_transform),
            "macro_pose_entry_present": bool(macro_row),
        },
    }


def _dreamer_transform_relay_payload(snapshot: dict, updated_ms: int, task_name: str = "", requested_bones=None) -> dict:
    task_key = str(task_name or "").strip() or "half_kneel_l"
    observation_payload = _dreamer_mechanics_observation_payload(snapshot, updated_ms)
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    bones = _dreamer_transform_relay_bones(task_key, requested_bones)
    relay_bones = [_dreamer_transform_relay_bone_entry(snapshot, task_key, bone_id) for bone_id in bones]
    support_polygon = balance.get("support_polygon") if isinstance(balance.get("support_polygon"), list) else []
    projected_com = balance.get("projected_com") if isinstance(balance.get("projected_com"), dict) else {}
    com = balance.get("com") if isinstance(balance.get("com"), dict) else {}
    nearest_edge = balance.get("nearest_edge") if isinstance(balance.get("nearest_edge"), dict) else {}
    pose = workbench.get("pose") if isinstance(workbench.get("pose"), dict) else {}
    transforms = pose.get("transforms") if isinstance(pose.get("transforms"), dict) else {}
    return {
        "status": "ok",
        "schema_id": _DREAMER_TRANSFORM_RELAY_SCHEMA_ID,
        "target_task": task_key,
        "updated_ms": int(updated_ms or 0),
        "obs_source": "text_theater_snapshot",
        "compact_observation": _dreamer_compact_observation(observation_payload),
        "workbench": {
            "pose_transform_count": len(transforms),
            "posed_bone_ids": list(workbench.get("posed_bone_ids") or []),
            "selected_controller_id": str(workbench.get("selected_controller_id") or ""),
            "selected_controller_label": str(workbench.get("selected_controller_label") or ""),
        },
        "route": {
            "status": str(route_report.get("status") or ""),
            "active_phase_id": str(route_report.get("active_phase_id") or ""),
            "active_phase_label": str(route_report.get("active_phase_label") or ""),
            "phase_gate_summary": str(route_report.get("phase_gate_summary") or ""),
            "realized_support_set": _json_clone(route_report.get("realized_support_set") or []),
            "intended_support_set": _json_clone(route_report.get("intended_support_set") or []),
            "missing_support_participants": _json_clone(route_report.get("missing_support_participants") or []),
        },
        "balance_geometry": {
            "com": _json_clone(com),
            "projected_com": _json_clone(projected_com),
            "support_polygon": _json_clone(support_polygon),
            "nearest_edge": _json_clone(nearest_edge),
            "supporting_joint_ids": _json_clone(balance.get("supporting_joint_ids") or []),
            "alert_ids": _json_clone(balance.get("alert_ids") or []),
            "stability_margin": _dreamer_mechanics_number(balance.get("stability_margin"), 0.0),
            "stability_risk": _dreamer_mechanics_number(balance.get("stability_risk"), 0.0),
        },
        "relay_bones": relay_bones,
    }


def _dreamer_sweep_axis_spec(axis_name: str) -> tuple[str, int] | None:
    text = str(axis_name or "").strip().lower()
    mapping = {
        "rotation_x": ("rotation_deg", 0),
        "rotation_y": ("rotation_deg", 1),
        "rotation_z": ("rotation_deg", 2),
        "offset_x": ("offset", 0),
        "offset_y": ("offset", 1),
        "offset_z": ("offset", 2),
    }
    return mapping.get(text)


def _dreamer_sweep_values(start: float, stop: float, step: float) -> list[float]:
    if step == 0:
        return [round(float(start), 4)]
    values = []
    current = float(start)
    forward = step > 0
    max_iters = 512
    while max_iters > 0:
        values.append(round(current, 4))
        max_iters -= 1
        next_value = current + step
        if forward:
            if next_value > stop + 1e-9:
                break
        else:
            if next_value < stop - 1e-9:
                break
        current = next_value
    if values and abs(values[-1] - stop) > 1e-6:
        values.append(round(float(stop), 4))
    return values


async def _dreamer_restore_task_baseline(task_name: str, *, source: str = "webui", client_id: str | None = None, actor: str = "assistant") -> tuple[dict | None, str | None]:
    editing_payload, editing_err = await _dreamer_dispatch_env_control({
        "command": "workbench_set_editing_mode",
        "target_id": json.dumps({"editing_mode": "pose"}),
        "actor": actor,
        "include_full": False,
    }, source=source, client_id=client_id)
    if editing_err:
        return None, editing_err
    macro_payload, macro_err = await _dreamer_dispatch_env_control({
        "command": "workbench_apply_pose_macro",
        "target_id": json.dumps({"macro_id": str(task_name or "half_kneel_l")}),
        "actor": actor,
        "include_full": False,
    }, source=source, client_id=client_id)
    if macro_err:
        return None, macro_err
    return {"editing_mode": editing_payload, "macro": macro_payload}, None


async def _dreamer_restore_neutral_baseline(*, source: str = "webui", client_id: str | None = None, actor: str = "assistant") -> tuple[dict | None, str | None]:
    pose_payload, pose_err = await _dreamer_dispatch_env_control({
        "command": "workbench_set_editing_mode",
        "target_id": json.dumps({"editing_mode": "pose"}),
        "actor": actor,
        "include_full": False,
    }, source=source, client_id=client_id)
    if pose_err:
        return None, pose_err
    clear_payload, clear_err = await _dreamer_dispatch_env_control({
        "command": "workbench_clear_pose",
        "target_id": json.dumps({"all": True}),
        "actor": actor,
        "include_full": False,
    }, source=source, client_id=client_id)
    if clear_err:
        return None, clear_err
    return {"pose_mode": pose_payload, "clear": clear_payload}, None


async def _dreamer_capture_stable_snapshot(after_updated_ms: int = 0, *, timeout_s: float = 2.2, poll_s: float = 0.05) -> tuple[dict | None, int]:
    baseline_ms = int(after_updated_ms or 0)
    deadline = time.time() + max(0.1, float(timeout_s or 0.1))
    latest_snapshot = None
    latest_updated_ms = 0
    while time.time() < deadline:
        snapshot, updated_ms = _dreamer_mechanics_live_snapshot()
        if isinstance(snapshot, dict):
            latest_snapshot = snapshot
            latest_updated_ms = int(updated_ms or 0)
            if latest_updated_ms > baseline_ms:
                return latest_snapshot, latest_updated_ms
        await asyncio.sleep(max(0.01, float(poll_s or 0.01)))
    return latest_snapshot, latest_updated_ms


async def _dreamer_capture_calibration_anchors(task_name: str, *, source: str = "webui", client_id: str | None = None, actor: str = "assistant", focus_bones: list[str] | None = None) -> tuple[dict | None, str | None]:
    target_bones = focus_bones if isinstance(focus_bones, list) and focus_bones else _dreamer_transform_relay_bones(task_name)
    neutral_restore, neutral_err = await _dreamer_restore_neutral_baseline(source=source, client_id=client_id, actor=actor)
    if neutral_err:
        return None, neutral_err
    neutral_clear = neutral_restore.get("clear") if isinstance(neutral_restore, dict) and isinstance(neutral_restore.get("clear"), dict) else {}
    neutral_text = neutral_clear.get("text_theater") if isinstance(neutral_clear.get("text_theater"), dict) else {}
    neutral_snapshot = neutral_text.get("snapshot") if isinstance(neutral_text.get("snapshot"), dict) else {}
    neutral_boundary_ms = int(
        neutral_snapshot.get("source_timestamp")
        or neutral_snapshot.get("snapshot_timestamp")
        or ((neutral_text.get("freshness") if isinstance(neutral_text.get("freshness"), dict) else {}).get("cache_updated_ms") or 0)
    )
    current_neutral_snapshot, current_neutral_updated_ms = await _dreamer_capture_stable_snapshot(neutral_boundary_ms)
    if not isinstance(current_neutral_snapshot, dict):
        return None, "No live text theater snapshot available for neutral calibration anchor"
    neutral_observation = _dreamer_mechanics_observation_payload(current_neutral_snapshot, current_neutral_updated_ms)
    neutral_root = _dreamer_calibration_root(current_neutral_snapshot, "neutral", target_bones)

    task_restore, task_err = await _dreamer_restore_task_baseline(task_name, source=source, client_id=client_id, actor=actor)
    if task_err:
        return None, task_err
    task_macro = task_restore.get("macro") if isinstance(task_restore, dict) and isinstance(task_restore.get("macro"), dict) else {}
    task_text = task_macro.get("text_theater") if isinstance(task_macro.get("text_theater"), dict) else {}
    task_snapshot = task_text.get("snapshot") if isinstance(task_text.get("snapshot"), dict) else {}
    task_boundary_ms = int(
        task_snapshot.get("source_timestamp")
        or task_snapshot.get("snapshot_timestamp")
        or ((task_text.get("freshness") if isinstance(task_text.get("freshness"), dict) else {}).get("cache_updated_ms") or 0)
    )
    current_task_snapshot, current_task_updated_ms = await _dreamer_capture_stable_snapshot(task_boundary_ms)
    if not isinstance(current_task_snapshot, dict):
        return None, "No live text theater snapshot available for task calibration anchor"
    task_observation = _dreamer_mechanics_observation_payload(current_task_snapshot, current_task_updated_ms)
    task_root = _dreamer_calibration_root(current_task_snapshot, task_name, target_bones)
    return {
        "task": str(task_name or "").strip() or "half_kneel_l",
        "bones": list(target_bones),
        "neutral": {
            "restore": neutral_restore,
            "updated_ms": int(current_neutral_updated_ms or 0),
            "observation": neutral_observation,
            "root": neutral_root,
        },
        "task_root": {
            "restore": task_restore,
            "updated_ms": int(current_task_updated_ms or 0),
            "observation": task_observation,
            "root": task_root,
        },
    }, None


def _dreamer_sweep_pose_batch(snapshot: dict, task_name: str, bone_id: str, axis_name: str, delta_value: float, baseline_root: dict | None = None) -> dict:
    axis_spec = _dreamer_sweep_axis_spec(axis_name)
    if not axis_spec:
        return {"poses": []}
    field_name, axis_index = axis_spec
    bone_row = _dreamer_mechanics_bone_row(snapshot, bone_id)
    macro_row = _dreamer_mechanics_macro_pose_entry(snapshot, task_name, bone_id)
    current_transform = _dreamer_mechanics_pose_transform(snapshot, bone_id)
    baseline_row = {}
    if isinstance(baseline_root, dict):
        bone_map = baseline_root.get("bone_map") if isinstance(baseline_root.get("bone_map"), dict) else {}
        baseline_row = bone_map.get(str(bone_id or "").strip()) if isinstance(bone_map.get(str(bone_id or "").strip()), dict) else {}
    row = {"bone": bone_id}
    if field_name == "rotation_deg":
        base_rotation = _dreamer_pose_triplet(
            baseline_row.get("rotation_deg"),
            _dreamer_pose_triplet(bone_row.get("rotation_deg"), _dreamer_pose_triplet(macro_row.get("rotation_deg"))),
        )
        next_rotation = list(base_rotation)
        next_rotation[axis_index] = round(base_rotation[axis_index] + float(delta_value), 4)
        row["rotation_deg"] = next_rotation
    else:
        base_offset = _dreamer_pose_triplet(
            baseline_row.get("offset"),
            _dreamer_pose_triplet(
                current_transform.get("offset"),
                _dreamer_pose_triplet(macro_row.get("offset"), _dreamer_pose_triplet(bone_row.get("local_offset"))),
            ),
        )
        next_offset = list(base_offset)
        next_offset[axis_index] = round(base_offset[axis_index] + float(delta_value), 4)
        row["offset"] = {"x": next_offset[0], "y": next_offset[1], "z": next_offset[2]}
    return {"poses": [row]}


def _dreamer_delta_pose_batch(snapshot: dict, task_name: str, selected_action: dict) -> dict:
    pose_delta = selected_action.get("pose_delta") if isinstance(selected_action.get("pose_delta"), dict) else {}
    rotation_delta_map = pose_delta.get("rotation_deg") if isinstance(pose_delta.get("rotation_deg"), dict) else {}
    offset_delta_map = pose_delta.get("offset") if isinstance(pose_delta.get("offset"), dict) else {}
    template = selected_action.get("workbench_set_pose_batch_template") if isinstance(selected_action.get("workbench_set_pose_batch_template"), dict) else {}
    template_poses = template.get("poses") if isinstance(template.get("poses"), list) else []
    template_by_bone = {}
    for row in template_poses:
        if not isinstance(row, dict):
            continue
        bone = str(row.get("bone") or row.get("bone_id") or "").strip()
        if bone:
            template_by_bone[bone] = row
    target_bones = set()
    target_bones.update(str(key).strip() for key in rotation_delta_map.keys())
    target_bones.update(str(key).strip() for key in offset_delta_map.keys())
    poses = []
    for bone_id in sorted(bone for bone in target_bones if bone):
        row = {"bone": bone_id}
        template_row = template_by_bone.get(bone_id) if isinstance(template_by_bone.get(bone_id), dict) else {}
        macro_row = _dreamer_mechanics_macro_pose_entry(snapshot, task_name, bone_id)
        current_transform = _dreamer_mechanics_pose_transform(snapshot, bone_id)
        bone_row = _dreamer_mechanics_bone_row(snapshot, bone_id)
        if bone_id in rotation_delta_map:
            current_rotation = _dreamer_pose_triplet(
                bone_row.get("rotation_deg"),
                _dreamer_pose_triplet(template_row.get("rotation_deg"), _dreamer_pose_triplet(macro_row.get("rotation_deg"))),
            )
            delta_rotation = _dreamer_pose_triplet(rotation_delta_map.get(bone_id), [0.0, 0.0, 0.0])
            row["rotation_deg"] = [round(current_rotation[i] + delta_rotation[i], 4) for i in range(3)]
        if bone_id in offset_delta_map:
            current_offset = _dreamer_pose_triplet(
                current_transform.get("offset"),
                _dreamer_pose_triplet(template_row.get("offset"), _dreamer_pose_triplet(macro_row.get("offset"))),
            )
            delta_offset = _dreamer_pose_triplet(offset_delta_map.get(bone_id), [0.0, 0.0, 0.0])
            row["offset"] = {
                "x": round(current_offset[0] + delta_offset[0], 4),
                "y": round(current_offset[1] + delta_offset[1], 4),
                "z": round(current_offset[2] + delta_offset[2], 4),
            }
        if len(row) > 1:
            poses.append(row)
    if poses:
        return {"poses": poses}
    return _json_clone(template) if isinstance(template, dict) else {"poses": []}


def _dreamer_mechanics_phase_index(route_report: dict, timeline: dict) -> float:
    phase_id = str(route_report.get("active_phase_id") or "").strip()
    if not phase_id:
        return -1.0
    phases = timeline.get("contact_phases") if isinstance(timeline.get("contact_phases"), list) else []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            continue
        if str(phase.get("phase_id") or "").strip() == phase_id:
            return float(index)
    return -1.0


def _dreamer_mechanics_observation_payload(snapshot: dict, updated_ms: int) -> dict:
    workbench = snapshot.get("workbench") if isinstance(snapshot.get("workbench"), dict) else {}
    route_report = workbench.get("route_report") if isinstance(workbench.get("route_report"), dict) else {}
    active_controller = workbench.get("active_controller") if isinstance(workbench.get("active_controller"), dict) else {}
    load_field = workbench.get("load_field") if isinstance(workbench.get("load_field"), dict) else {}
    timeline = snapshot.get("timeline") if isinstance(snapshot.get("timeline"), dict) else {}
    balance = snapshot.get("balance") if isinstance(snapshot.get("balance"), dict) else {}
    contacts = snapshot.get("contacts") if isinstance(snapshot.get("contacts"), list) else []
    blackboard_context = _dreamer_snapshot_blackboard_context(snapshot)
    query_thread = _dreamer_snapshot_query_thread(snapshot)
    oracle_context = _dreamer_snapshot_oracle_context(snapshot)

    lower_leg_l = _dreamer_mechanics_contact_row(contacts, "lower_leg_l")
    foot_r = _dreamer_mechanics_contact_row(contacts, "foot_r")
    balance_mode = str(balance.get("balance_mode") or "").strip().lower()
    intended_support = route_report.get("intended_support_set") if isinstance(route_report.get("intended_support_set"), list) else []
    realized_support = route_report.get("realized_support_set") if isinstance(route_report.get("realized_support_set"), list) else []
    missing_support = route_report.get("missing_support_participants") if isinstance(route_report.get("missing_support_participants"), list) else []

    features = {
        "route": {
            "realized_support_count": len(realized_support),
            "missing_support_count": len(missing_support),
            "intended_support_count": len(intended_support),
            "phase_index": _dreamer_mechanics_phase_index(route_report, timeline),
            "stage_blocked": bool(route_report.get("stage_blocked")),
            "has_active_route": bool(str(route_report.get("status") or "").strip() not in ("", "none")),
            "status": str(route_report.get("status") or "none"),
            "active_phase_id": str(route_report.get("active_phase_id") or ""),
            "active_phase_label": str(route_report.get("active_phase_label") or ""),
            "phase_gate_summary": str(route_report.get("phase_gate_summary") or ""),
        },
        "balance": {
            "stability_risk": _dreamer_mechanics_number(balance.get("stability_risk"), 0.0),
            "stability_margin": _dreamer_mechanics_number(balance.get("stability_margin"), 0.0),
            "normalized_margin": _dreamer_mechanics_number(balance.get("normalized_margin"), 0.0),
            "nearest_edge_distance": _dreamer_mechanics_number(((balance.get("nearest_edge") or {}).get("distance")), 0.0),
            "support_count": int(_dreamer_mechanics_number(balance.get("support_count"), 0.0)),
            "balance_mode": balance_mode or "none",
            "balance_mode_code": int(_DREAMER_BALANCE_MODE_CODES.get(balance_mode or "none", 0)),
            "supporting_joint_ids": list(balance.get("supporting_joint_ids") or []),
            "alert_ids": list(balance.get("alert_ids") or []),
        },
        "controller": {
            "present": bool(active_controller),
            "controller_id": str(active_controller.get("controller_id") or ""),
            "leader_count": len(active_controller.get("leader_bone_ids") or []),
            "anchor_count": len(active_controller.get("anchor_bone_ids") or []),
            "carrier_count": len(active_controller.get("carrier_bone_ids") or []),
        },
        "contacts": {
            "lower_leg_l": {
                "gap": _dreamer_mechanics_number(lower_leg_l.get("gap"), 0.0),
                "manifold_points": int(_dreamer_mechanics_number(lower_leg_l.get("manifold_points"), 0.0)),
                "load_share": _dreamer_mechanics_load_share(load_field, "lower_leg_l"),
                "supporting": bool(lower_leg_l.get("supporting")),
                "state": str(lower_leg_l.get("state") or ""),
            },
            "foot_r": {
                "gap": _dreamer_mechanics_number(foot_r.get("gap"), 0.0),
                "manifold_points": int(_dreamer_mechanics_number(foot_r.get("manifold_points"), 0.0)),
                "load_share": _dreamer_mechanics_load_share(load_field, "foot_r"),
                "supporting": bool(foot_r.get("supporting")),
                "state": str(foot_r.get("state") or ""),
            },
        },
        "pose": {
            "hips_pitch_deg": _dreamer_mechanics_bone_rotation(snapshot, "hips", 0),
            "hips_world_y": _dreamer_mechanics_bone_world(snapshot, "hips", 1),
            "hips_world_z": _dreamer_mechanics_bone_world(snapshot, "hips", 2),
            "spine_pitch_deg": _dreamer_mechanics_bone_rotation(snapshot, "spine", 0),
            "chest_pitch_deg": _dreamer_mechanics_bone_rotation(snapshot, "chest", 0),
            "lower_leg_l_pitch_deg": _dreamer_mechanics_bone_rotation(snapshot, "lower_leg_l", 0),
            "foot_r_yaw_deg": _dreamer_mechanics_bone_rotation(snapshot, "foot_r", 1),
        },
    }

    observation = [
        float(features["route"]["realized_support_count"]),
        float(features["route"]["missing_support_count"]),
        float(features["route"]["intended_support_count"]),
        float(features["route"]["phase_index"]),
        _dreamer_mechanics_flag(features["route"]["stage_blocked"]),
        _dreamer_mechanics_flag(features["route"]["has_active_route"]),
        float(features["balance"]["stability_risk"]),
        float(features["balance"]["stability_margin"]),
        float(features["balance"]["normalized_margin"]),
        float(features["balance"]["nearest_edge_distance"]),
        float(features["balance"]["support_count"]),
        float(features["balance"]["balance_mode_code"]),
        _dreamer_mechanics_flag(features["controller"]["present"]),
        float(features["controller"]["leader_count"]),
        float(features["controller"]["anchor_count"]),
        float(features["controller"]["carrier_count"]),
        float(features["contacts"]["lower_leg_l"]["gap"]),
        float(features["contacts"]["lower_leg_l"]["manifold_points"]),
        float(features["contacts"]["lower_leg_l"]["load_share"]),
        _dreamer_mechanics_flag(features["contacts"]["lower_leg_l"]["supporting"]),
        float(features["contacts"]["foot_r"]["gap"]),
        float(features["contacts"]["foot_r"]["manifold_points"]),
        float(features["contacts"]["foot_r"]["load_share"]),
        _dreamer_mechanics_flag(features["contacts"]["foot_r"]["supporting"]),
        float(features["pose"]["hips_pitch_deg"]),
        float(features["pose"]["hips_world_y"]),
        float(features["pose"]["hips_world_z"]),
        float(features["pose"]["spine_pitch_deg"]),
        float(features["pose"]["chest_pitch_deg"]),
        float(features["pose"]["lower_leg_l_pitch_deg"]),
        float(features["pose"]["foot_r_yaw_deg"]),
    ]

    return {
        "status": "ok",
        "schema_id": _DREAMER_MECHANICS_SCHEMA_ID,
        "obs_source": "text_theater_snapshot",
        "updated_ms": int(updated_ms or 0),
        "observation_size": len(observation),
        "field_names": list(_DREAMER_MECHANICS_FIELDS),
        "observation": observation,
        "features": features,
        "target_task": "half_kneel_l",
        "focus": {
            "object_key": str((((snapshot.get("runtime") or {}).get("object_key")) or "")),
            "mode": str((((snapshot.get("runtime") or {}).get("mode")) or "")),
            "behavior": str((((snapshot.get("runtime") or {}).get("behavior")) or "")),
            "activity": str((((snapshot.get("runtime") or {}).get("activity")) or "")),
        },
        "blackboard": blackboard_context,
        "query_thread": query_thread,
        "oracle_context": oracle_context,
        "correction_table": _json_clone(_DREAMER_KNEEL_CORRECTIONS),
        "mode_legend": {
            "balance_mode_code": _json_clone(_DREAMER_BALANCE_MODE_CODES),
        },
    }


def _dreamer_history_append(key: str, entry: dict, limit: int = 60) -> None:
    if key not in _dreamer_history:
        _dreamer_history[key] = []
    bucket = _dreamer_history.get(key)
    if not isinstance(bucket, list):
        bucket = []
        _dreamer_history[key] = bucket
    bucket.append(entry)
    max_len = max(1, int(limit or 1))
    if len(bucket) > max_len:
        _dreamer_history[key] = bucket[-max_len:]


async def _dreamer_effective_config() -> tuple[dict, str, list[str]]:
    raw_config, source, warnings = await _dreamer_config_load_saved()
    effective, normalized_warnings = _dreamer_config_normalize(raw_config or {})
    merged_warnings = [str(item) for item in (warnings or []) + (normalized_warnings or []) if str(item or "").strip()]
    return effective, source, merged_warnings


def _dreamer_control_plane_view(config: dict | None = None) -> dict:
    cfg = config if isinstance(config, dict) else {}
    control_plane = cfg.get("control_plane") if isinstance(cfg.get("control_plane"), dict) else {}
    overlay = cfg.get("overlay") if isinstance(cfg.get("overlay"), dict) else {}
    return {
        "control_plane": _json_clone(control_plane),
        "overlay": _json_clone(overlay),
    }


def _dreamer_mechanics_current_payload() -> tuple[dict | None, str | None]:
    snapshot, updated_ms = _dreamer_mechanics_live_snapshot()
    if not isinstance(snapshot, dict):
        return None, "No live text theater snapshot available"
    return _dreamer_mechanics_observation_payload(snapshot, updated_ms), None


def _dreamer_mechanics_payload_from_env_control(env_payload: dict | None) -> tuple[dict | None, str | None, dict]:
    payload = env_payload if isinstance(env_payload, dict) else {}
    text_theater = payload.get("text_theater") if isinstance(payload.get("text_theater"), dict) else {}
    snapshot = text_theater.get("snapshot") if isinstance(text_theater.get("snapshot"), dict) else {}
    freshness = text_theater.get("freshness") if isinstance(text_theater.get("freshness"), dict) else {}
    if not isinstance(snapshot, dict) or not snapshot:
        return None, "No text theater snapshot attached to env control result", freshness
    updated_ms = int(snapshot.get("source_timestamp") or snapshot.get("snapshot_timestamp") or 0)
    if not updated_ms:
        updated_ms = int(freshness.get("cache_updated_ms") or 0)
    if not int(updated_ms or 0):
        return None, "Attached text theater snapshot did not include a usable timestamp", freshness
    return _dreamer_mechanics_observation_payload(snapshot, updated_ms), None, freshness


def _dreamer_control_plane_task(config: dict | None = None) -> str:
    control = _dreamer_control_plane_view(config).get("control_plane", {})
    task = str(control.get("task") or "").strip()
    return task or "half_kneel_l"


def _dreamer_correction_table_for_task(task: str = "") -> list[dict]:
    task_key = str(task or "").strip()
    rows = []
    for entry in _DREAMER_KNEEL_CORRECTIONS:
        scope = entry.get("task_scope") if isinstance(entry.get("task_scope"), list) else []
        if task_key and scope and task_key not in scope:
            continue
        rows.append(_json_clone(entry))
    return rows


def _dreamer_pick_contact(payload: dict, joint_id: str) -> dict:
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    contacts = features.get("contacts") if isinstance(features.get("contacts"), dict) else {}
    contact = contacts.get(str(joint_id or "").strip()) if isinstance(contacts.get(str(joint_id or "").strip()), dict) else {}
    return contact


def _dreamer_reward_breakdown(previous_payload: dict, current_payload: dict) -> dict:
    prev_features = previous_payload.get("features") if isinstance(previous_payload.get("features"), dict) else {}
    curr_features = current_payload.get("features") if isinstance(current_payload.get("features"), dict) else {}
    prev_route = prev_features.get("route") if isinstance(prev_features.get("route"), dict) else {}
    curr_route = curr_features.get("route") if isinstance(curr_features.get("route"), dict) else {}
    prev_balance = prev_features.get("balance") if isinstance(prev_features.get("balance"), dict) else {}
    curr_balance = curr_features.get("balance") if isinstance(curr_features.get("balance"), dict) else {}
    prev_knee = _dreamer_pick_contact(previous_payload, "lower_leg_l")
    curr_knee = _dreamer_pick_contact(current_payload, "lower_leg_l")
    prev_foot = _dreamer_pick_contact(previous_payload, "foot_r")
    curr_foot = _dreamer_pick_contact(current_payload, "foot_r")

    prev_gap = _dreamer_mechanics_number(prev_knee.get("gap"), 0.0)
    curr_gap = _dreamer_mechanics_number(curr_knee.get("gap"), 0.0)
    prev_phase = _dreamer_mechanics_number(prev_route.get("phase_index"), -1.0)
    curr_phase = _dreamer_mechanics_number(curr_route.get("phase_index"), -1.0)
    prev_risk = _dreamer_mechanics_number(prev_balance.get("stability_risk"), 0.0)
    curr_risk = _dreamer_mechanics_number(curr_balance.get("stability_risk"), 0.0)
    prev_margin = _dreamer_mechanics_number(prev_balance.get("stability_margin"), 0.0)
    curr_margin = _dreamer_mechanics_number(curr_balance.get("stability_margin"), 0.0)
    prev_manifold = _dreamer_mechanics_number(prev_knee.get("manifold_points"), 0.0) + _dreamer_mechanics_number(prev_foot.get("manifold_points"), 0.0)
    curr_manifold = _dreamer_mechanics_number(curr_knee.get("manifold_points"), 0.0) + _dreamer_mechanics_number(curr_foot.get("manifold_points"), 0.0)
    prev_support = set(prev_balance.get("supporting_joint_ids") or [])
    curr_support = set(curr_balance.get("supporting_joint_ids") or [])
    prev_alerts = set(prev_balance.get("alert_ids") or [])
    curr_alerts = set(curr_balance.get("alert_ids") or [])

    contributions: dict[str, float] = {}

    gap_delta = prev_gap - curr_gap
    if abs(gap_delta) > 0.0001:
        contributions["gap_delta"] = round(max(-2.0, min(2.0, gap_delta * 4.0)), 4)

    phase_delta = curr_phase - prev_phase
    if phase_delta > 0:
        contributions["phase_advance"] = round(min(4.0, phase_delta * 2.0), 4)
    elif phase_delta < 0:
        contributions["phase_regression"] = round(max(-4.0, phase_delta * 1.0), 4)

    new_support = max(0, len(curr_support - prev_support))
    lost_support = max(0, len(prev_support - curr_support))
    if new_support:
        contributions["support_realized"] = round(new_support * 1.5, 4)
    if lost_support:
        contributions["support_lost"] = round(-1.5 * lost_support, 4)

    risk_delta = prev_risk - curr_risk
    if abs(risk_delta) > 0.0001:
        contributions["stability_gain"] = round(max(-2.0, min(2.0, risk_delta * 2.0)), 4)

    margin_delta = curr_margin - prev_margin
    if abs(margin_delta) > 0.0001:
        contributions["margin_gain"] = round(max(-1.5, min(1.5, margin_delta * 0.75)), 4)

    manifold_delta = curr_manifold - prev_manifold
    if abs(manifold_delta) > 0.0001:
        contributions["manifold_gain"] = round(max(-1.0, min(1.0, manifold_delta * 0.2)), 4)

    new_alerts = curr_alerts - prev_alerts
    if "support_penetration" in new_alerts:
        contributions["support_penetration"] = -3.0
    if bool(curr_route.get("stage_blocked")) and not bool(prev_route.get("stage_blocked")):
        contributions["stage_blocked"] = -1.5
    if str(curr_balance.get("balance_mode") or "").strip().lower() == "falling":
        contributions["falling"] = -4.0

    total_reward = round(sum(contributions.values()), 4)
    return {
        "total_reward": total_reward,
        "contributions": contributions,
        "delta": {
            "lower_leg_l_gap": round(gap_delta, 4),
            "phase_index": round(phase_delta, 4),
            "stability_risk": round(risk_delta, 4),
            "stability_margin": round(margin_delta, 4),
            "manifold_points": round(manifold_delta, 4),
            "new_supporting_joints": sorted(curr_support - prev_support),
            "lost_supporting_joints": sorted(prev_support - curr_support),
            "new_alerts": sorted(new_alerts),
        },
    }


def _dreamer_rank_proposals(observation_payload: dict, config: dict | None = None) -> dict:
    task = _dreamer_control_plane_task(config)
    corrections = _dreamer_correction_table_for_task(task)
    features = observation_payload.get("features") if isinstance(observation_payload.get("features"), dict) else {}
    oracle_context = observation_payload.get("oracle_context") if isinstance(observation_payload.get("oracle_context"), dict) else {}
    query_thread = observation_payload.get("query_thread") if isinstance(observation_payload.get("query_thread"), dict) else {}
    balance = features.get("balance") if isinstance(features.get("balance"), dict) else {}
    contacts = features.get("contacts") if isinstance(features.get("contacts"), dict) else {}
    pose = features.get("pose") if isinstance(features.get("pose"), dict) else {}
    knee = contacts.get("lower_leg_l") if isinstance(contacts.get("lower_leg_l"), dict) else {}
    foot = contacts.get("foot_r") if isinstance(contacts.get("foot_r"), dict) else {}
    gap = _dreamer_mechanics_number(knee.get("gap"), 0.0)
    risk = _dreamer_mechanics_number(balance.get("stability_risk"), 0.0)
    margin = _dreamer_mechanics_number(balance.get("stability_margin"), 0.0)
    hips_world_y = _dreamer_mechanics_number(pose.get("hips_world_y"), 0.0)
    load_share = _dreamer_mechanics_number(foot.get("load_share"), 0.0)
    supporting = bool(foot.get("supporting"))
    rotational_grounding = bool(oracle_context.get("rotational_grounding"))
    pan_band = str(oracle_context.get("pan_band") or "")
    contact_bias = str(oracle_context.get("contact_bias") or "")
    support_role = str(oracle_context.get("support_role") or "")
    watch_alerts = {str(item or "").strip().lower() for item in list(oracle_context.get("watch_alerts") or [])[:8]}
    pivot_id = str(query_thread.get("current_pivot_id") or "")

    ranked = []
    for entry in corrections:
        action_key = str(entry.get("action_key") or "")
        score = 0.0
        reasons: list[str] = []

        if gap > 0.2:
            if action_key == "drop_hips":
                score += min(3.2, gap * 4.8)
                reasons.append("left knee gap is still high")
            if action_key == "tuck_lead_knee":
                score += min(2.8, gap * 3.8)
                reasons.append("knee flexion can close the contact gap")
            if action_key == "shift_hips_fore":
                score += 1.2
                reasons.append("carrier projection can move load toward the kneel lane")
            if action_key == "raise_hips":
                score -= 0.8
                reasons.append("raising the carrier would usually widen the kneel gap")

        if risk >= 0.84 or margin < 0:
            if action_key == "widen_anchor_foot":
                score += 2.0
                reasons.append("support polygon is failing and the planted foot can widen it")
            if action_key == "counter_rotate_spine":
                score += 1.4
                reasons.append("upper-body counter-rotation can reduce forward collapse")
            if action_key == "counter_rotate_chest":
                score += 1.2
                reasons.append("chest compensation can stabilize the braced posture")
            if action_key == "shift_hips_aft":
                score += 1.6
                reasons.append("carrier is outside the support polygon")

        if hips_world_y > 5.5 and action_key == "drop_hips":
            score += 0.8
            reasons.append("hips remain visually high for the kneel target")

        if supporting and load_share >= 0.85 and action_key == "widen_anchor_foot":
            score += 0.8
            reasons.append("right foot is carrying nearly all support load")

        if rotational_grounding and action_key == "widen_anchor_foot":
            score += 1.6
            reasons.append("Pan probe says the planted foot is resolving through rotational grounding")

        if contact_bias in {"inverted", "wrong-way"} and action_key == "widen_anchor_foot":
            score += 1.0
            reasons.append("planted foot bias is inverted/wrong-way in the Pan/contact read")

        if support_role == "brace" and action_key in {"counter_rotate_spine", "counter_rotate_chest"}:
            score += 0.8
            reasons.append("Pan probe says the active support role is brace, so upper-body counter-rotation matters")

        if "support risk" in watch_alerts and action_key == "widen_anchor_foot":
            score += 0.7
            reasons.append("output_state watch board is carrying a live support-risk alert")

        if pan_band == "rotational_grounding" and action_key == "widen_anchor_foot":
            score += 0.6
            reasons.append("Pan probe is already in a rotational-grounding band")

        if pivot_id == "operative_memory_alignment" and action_key == "widen_anchor_foot":
            score += 0.2
            reasons.append("current pivot still favors alignment-preserving corrections over larger posture swings")

        if action_key == "raise_hips" and risk < 0.25 and gap < 0.08:
            score += 0.4
            reasons.append("carrier lift only helps if the kneel is already compressed")

        ranked.append({
            "action_id": entry.get("action_id"),
            "action_key": action_key,
            "label": entry.get("label"),
            "summary": entry.get("summary"),
            "score": round(score, 4),
            "reasons": reasons,
            "targets": _json_clone(entry.get("targets") or []),
            "pose_delta": _json_clone(entry.get("pose_delta") or {}),
            "workbench_set_pose_batch_template": _json_clone(entry.get("workbench_set_pose_batch_template") or {}),
        })

    ranked.sort(key=lambda item: (-float(item.get("score") or 0.0), int(item.get("action_id") or 0)))
    best = ranked[0] if ranked else None
    return {
        "proposal_source": "outer_control_plane_heuristic_v1",
        "task": task,
        "ranked_actions": ranked,
        "best_action": _json_clone(best) if isinstance(best, dict) else None,
    }


def _dreamer_compact_observation(payload: dict | None = None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    features = source.get("features") if isinstance(source.get("features"), dict) else {}
    blackboard = source.get("blackboard") if isinstance(source.get("blackboard"), dict) else {}
    query_thread = source.get("query_thread") if isinstance(source.get("query_thread"), dict) else {}
    oracle_context = source.get("oracle_context") if isinstance(source.get("oracle_context"), dict) else {}
    route = features.get("route") if isinstance(features.get("route"), dict) else {}
    balance = features.get("balance") if isinstance(features.get("balance"), dict) else {}
    contacts = features.get("contacts") if isinstance(features.get("contacts"), dict) else {}
    pose = features.get("pose") if isinstance(features.get("pose"), dict) else {}
    knee = contacts.get("lower_leg_l") if isinstance(contacts.get("lower_leg_l"), dict) else {}
    foot = contacts.get("foot_r") if isinstance(contacts.get("foot_r"), dict) else {}
    return {
        "updated_ms": int(source.get("updated_ms") or 0),
        "target_task": str(source.get("target_task") or ""),
        "route": {
            "status": str(route.get("status") or ""),
            "phase_index": _dreamer_mechanics_number(route.get("phase_index"), -1.0),
            "stage_blocked": bool(route.get("stage_blocked")),
        },
        "balance": {
            "stability_risk": _dreamer_mechanics_number(balance.get("stability_risk"), 0.0),
            "stability_margin": _dreamer_mechanics_number(balance.get("stability_margin"), 0.0),
            "balance_mode": str(balance.get("balance_mode") or ""),
            "supporting_joint_ids": list(balance.get("supporting_joint_ids") or []),
            "alert_ids": list(balance.get("alert_ids") or []),
        },
        "contacts": {
            "lower_leg_l": {
                "gap": _dreamer_mechanics_number(knee.get("gap"), 0.0),
                "state": str(knee.get("state") or ""),
                "supporting": bool(knee.get("supporting")),
                "manifold_points": int(_dreamer_mechanics_number(knee.get("manifold_points"), 0.0)),
            },
            "foot_r": {
                "gap": _dreamer_mechanics_number(foot.get("gap"), 0.0),
                "state": str(foot.get("state") or ""),
                "supporting": bool(foot.get("supporting")),
                "load_share": _dreamer_mechanics_number(foot.get("load_share"), 0.0),
                "manifold_points": int(_dreamer_mechanics_number(foot.get("manifold_points"), 0.0)),
            },
        },
        "pose": {
            "hips_world_y": _dreamer_mechanics_number(pose.get("hips_world_y"), 0.0),
            "hips_world_z": _dreamer_mechanics_number(pose.get("hips_world_z"), 0.0),
            "lower_leg_l_pitch_deg": _dreamer_mechanics_number(pose.get("lower_leg_l_pitch_deg"), 0.0),
            "foot_r_yaw_deg": _dreamer_mechanics_number(pose.get("foot_r_yaw_deg"), 0.0),
        },
        "blackboard": {
            "row_count": int(blackboard.get("row_count") or 0),
            "lead_row_ids": list(blackboard.get("lead_row_ids") or []),
            "families": list(blackboard.get("families") or []),
        },
        "sequence": {
            "sequence_id": str(query_thread.get("sequence_id") or ""),
            "segment_id": str(query_thread.get("segment_id") or ""),
            "session_id": str(query_thread.get("session_id") or ""),
            "subject_key": str(query_thread.get("subject_key") or ""),
            "status": str(query_thread.get("status") or ""),
            "current_pivot_id": str(query_thread.get("current_pivot_id") or ""),
            "objective_label": str(query_thread.get("objective_label") or query_thread.get("objective_id") or ""),
        },
        "oracle": {
            "summary": str(oracle_context.get("summary") or ""),
            "equilibrium_band": str(oracle_context.get("equilibrium_band") or oracle_context.get("equilibrium_state") or ""),
            "equilibrium_state": str(oracle_context.get("equilibrium_state") or ""),
            "technolit_band": str(oracle_context.get("technolit_band") or ""),
            "technolit_symbol": str(oracle_context.get("technolit_symbol") or ""),
            "technolit_summary": str(oracle_context.get("technolit_summary") or ""),
            "technolit_flow_posture": str(oracle_context.get("technolit_flow_posture") or ""),
            "technolit_distribution_posture": str(oracle_context.get("technolit_distribution_posture") or ""),
            "technolit_burn_gate": str(oracle_context.get("technolit_burn_gate") or ""),
            "technolit_creator_rewards_unclaimed_sol": oracle_context.get("technolit_creator_rewards_unclaimed_sol"),
            "watch_band": str(oracle_context.get("watch_band") or oracle_context.get("watch_status") or ""),
            "watch_status": str(oracle_context.get("watch_status") or ""),
            "watch_alerts": list(oracle_context.get("watch_alerts") or []),
            "attention_band": str(oracle_context.get("attention_band") or ""),
            "attention_kind": str(oracle_context.get("attention_kind") or ""),
            "attention_target": str(oracle_context.get("attention_target") or ""),
            "attention_why_now": str(oracle_context.get("attention_why_now") or ""),
            "attention_expected_read": str(oracle_context.get("attention_expected_read") or ""),
            "attention_hold_candidate": bool(oracle_context.get("attention_hold_candidate")),
            "field_settling_band": str(oracle_context.get("field_settling_band") or oracle_context.get("field_settle_band") or ""),
            "pan_band": str(oracle_context.get("pan_band") or ""),
            "rotational_grounding": bool(oracle_context.get("rotational_grounding")),
            "contact_bias": str(oracle_context.get("contact_bias") or ""),
            "support_role": str(oracle_context.get("support_role") or ""),
            "placement": {
                "subject": str(oracle_context.get("placement_subject") or ""),
                "objective": str(oracle_context.get("placement_objective") or ""),
                "seam": str(oracle_context.get("placement_seam") or ""),
            },
        },
    }


async def _dreamer_dispatch_env_control(args: dict, *, source: str = "webui", client_id: str | None = None) -> tuple[dict | None, str | None]:
    env_control_proxy_payload = _env_control_local_proxy_payload(args)
    if env_control_proxy_payload is None:
        return None, "Command is not an environment-control proxy command"
    before_live_cache = _env_live_cache_snapshot()
    before_updated_ms = int((before_live_cache or {}).get("updated_ms") or 0)
    err_msg = env_control_proxy_payload.get("error") if isinstance(env_control_proxy_payload, dict) else None
    _broadcast_activity("env_control", args, env_control_proxy_payload, 0, err_msg, source=source, client_id=client_id)
    payload = await _env_control_attach_text_theater_observation(
        env_control_proxy_payload,
        args=args,
        before_updated_ms=before_updated_ms,
    )
    return payload, err_msg


def _dreamer_select_ranked_action(ranked_actions: list[dict] | None, action_key: str = "", action_id=None) -> tuple[dict | None, str | None]:
    rows = ranked_actions if isinstance(ranked_actions, list) else []
    key = str(action_key or "").strip()
    wanted_id = None
    if action_id is not None and str(action_id).strip() != "":
        try:
            wanted_id = int(action_id)
        except Exception:
            return None, "Invalid action_id"
    if key:
        for entry in rows:
            if str((entry or {}).get("action_key") or "").strip() == key:
                return _json_clone(entry), None
        return None, f"Unknown action_key '{key}'"
    if wanted_id is not None:
        for entry in rows:
            try:
                entry_id = int((entry or {}).get("action_id"))
            except Exception:
                entry_id = None
            if entry_id == wanted_id:
                return _json_clone(entry), None
        return None, f"Unknown action_id '{wanted_id}'"
    if rows:
        return _json_clone(rows[0]), None
    return None, "No ranked actions available"


def _dreamer_config_default_value(section: str, key: str):
    section_defaults = _dreamer_config_defaults.get(section)
    if not isinstance(section_defaults, dict):
        return None
    return _json_clone(section_defaults.get(key))


def _dreamer_config_coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _dreamer_config_coerce_scalar(section: str, key: str, value, spec: dict, warnings: list[str]):
    default = _dreamer_config_default_value(section, key)
    kind = str(spec.get("type") or "float").strip().lower()
    if kind == "bool":
        return _dreamer_config_coerce_bool(value, bool(default))
    if kind == "string":
        text = str(value if value is not None else "").strip()
        if not text:
            if default is not None:
                warnings.append(f"{section}.{key}: blank value; using default {default!r}")
            return str(default or "")
        max_len = spec.get("max_len")
        if max_len is not None and len(text) > int(max_len):
            warnings.append(f"{section}.{key}: trimmed to max_len {max_len}")
            text = text[: int(max_len)]
        return text
    if kind == "enum":
        options = [str(item or "").strip() for item in (spec.get("options") or []) if str(item or "").strip()]
        fallback = str(default or "")
        candidate = str(value if value is not None else "").strip()
        if not candidate:
            if fallback:
                warnings.append(f"{section}.{key}: blank value; using default {fallback!r}")
            return fallback
        if options and candidate not in options:
            warnings.append(f"{section}.{key}: invalid option {candidate!r}; using default {fallback!r}")
            return fallback
        return candidate
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{section}.{key}: invalid value {value!r}; using default {default!r}")
        numeric = float(default if default is not None else 0)
    minimum = spec.get("min")
    maximum = spec.get("max")
    if minimum is not None and numeric < float(minimum):
        warnings.append(f"{section}.{key}: clamped {numeric} to min {minimum}")
        numeric = float(minimum)
    if maximum is not None and numeric > float(maximum):
        warnings.append(f"{section}.{key}: clamped {numeric} to max {maximum}")
        numeric = float(maximum)
    if kind == "int":
        return int(round(numeric))
    return float(numeric)


def _dreamer_config_normalize(raw_config) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    source = raw_config if isinstance(raw_config, dict) else {}
    effective = {}
    known_sections = set(_DREAMER_CONFIG_EDITABLE_SCHEMA.keys()) | set(_DREAMER_CONFIG_READ_ONLY_SECTIONS)

    if source and not isinstance(raw_config, dict):
        warnings.append("config root was not an object; using defaults")
    for section in sorted(set(source.keys()) - known_sections):
        warnings.append(f"unknown section ignored: {section}")

    for section, schema in _DREAMER_CONFIG_EDITABLE_SCHEMA.items():
        raw_section = source.get(section)
        section_input = raw_section if isinstance(raw_section, dict) else {}
        if raw_section is not None and not isinstance(raw_section, dict):
            warnings.append(f"{section}: expected object; using defaults")
        for key in sorted(set(section_input.keys()) - set(schema.keys())):
            warnings.append(f"unknown key ignored: {section}.{key}")
        effective[section] = {}
        for key, spec in schema.items():
            candidate = section_input.get(key, _dreamer_config_default_value(section, key))
            effective[section][key] = _dreamer_config_coerce_scalar(section, key, candidate, spec, warnings)

    effective["architecture"] = _json_clone(_dreamer_config_defaults.get("architecture") or {})
    if "architecture" in source:
        warnings.append("architecture is read-only and was ignored")
    return effective, warnings


def _dreamer_config_editable_view(config: dict) -> dict:
    editable = {}
    for section in _DREAMER_CONFIG_EDITABLE_SCHEMA.keys():
        if isinstance(config.get(section), dict):
            editable[section] = _json_clone(config.get(section) or {})
    return editable


async def _dreamer_config_load_saved() -> tuple[dict | None, str, list[str]]:
    warnings: list[str] = []
    result = await _call_tool("bag_get", {"key": "dreamer_config"})
    parsed = _parse_mcp_result(result.get("result"))
    if parsed and isinstance(parsed, dict) and "value" in parsed:
        try:
            loaded = json.loads(parsed["value"])
            if isinstance(loaded, dict):
                return loaded, "bag", warnings
            warnings.append("saved dreamer_config was not an object; using defaults")
        except (json.JSONDecodeError, TypeError) as exc:
            warnings.append(f"saved dreamer_config was unreadable: {type(exc).__name__}")
    return None, "defaults", warnings


async def _dreamer_runtime_meta() -> dict:
    now = time.time()
    cached = _dreamer_cache["data"] if _dreamer_cache["data"] and now - _dreamer_cache["ts"] < 3 else None
    if isinstance(cached, dict):
        dreamer = cached.get("dreamer") if isinstance(cached.get("dreamer"), dict) else {}
        rssm_view = cached.get("rssm") if isinstance(cached.get("rssm"), dict) else {}
    else:
        status_raw = await _call_tool("get_status", {})
        rssm_raw = await _call_tool("show_rssm", {})
        status = _parse_mcp_result(status_raw.get("result")) or {}
        rssm = _parse_mcp_result(rssm_raw.get("result")) or {}
        dreamer = status.get("dreamer") if isinstance(status.get("dreamer"), dict) else {}
        if isinstance(rssm, dict):
            rssm_view = rssm.get("metrics", {}).get("other", rssm)
        else:
            rssm_view = {}
    return {
        "action_dim": rssm_view.get("action_dim"),
        "deter_dim": rssm_view.get("deter_dim"),
        "stoch_dim": rssm_view.get("stoch_dim"),
        "stoch_classes": rssm_view.get("stoch_classes"),
        "total_latent": rssm_view.get("total_latent"),
        "imagine_horizon": rssm_view.get("imagine_horizon"),
        "obs_buffer_size": dreamer.get("obs_buffer_size"),
        "reward_buffer_size": dreamer.get("reward_buffer_size"),
        "reward_count": dreamer.get("reward_count"),
        "training_cycles": dreamer.get("training_cycles"),
        "has_real_rssm": dreamer.get("has_real_rssm"),
    }


async def _dreamer_config_payload(raw_config, source: str, extra_warnings: list[str] | None = None) -> dict:
    effective, warnings = _dreamer_config_normalize(raw_config or {})
    if extra_warnings:
        warnings.extend([str(item) for item in extra_warnings if str(item or "").strip()])
    runtime = await _dreamer_runtime_meta()
    return {
        "config": effective,
        "effective_config": _json_clone(effective),
        "saved_config": _dreamer_config_editable_view(effective),
        "source": source,
        "schema_version": _DREAMER_CONFIG_SCHEMA_VERSION,
        "editable_sections": list(_DREAMER_CONFIG_EDITABLE_SCHEMA.keys()),
        "editable_schema": _json_clone(_DREAMER_CONFIG_EDITABLE_SCHEMA),
        "read_only_sections": list(_DREAMER_CONFIG_READ_ONLY_SECTIONS),
        "warnings": warnings,
        "runtime": runtime,
    }


@app.get("/api/dreamer/mechanics_obs")
async def dreamer_mechanics_obs():
    """Return a compact mechanics observation vector plus the first-kneel correction vocabulary."""
    snapshot, updated_ms = _dreamer_mechanics_live_snapshot()
    if not isinstance(snapshot, dict):
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "schema_id": _DREAMER_MECHANICS_SCHEMA_ID,
                "error": "No live text theater snapshot available",
                "obs_source": "text_theater_snapshot",
            },
        )
    return _dreamer_mechanics_observation_payload(snapshot, updated_ms)


@app.get("/api/dreamer/transform_relay")
async def dreamer_transform_relay(task: str = "", bones: str = ""):
    cached = _env_live_cache_snapshot()
    gate_payload = _env_shared_state_prereq_payload("shared_state", cached)
    if isinstance(gate_payload, dict) and str(gate_payload.get("status") or "").lower() == "error":
        return JSONResponse(status_code=428, content=gate_payload)
    snapshot, updated_ms = _dreamer_mechanics_live_snapshot()
    if not isinstance(snapshot, dict):
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "schema_id": _DREAMER_TRANSFORM_RELAY_SCHEMA_ID,
                "error": "No live text theater snapshot available",
                "obs_source": "text_theater_snapshot",
            },
        )
    task_name = str(task or "").strip() or "half_kneel_l"
    payload = _dreamer_transform_relay_payload(snapshot, updated_ms, task_name, bones)
    payload["gate"] = {
        "theater_first_satisfied": True,
        "required_sequence": [
            "env_read(query='text_theater_view', view='render', diagnostics=true) or env_read(query='text_theater_embodiment')",
            "env_control(command='capture_supercam')",
            "env_read(query='supercam')",
            "env_read(query='text_theater_snapshot')",
            "env_report(report_id='route_stability_diagnosis')",
            "env_read(query='shared_state')",
        ],
    }
    return payload


@app.post("/api/dreamer/bounded_sweep")
async def dreamer_bounded_sweep(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    cached = _env_live_cache_snapshot()
    gate_payload = _env_shared_state_prereq_payload("shared_state", cached)
    if isinstance(gate_payload, dict) and str(gate_payload.get("status") or "").lower() == "error":
        return JSONResponse(status_code=428, content=gate_payload)

    task_name = str(body.get("task") or "half_kneel_l").strip() or "half_kneel_l"
    bone_id = str(body.get("bone_id") or body.get("bone") or "").strip()
    axis_name = str(body.get("axis") or "").strip().lower()
    axis_spec = _dreamer_sweep_axis_spec(axis_name)
    if not bone_id or not axis_spec:
        payload = {
            "status": "error",
            "error": "bone_id and axis are required",
            "supported_axes": ["rotation_x", "rotation_y", "rotation_z", "offset_x", "offset_y", "offset_z"],
        }
        _broadcast_activity("dreamer_bounded_sweep", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=400, content=payload)

    start = _dreamer_mechanics_number(body.get("start"), 0.0)
    stop = _dreamer_mechanics_number(body.get("stop"), start)
    step = _dreamer_mechanics_number(body.get("step"), 0.0)
    actor = str(body.get("actor", "assistant") or "assistant").strip() or "assistant"
    values = _dreamer_sweep_values(start, stop, step)
    if len(values) > 25:
        values = values[:25]

    calibration_anchors, baseline_err = await _dreamer_capture_calibration_anchors(
        task_name,
        source=source,
        client_id=client_id,
        actor=actor,
        focus_bones=[bone_id],
    )
    if baseline_err or not isinstance(calibration_anchors, dict):
        payload = {
            "status": "error",
            "error": baseline_err,
            "task": task_name,
            "bone_id": bone_id,
            "axis": axis_name,
        }
        _broadcast_activity("dreamer_bounded_sweep", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=503, content=payload)

    task_anchor = calibration_anchors.get("task_root") if isinstance(calibration_anchors.get("task_root"), dict) else {}
    baseline_snapshot, baseline_updated_ms = _dreamer_mechanics_live_snapshot()
    if not isinstance(baseline_snapshot, dict):
        payload = {
            "status": "unavailable",
            "error": "No live text theater snapshot available",
            "task": task_name,
            "bone_id": bone_id,
            "axis": axis_name,
        }
        _broadcast_activity("dreamer_bounded_sweep", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=503, content=payload)
    baseline_observation = task_anchor.get("observation") if isinstance(task_anchor.get("observation"), dict) else _dreamer_mechanics_observation_payload(baseline_snapshot, baseline_updated_ms)
    baseline_root = task_anchor.get("root") if isinstance(task_anchor.get("root"), dict) else _dreamer_calibration_root(baseline_snapshot, task_name, [bone_id])

    sweep_rows = []
    for delta_value in values:
        restore_result, restore_err = await _dreamer_restore_task_baseline(task_name, source=source, client_id=client_id, actor=actor)
        if restore_err:
            sweep_rows.append({
                "delta_value": delta_value,
                "status": "error",
                "error": restore_err,
            })
            continue
        restore_macro = restore_result.get("macro") if isinstance(restore_result, dict) and isinstance(restore_result.get("macro"), dict) else {}
        restore_text = restore_macro.get("text_theater") if isinstance(restore_macro.get("text_theater"), dict) else {}
        restore_snapshot = restore_text.get("snapshot") if isinstance(restore_text.get("snapshot"), dict) else {}
        restore_boundary_ms = int(
            restore_snapshot.get("source_timestamp")
            or restore_snapshot.get("snapshot_timestamp")
            or ((restore_text.get("freshness") if isinstance(restore_text.get("freshness"), dict) else {}).get("cache_updated_ms") or 0)
        )
        current_snapshot, current_updated_ms = await _dreamer_capture_stable_snapshot(restore_boundary_ms)
        if not isinstance(current_snapshot, dict):
            sweep_rows.append({
                "delta_value": delta_value,
                "status": "unavailable",
                "error": "No live text theater snapshot available",
            })
            continue
        pose_batch = _dreamer_sweep_pose_batch(current_snapshot, task_name, bone_id, axis_name, delta_value, baseline_root=baseline_root)
        poses = pose_batch.get("poses") if isinstance(pose_batch.get("poses"), list) else []
        if not poses:
            sweep_rows.append({
                "delta_value": delta_value,
                "status": "error",
                "error": "No pose batch generated for sweep step",
            })
            continue
        env_payload, env_err = await _dreamer_dispatch_env_control({
            "command": "workbench_set_pose_batch",
            "target_id": json.dumps(pose_batch),
            "actor": actor,
            "include_full": False,
        }, source=source, client_id=client_id)
        if env_err:
            sweep_rows.append({
                "delta_value": delta_value,
                "status": "error",
                "error": env_err,
                "pose_batch": pose_batch,
            })
            continue
        after_payload, after_err, after_freshness = _dreamer_mechanics_payload_from_env_control(env_payload)
        if after_err or not isinstance(after_payload, dict):
            sweep_rows.append({
                "delta_value": delta_value,
                "status": "partial",
                "error": after_err or "No post-step mechanics observation available",
                "pose_batch": pose_batch,
                "env_control": env_payload,
            })
            continue
        cache_advanced = bool(after_freshness.get("cache_advanced_after_command"))
        matched_sync = bool(after_freshness.get("matched_command_sync"))
        reward_breakdown = _dreamer_reward_breakdown(baseline_observation, after_payload)
        row_status = "ok"
        row_error = None
        if not cache_advanced:
            row_status = "stale"
            row_error = "Post-step text theater cache did not advance after sweep command"
        sweep_rows.append({
            "delta_value": round(delta_value, 4),
            "status": row_status,
            "error": row_error,
            "pose_batch": pose_batch,
            "reward_breakdown": reward_breakdown,
            "after": _dreamer_compact_observation(after_payload),
            "freshness": _json_clone(after_freshness),
        })

    await _dreamer_restore_task_baseline(task_name, source=source, client_id=client_id, actor=actor)
    best_row = None
    ok_rows = [row for row in sweep_rows if isinstance(row, dict) and str(row.get("status") or "").lower() == "ok"]
    if ok_rows:
        best_row = max(ok_rows, key=lambda row: float(((row.get("reward_breakdown") or {}).get("total_reward") or 0.0)))
    payload = {
        "status": "ok",
        "schema_id": _DREAMER_BOUNDED_SWEEP_SCHEMA_ID,
        "summary": f"Ran bounded sweep for {bone_id} {axis_name} on task {task_name}.",
            "task": task_name,
            "bone_id": bone_id,
            "axis": axis_name,
            "values": values,
            "neutral_baseline": _dreamer_compact_observation((calibration_anchors.get("neutral") or {}).get("observation")),
            "baseline": _dreamer_compact_observation(baseline_observation),
            "neutral_root": _json_clone((calibration_anchors.get("neutral") or {}).get("root")),
            "baseline_root": _json_clone(baseline_root),
            "restore": task_anchor.get("restore"),
            "steps": sweep_rows,
            "best_step": _json_clone(best_row),
    }
    _broadcast_activity("dreamer_bounded_sweep", body, payload, 0, None, source=source, client_id=client_id)
    return payload


@app.get("/api/dreamer/proposal_preview")
async def dreamer_proposal_preview(limit: int = 5):
    limit = max(1, min(int(limit or 5), 16))
    effective, config_source, warnings = await _dreamer_effective_config()
    observation_payload, err = _dreamer_mechanics_current_payload()
    if err:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "error": err,
                "control_plane": _dreamer_control_plane_view(effective),
                "config_source": config_source,
                "warnings": warnings,
            },
        )
    ranked_payload = _dreamer_rank_proposals(observation_payload, effective)
    ranked_actions = ranked_payload.get("ranked_actions") if isinstance(ranked_payload.get("ranked_actions"), list) else []
    best_action = ranked_payload.get("best_action") if isinstance(ranked_payload.get("best_action"), dict) else None
    return {
        "status": "ok",
        "proposal_source": str(ranked_payload.get("proposal_source") or "outer_control_plane_heuristic_v1"),
        "task": str(ranked_payload.get("task") or _dreamer_control_plane_task(effective)),
        "config_source": config_source,
        "warnings": warnings,
        "control_plane": _dreamer_control_plane_view(effective),
        "current_observation": _dreamer_compact_observation(observation_payload),
        "available_actions": len(ranked_actions),
        "best_action": _json_clone(best_action),
        "ranked_actions": _json_clone(ranked_actions[:limit]),
    }


@app.post("/api/dreamer/episode_reset")
async def dreamer_episode_reset(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    cleared = {
        "mechanics_rewards": len(_dreamer_history.get("mechanics_rewards") or []),
        "episode_steps": len(_dreamer_history.get("episode_steps") or []),
    }
    _dreamer_history["mechanics_rewards"] = []
    _dreamer_history["episode_steps"] = []
    payload = {
        "status": "ok",
        "summary": "Cleared bounded Dreamer episode trail.",
        "cleared": cleared,
        "history": {
            "mechanics_rewards": 0,
            "episode_steps": 0,
        },
    }
    _broadcast_activity("dreamer_episode_reset", {}, payload, 0, None, source=source, client_id=client_id)
    return payload


@app.post("/api/dreamer/episode_step")
async def dreamer_episode_step(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}

    effective, config_source, warnings = await _dreamer_effective_config()
    snapshot, updated_ms = _dreamer_mechanics_live_snapshot()
    if not isinstance(snapshot, dict):
        payload = {
            "status": "unavailable",
            "error": "No mechanics observation available",
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "warnings": warnings,
        }
        _broadcast_activity("dreamer_episode_step", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=503, content=payload)
    before_payload = _dreamer_mechanics_observation_payload(snapshot, updated_ms)

    task_name = _dreamer_control_plane_task(effective)
    try:
        await _call_tool("observe", {
            "signal_type": "mechanics_v1",
            "data": json.dumps({
                "schema_id": _DREAMER_MECHANICS_SCHEMA_ID,
                "task": task_name,
                "payload": before_payload,
                "ts": time.time(),
            }, ensure_ascii=False),
        })
    except Exception:
        pass

    ranked_payload = _dreamer_rank_proposals(before_payload, effective)
    ranked_actions = ranked_payload.get("ranked_actions") if isinstance(ranked_payload.get("ranked_actions"), list) else []
    selected_action, selection_error = _dreamer_select_ranked_action(
        ranked_actions,
        action_key=body.get("action_key"),
        action_id=body.get("action_id"),
    )
    if selection_error or not isinstance(selected_action, dict):
        payload = {
            "status": "error",
            "error": selection_error or "No ranked action available",
            "proposal_source": str(ranked_payload.get("proposal_source") or "outer_control_plane_heuristic_v1"),
            "task": str(ranked_payload.get("task") or _dreamer_control_plane_task(effective)),
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "warnings": warnings,
            "current_observation": _dreamer_compact_observation(before_payload),
            "ranked_actions": _json_clone(ranked_actions[:5]),
        }
        _broadcast_activity("dreamer_episode_step", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=400, content=payload)

    pose_batch_template = _dreamer_delta_pose_batch(snapshot, task_name, selected_action)
    poses = pose_batch_template.get("poses") if isinstance(pose_batch_template.get("poses"), list) else []
    if not poses:
        payload = {
            "status": "error",
            "error": "Selected action has no pose batch template",
            "selected_action": _json_clone(selected_action),
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "warnings": warnings,
        }
        _broadcast_activity("dreamer_episode_step", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=400, content=payload)

    actor = str(body.get("actor", "assistant") or "assistant").strip() or "assistant"
    env_args = {
        "command": "workbench_set_pose_batch",
        "target_id": json.dumps(pose_batch_template),
        "actor": actor,
        "include_full": False,
    }
    env_payload, env_err = await _dreamer_dispatch_env_control(env_args, source=source, client_id=client_id)
    if env_err or not isinstance(env_payload, dict):
        payload = {
            "status": "error",
            "error": env_err or "Failed to dispatch workbench_set_pose_batch",
            "selected_action": _json_clone(selected_action),
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "warnings": warnings,
        }
        _broadcast_activity("dreamer_episode_step", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=503, content=payload)

    after_payload, after_err = _dreamer_mechanics_current_payload()
    if after_err or not isinstance(after_payload, dict):
        payload = {
            "status": "partial",
            "error": after_err or "No post-step mechanics observation available",
            "selected_action": _json_clone(selected_action),
            "env_control": env_payload,
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "warnings": warnings,
        }
        _broadcast_activity("dreamer_episode_step", body, payload, 0, payload.get("error"), source=source, client_id=client_id)
        return JSONResponse(status_code=503, content=payload)

    reward_breakdown = _dreamer_reward_breakdown(before_payload, after_payload)
    event_ts = time.time()
    reward_row = {
        "ts": event_ts,
        "task": str(ranked_payload.get("task") or task_name),
        "action_key": str(selected_action.get("action_key") or ""),
        "total_reward": float(reward_breakdown.get("total_reward") or 0.0),
        "contributions": _json_clone(reward_breakdown.get("contributions") or {}),
    }
    step_row = {
        "ts": event_ts,
        "task": str(ranked_payload.get("task") or task_name),
        "action_id": selected_action.get("action_id"),
        "action_key": str(selected_action.get("action_key") or ""),
        "label": str(selected_action.get("label") or selected_action.get("action_key") or "action"),
        "score": float(selected_action.get("score") or 0.0),
        "total_reward": float(reward_breakdown.get("total_reward") or 0.0),
        "before": _dreamer_compact_observation(before_payload),
        "after": _dreamer_compact_observation(after_payload),
        "delta": _json_clone(reward_breakdown.get("delta") or {}),
    }
    try:
        await _call_tool("observe", {
            "signal_type": "mechanics_reward",
            "data": json.dumps(reward_row, ensure_ascii=False),
        })
    except Exception:
        pass
    _dreamer_history_append("mechanics_rewards", reward_row, limit=120)
    _dreamer_history_append("episode_steps", step_row, limit=80)

    payload = {
        "status": "ok",
        "summary": f"Applied bounded Dreamer action {selected_action.get('action_key') or 'action'} through workbench_set_pose_batch.",
        "proposal_source": str(ranked_payload.get("proposal_source") or "outer_control_plane_heuristic_v1"),
        "task": str(ranked_payload.get("task") or _dreamer_control_plane_task(effective)),
        "control_plane": _dreamer_control_plane_view(effective),
        "config_source": config_source,
        "warnings": warnings,
        "selected_action": _json_clone(selected_action),
        "current_observation": _dreamer_compact_observation(before_payload),
        "next_observation": _dreamer_compact_observation(after_payload),
        "reward_breakdown": reward_breakdown,
        "env_control": env_payload,
        "history_sizes": {
            "mechanics_rewards": len(_dreamer_history.get("mechanics_rewards") or []),
            "episode_steps": len(_dreamer_history.get("episode_steps") or []),
        },
    }
    _broadcast_activity("dreamer_episode_step", body, payload, 0, None, source=source, client_id=client_id)
    return payload


async def _dreamer_refresh_state(force: bool = False, include_weights: bool = True) -> dict:
    """Refresh aggregated Dreamer state and maintain a server-side trail independent of tab visibility."""
    global _dreamer_last_cycle
    now = time.time()

    async with _dreamer_fetch_lock:
        if not force and _dreamer_cache["data"] and now - _dreamer_cache["ts"] < 3:
            return _dreamer_cache["data"]

        status_raw = await _call_tool("get_status", {})
        rssm_raw = await _call_tool("show_rssm", {})
        if include_weights:
            weights_raw = await _call_tool("show_weights", {})
            lora_raw = await _call_tool("show_lora", {})
            weights = _parse_mcp_result(weights_raw.get("result")) or {}
            lora = _parse_mcp_result(lora_raw.get("result")) or {}
        else:
            cached = _dreamer_cache["data"] if isinstance(_dreamer_cache.get("data"), dict) else {}
            weights = cached.get("weights") if isinstance(cached.get("weights"), dict) else {}
            lora = cached.get("lora") if isinstance(cached.get("lora"), dict) else {}

        status = _parse_mcp_result(status_raw.get("result")) or {}
        rssm = _parse_mcp_result(rssm_raw.get("result")) or {}
        dreamer = status.get("dreamer", {}) if isinstance(status, dict) else {}
        effective, config_source, config_warnings = await _dreamer_effective_config()
        current_payload, current_error = _dreamer_mechanics_current_payload()
        ranked_payload = _dreamer_rank_proposals(current_payload, effective) if isinstance(current_payload, dict) else {}

        cycles = dreamer.get("training_cycles", 0)
        if cycles > _dreamer_last_cycle and dreamer.get("last_train"):
            lt = dreamer["last_train"]
            _dreamer_history["critic_loss"].append({
                "ts": now,
                "cycle": cycles,
                "baseline": lt.get("critic_baseline_loss"),
                "perturbed": lt.get("critic_perturbed_loss"),
                "accepted": lt.get("accepted"),
            })
            if len(_dreamer_history["critic_loss"]) > 200:
                _dreamer_history["critic_loss"] = _dreamer_history["critic_loss"][-200:]
            _dreamer_last_cycle = cycles

        _dreamer_history["reward_counts"].append({"ts": now, "count": dreamer.get("reward_count", 0)})
        _dreamer_history["fitness"].append({"ts": now, "value": dreamer.get("fitness", 0)})
        for key in ("reward_counts", "fitness"):
            if len(_dreamer_history[key]) > 200:
                _dreamer_history[key] = _dreamer_history[key][-200:]

        if isinstance(rssm, dict):
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
            "history_source": "server_sampler",
            "history_updated_ts": now,
            "control_plane": _dreamer_control_plane_view(effective),
            "config_source": config_source,
            "config_warnings": list(config_warnings or []),
            "current_observation": _dreamer_compact_observation(current_payload),
            "current_observation_error": str(current_error or ""),
            "oracle_context": _json_clone((current_payload or {}).get("oracle_context") or {}),
            "query_thread": _json_clone((current_payload or {}).get("query_thread") or {}),
            "ranked_actions_preview": _json_clone((ranked_payload.get("ranked_actions") if isinstance(ranked_payload, dict) else [])[:3]),
        }
        _dreamer_cache["data"] = result
        _dreamer_cache["ts"] = now
        return result


async def _dreamer_sampler_loop():
    while True:
        try:
            await _dreamer_refresh_state(force=True, include_weights=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[WARN] Dreamer sampler failed: {exc}")
        await asyncio.sleep(5)


@app.get("/api/dreamer/state")
async def dreamer_state():
    """Aggregated Dreamer state for the dashboard.
    History is advanced by a background sampler so the tab has useful context on arrival."""
    return await _dreamer_refresh_state(force=False, include_weights=True)


@app.get("/api/dreamer/config")
async def dreamer_config_get():
    """Load Dreamer config with validation, coercion, and runtime/read-only metadata."""
    raw_config, source, warnings = await _dreamer_config_load_saved()
    return await _dreamer_config_payload(raw_config, source, warnings)


@app.get("/api/dreamer/config/effective")
async def dreamer_config_effective():
    """Alias for the normalized Dreamer config payload."""
    raw_config, source, warnings = await _dreamer_config_load_saved()
    return await _dreamer_config_payload(raw_config, source, warnings)


@app.post("/api/dreamer/config")
async def dreamer_config_save(request: Request):
    """Validate and save Dreamer config to FelixBag."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    config = body.get("config", body) if isinstance(body, dict) else body
    effective, warnings = _dreamer_config_normalize(config if isinstance(config, dict) else {})
    persistable = _dreamer_config_editable_view(effective)
    result = await _call_tool("bag_induct", {
        "key": "dreamer_config",
        "content": json.dumps(persistable),
        "item_type": "config"
    })
    parsed = _parse_mcp_result(result.get("result"))
    payload = await _dreamer_config_payload(persistable, "bag", warnings)
    payload["status"] = "saved"
    payload["result"] = parsed
    return payload


@app.post("/api/dreamer/config/reset")
async def dreamer_config_reset():
    """Reset Dreamer config to defaults and return the normalized payload."""
    await _call_tool("bag_forget", {"key": "dreamer_config"})
    payload = await _dreamer_config_payload(None, "defaults")
    payload["status"] = "reset"
    return payload


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

    timeout = _HF_ROUTER_REQUEST_TIMEOUT_SECONDS
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


async def _pi_router_models_impl(request: Request, provider: str | None = None):
    provider_name = _pi_router_normalize_provider(provider or request.query_params.get("provider"))
    if not provider_name:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Unsupported Pi provider",
                "providers": sorted(_PI_ROUTER_ALLOWED_PROVIDERS),
            },
        )

    model_hint = str(request.query_params.get("model") or "").strip()
    if not model_hint:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Model hint is required for Pi router slots",
                "provider": provider_name,
            },
        )

    return JSONResponse(
        content={
            "object": "list",
            "data": [
                {
                    "id": model_hint,
                    "object": "model",
                    "owned_by": provider_name,
                }
            ],
            "provider": provider_name,
        },
        headers={"x-pi-provider": provider_name},
    )


async def _pi_router_chat_completions_impl(request: Request, provider: str | None = None):
    provider_name = _pi_router_normalize_provider(provider or request.query_params.get("provider"))
    if not provider_name:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Unsupported Pi provider",
                "providers": sorted(_PI_ROUTER_ALLOWED_PROVIDERS),
            },
        )

    body_bytes = await request.body()
    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "JSON payload must be an object"})

    model = str(payload.get("model") or request.query_params.get("model") or "").strip()
    if not model:
        return JSONResponse(
            status_code=400,
            content={"error": "Model is required", "provider": provider_name},
        )

    messages = payload.get("messages")
    fallback_prompt = str(
        payload.get("input")
        or payload.get("prompt")
        or payload.get("text")
        or ""
    ).strip()
    max_tokens = payload.get("max_tokens")
    thinking = payload.get("thinking") or payload.get("reasoning_effort") or request.query_params.get("thinking")
    system_prompt, prompt = _pi_router_build_prompt(messages, fallback_prompt=fallback_prompt, max_tokens=max_tokens)

    try:
        completion = await _pi_router_run_completion(
            provider_name,
            model,
            system_prompt,
            prompt,
            thinking=thinking,
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={
                "error": f"Pi router completion failed: {e}",
                "provider": provider_name,
                "model": model,
            },
        )

    return JSONResponse(
        content={
            "id": "chatcmpl-pi-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": completion.get("text", ""),
                    },
                    "finish_reason": "stop",
                }
            ],
            "provider": provider_name,
        },
        headers={"x-pi-provider": provider_name},
    )


@app.get("/pi-router/v1/models")
async def pi_router_models_default(request: Request):
    return await _pi_router_models_impl(request, provider=None)


@app.get("/pi-router/{provider}/v1/models")
async def pi_router_models_provider(provider: str, request: Request):
    return await _pi_router_models_impl(request, provider=provider)


@app.post("/pi-router/v1/chat/completions")
async def pi_router_chat_completions_default(request: Request):
    return await _pi_router_chat_completions_impl(request, provider=None)


@app.post("/pi-router/{provider}/v1/chat/completions")
async def pi_router_chat_completions_provider(provider: str, request: Request):
    return await _pi_router_chat_completions_impl(request, provider=provider)


@app.post("/pi-router/v1/embeddings")
async def pi_router_embeddings_default(request: Request):
    provider_name = _pi_router_normalize_provider(request.query_params.get("provider")) or "unknown"
    return _pi_router_feature_not_supported(provider_name, "embeddings")


@app.post("/pi-router/{provider}/v1/embeddings")
async def pi_router_embeddings_provider(provider: str, request: Request):
    provider_name = _pi_router_normalize_provider(provider) or str(provider or "unknown")
    return _pi_router_feature_not_supported(provider_name, "embeddings")


@app.post("/pi-router/v1/audio/speech")
async def pi_router_audio_speech_default(request: Request):
    provider_name = _pi_router_normalize_provider(request.query_params.get("provider")) or "unknown"
    return _pi_router_feature_not_supported(provider_name, "audio speech")


@app.post("/pi-router/{provider}/v1/audio/speech")
async def pi_router_audio_speech_provider(provider: str, request: Request):
    provider_name = _pi_router_normalize_provider(provider) or str(provider or "unknown")
    return _pi_router_feature_not_supported(provider_name, "audio speech")


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


@app.post("/api/env/capture")
async def env_capture(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    capture_type = str((body or {}).get("type") or "frame").strip() or "frame"
    result = (body or {}).get("result")
    if not isinstance(result, dict):
        return JSONResponse(status_code=400, content={"error": "Missing capture result payload"})
    try:
        payload = _env_capture_append(capture_type, result)
        return JSONResponse(content=payload)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Failed to persist capture: {exc}",
                "type": capture_type,
            },
        )


@app.post("/api/live-sync")
async def api_live_sync(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "Missing live sync payload"})
    cached = _env_live_cache_store(payload)
    if not isinstance(cached, dict):
        return JSONResponse(status_code=500, content={"error": "Failed to update live cache"})
    snapshot = _env_cached_text_theater_snapshot(cached)
    return JSONResponse(content={
        "ok": True,
        "updated_ms": int((cached or {}).get("updated_ms") or 0),
        "snapshot_timestamp": int((snapshot or {}).get("snapshot_timestamp") or 0),
        "last_sync_reason": str((snapshot or {}).get("last_sync_reason") or ""),
    })


@app.get("/api/text-theater/live")
async def api_text_theater_live():
    payload = _env_text_theater_live_payload({"query": "text_theater_live"})
    err_msg = payload.get("error") if isinstance(payload, dict) else None
    if err_msg:
        return JSONResponse(status_code=503, content=payload)
    return JSONResponse(content=payload)


@app.get("/", response_class=HTMLResponse)
async def landing():
    return Path("static/index.html").read_text(encoding="utf-8")


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy():
    return Path("static/privacy.html").read_text(encoding="utf-8")


@app.get("/envops.config.json")
async def root_envops_config():
    return FileResponse(Path("static/envops.config.json"), media_type="application/json")


@app.get("/favicon.ico")
async def root_favicon():
    return FileResponse(Path("static/logo.png"), media_type="image/png")


@app.get("/manifest.json")
async def root_manifest():
    return FileResponse(Path("static/manifest.json"), media_type="application/json")


@app.get("/api/packs/status")
async def pack_status():
    return pack_storage.status()


@app.post("/api/packs/sync")
async def pack_sync(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    force = bool((body or {}).get("force"))
    return await pack_storage.sync_runtime_packs(force=force)


@app.get("/static/assets/packs/{pack_path:path}")
async def pack_asset(pack_path: str):
    resolved = await pack_storage.resolve_runtime_pack_file(pack_path)
    if not resolved or not resolved.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "Pack asset not found",
                "path": str(pack_path or ""),
                "packs": pack_storage.status(),
            },
        )
    return FileResponse(resolved)


@app.get("/panel", response_class=HTMLResponse)
async def control_panel():
    content = Path("static/panel.html").read_text(encoding="utf-8")
    runtime_boot = (
        "<script>"
        f"window.__APP_MODE__ = {json.dumps(APP_MODE)};"
        f"window.__MCP_EXTERNAL_POLICY__ = {json.dumps(MCP_EXTERNAL_POLICY)};"
        "</script>"
    )
    if "</head>" in content:
        content = content.replace("</head>", runtime_boot + "\n</head>", 1)
    else:
        content = runtime_boot + "\n" + content
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
    if _external_mcp_blocked():
        return JSONResponse(
            status_code=403,
            content={
                "error": "External MCP is disabled for this runtime",
                "app_mode": APP_MODE,
                "mcp_external_policy": MCP_EXTERNAL_POLICY,
            },
        )

    # Build the public base URL from the incoming request
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", request.url.netloc)
    public_base = f"{proto}://{host}"
    print(f"[MCP-PROXY] SSE connect — public_base={public_base}")

    async def _stream():
        out_queue: asyncio.Queue = asyncio.Queue()
        endpoint_rewritten = False
        current_event_type = ""
        registered_session_id = ""

        async def _pump_capsule_stream():
            nonlocal endpoint_rewritten, current_event_type, registered_session_id
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("GET", f"{MCP_BASE}/sse", timeout=None) as resp:
                        buffer = ""
                        async for chunk in resp.aiter_text():
                            buffer += chunk
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)

                                if line.startswith("event:"):
                                    current_event_type = line.split(":", 1)[1].strip()

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
                                    query_pairs = dict(parse_qsl(urlsplit(path_and_query).query or ""))
                                    session_id = str(query_pairs.get("session_id") or query_pairs.get("sessionId") or "").strip()
                                    if session_id:
                                        _register_external_mcp_sse_subscriber(session_id, out_queue)
                                        registered_session_id = session_id
                                    rewritten = f"data: {public_base}/mcp{path_and_query}"
                                    print(f"[MCP-PROXY] Rewrote endpoint: {line.strip()} -> {rewritten.strip()}")
                                    endpoint_rewritten = True
                                    await out_queue.put(rewritten + "\n")
                                else:
                                    if line.startswith("data:") and _pending_external_calls:
                                        raw_data = line.split("data:", 1)[1].strip()
                                        print(f"[MCP-PROXY] SSE data line, event_type='{current_event_type}', pending={len(_pending_external_calls)}, data={raw_data[:120]}")
                                        try:
                                            payload = json.loads(raw_data)
                                            rpc_id = payload.get("id")
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

                                    await out_queue.put(line + "\n")
            except httpx.RemoteProtocolError:
                pass
            except Exception as e:
                print(f"[MCP-PROXY] SSE stream error: {e}")
                await out_queue.put(f"event: error\ndata: {e}\n\n")
            finally:
                if registered_session_id:
                    _unregister_external_mcp_sse_subscriber(registered_session_id, out_queue)
                stale_ids = [k for k, v in _pending_external_calls.items()
                             if time.time() - v["start"] > 300]
                for k in stale_ids:
                    stale = _pending_external_calls.pop(k, None)
                    if isinstance(stale, dict):
                        await _release_slot_execution(stale.get("claim"))
                await out_queue.put(None)

        pump_task = asyncio.create_task(_pump_capsule_stream())
        try:
            while True:
                chunk = await out_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if not pump_task.done():
                pump_task.cancel()
                try:
                    await pump_task
                except Exception:
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


@app.post("/mcp/message")
@app.post("/mcp/messages/")
@app.post("/mcp/messages")
async def mcp_message_proxy(request: Request):
    """Proxy JSON-RPC messages from external client to capsule MCP server."""
    if _external_mcp_blocked():
        return JSONResponse(
            status_code=403,
            content={
                "error": "External MCP is disabled for this runtime",
                "app_mode": APP_MODE,
                "mcp_external_policy": MCP_EXTERNAL_POLICY,
            },
        )
    session_id = request.query_params.get("session_id", "")
    body = await request.body()
    body = _normalize_mcp_jsonrpc_payload(body)
    content_type = request.headers.get("content-type", "application/json")
    _mcp_client_id = _extract_client_id(request)
    print(f"[MCP-PROXY] POST /mcp/message(s) session_id={session_id} client={_mcp_client_id} len={len(body)}")

    rpc_payload = None
    try:
        rpc_payload = json.loads(body)
    except Exception:
        rpc_payload = None

    if MCP_EXTERNAL_POLICY != "full" and isinstance(rpc_payload, dict):
        if str(rpc_payload.get("method") or "") in ("initialize", "tools/list"):
            handled = await _handle_streamable_rpc(rpc_payload, _mcp_client_id)
            if handled is None:
                return Response(status_code=202)
            if session_id and _push_external_mcp_sse_response(session_id, handled):
                return Response(status_code=202)
            return JSONResponse(status_code=200, content=handled)

    if MCP_EXTERNAL_POLICY != "full" and isinstance(rpc_payload, (dict, list)):
        rpc_items = [rpc_payload] if isinstance(rpc_payload, dict) else [item for item in rpc_payload if isinstance(item, dict)]
        violations = []
        for item in rpc_items:
            method = str(item.get("method") or "")
            params = item.get("params", {})
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    params = {}
            if not isinstance(params, dict):
                params = {}
            violation = _external_mcp_policy_violation(method, params)
            if violation:
                violations.append({"id": item.get("id"), **violation})

        if violations:
            if isinstance(rpc_payload, dict) and rpc_payload.get("id") is not None:
                first = violations[0]
                return JSONResponse(
                    status_code=200,
                    content=_rpc_error(
                        rpc_payload.get("id"),
                        first.get("code", -32004),
                        first.get("message", "Blocked by external MCP policy"),
                        first.get("data"),
                    ),
                )
            return JSONResponse(
                status_code=403,
                content={
                    "error": violations[0].get("message") or "Blocked by external MCP policy",
                    "violations": violations,
                    "app_mode": APP_MODE,
                    "mcp_external_policy": MCP_EXTERNAL_POLICY,
                },
            )

    # Extract tools/call payload(s) for activity tracking (single or batch).
    rpc_calls = [
        {"tool": tool, "args": args, "rpc_id": rpc_id}
        for tool, args, rpc_id in _parse_rpc_tool_calls(body)
    ]

    # Local proxy tools should work even for SSE-only MCP clients.
    _local_proxy_tools = _workflow_local_proxy_tool_names()
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
        if session_id and _push_external_mcp_sse_response(session_id, handled):
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
                timeout=float(_MCP_TOOL_TIMEOUT_SECONDS),
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
    if _external_mcp_blocked():
        return JSONResponse(
            status_code=403,
            content=_rpc_error(
                None,
                -32003,
                "External MCP is disabled for this runtime",
                {"app_mode": APP_MODE, "mcp_external_policy": MCP_EXTERNAL_POLICY},
            ),
        )

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

    violation = _external_mcp_policy_violation(method, params)
    if violation:
        return _rpc_error(rpc_id, violation.get("code", -32004), violation.get("message", "Blocked by external MCP policy"), violation.get("data"))

    # ── initialize ──
    if method == "initialize":
        session = await _ensure_session()
        if not session:
            return _rpc_error(rpc_id, -32603, "Failed to connect to capsule MCP")
        # Return server capabilities with the capsule's REAL instructions.
        # _capsule_instructions is populated during _connect_mcp() from the
        # capsule's _build_mcp_instructions() — the full onboarding orientation.
        _fallback_instructions = (
            "Use tools/call for all operations. For large payloads, follow _cached via "
            "get_cached(cache_id). agent_chat supports granted_tools for agentic tool use. "
            "Local proxy tools include continuity_status, continuity_restore, env_help, "
            "env_report, agent_delegate, agent_chat_inject, agent_chat_sessions, "
            "agent_chat_result, agent_chat_purge, workflow_execute, hf_cache_status, "
            "hf_cache_clear, capsule_restart, persist_status, persist_restore_revision, "
            "product_bundle_profiles, and product_bundle_export."
        )
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
                "instructions": (
                    (_capsule_instructions or _fallback_instructions)
                    + _external_mcp_local_bridge_note()
                    + _external_mcp_policy_note()
                ),
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
            tools_list = _filter_external_mcp_tools_list(tools_list)
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

        if tool_name == "continuity_status":
            try:
                limit = int(args.get("limit", 10) or 10)
            except Exception:
                limit = 10
            payload = continuity_status_payload(
                limit=max(1, min(limit, 50)),
                codex_home=str(args.get("codex_home", "") or "").strip() or None,
            )
            _broadcast_activity(tool_name, args, payload, 0, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "continuity_restore":
            try:
                limit = int(args.get("limit", 3) or 3)
            except Exception:
                limit = 3
            try:
                since_days = int(args.get("since_days", 30) or 30)
            except Exception:
                since_days = 30
            payload = continuity_restore_payload(
                summary=str(args.get("summary", "") or ""),
                cwd=str(args.get("cwd", "") or ""),
                limit=max(1, min(limit, 10)),
                since_days=max(1, min(since_days, 3650)),
                session_path=str(args.get("session_path", "") or "").strip() or None,
                codex_home=str(args.get("codex_home", "") or "").strip() or None,
            )
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            _broadcast_activity(tool_name, args, payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        get_help_bridge_payload = _get_help_environment_bridge_payload(args) if tool_name == "get_help" else None
        if tool_name == "get_help" and get_help_bridge_payload is not None:
            _broadcast_activity(tool_name, args, get_help_bridge_payload, 0, None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(get_help_bridge_payload)}], "isError": False}}

        env_help_proxy_payload = _env_help_local_proxy_payload(args) if tool_name == "env_help" else None
        if tool_name == "env_help" and env_help_proxy_payload is not None:
            err_msg = env_help_proxy_payload.get("error") if isinstance(env_help_proxy_payload, dict) else None
            _broadcast_activity(tool_name, args, env_help_proxy_payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg and str(env_help_proxy_payload.get("status") or "").lower() == "error":
                return _rpc_error(rpc_id, -32603, err_msg, env_help_proxy_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(env_help_proxy_payload)}], "isError": False}}

        env_control_proxy_payload = _env_control_local_proxy_payload(args)
        if env_control_proxy_payload is not None:
            before_live_cache = _env_live_cache_snapshot()
            before_updated_ms = int((before_live_cache or {}).get("updated_ms") or 0)
            err_msg = env_control_proxy_payload.get("error") if isinstance(env_control_proxy_payload, dict) else None
            _broadcast_activity(tool_name, args, env_control_proxy_payload, 0, err_msg, source="external", client_id=client_id)
            env_control_proxy_payload = await _env_control_attach_text_theater_observation(
                env_control_proxy_payload,
                args=args,
                before_updated_ms=before_updated_ms,
            )
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, env_control_proxy_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(env_control_proxy_payload)}], "isError": False}}

        env_persist_proxy_payload = _env_persist_local_proxy_payload(args) if tool_name == "env_persist" else None
        if tool_name == "env_persist" and env_persist_proxy_payload is not None:
            err_msg = env_persist_proxy_payload.get("error") if isinstance(env_persist_proxy_payload, dict) else None
            _broadcast_activity(tool_name, args, env_persist_proxy_payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, env_persist_proxy_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(env_persist_proxy_payload)}], "isError": False}}

        env_read_proxy_payload = await _env_read_local_proxy_payload_async(args)
        if tool_name == "env_read" and env_read_proxy_payload is not None:
            err_msg = env_read_proxy_payload.get("error") if isinstance(env_read_proxy_payload, dict) else None
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, env_read_proxy_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(env_read_proxy_payload)}], "isError": False}}

        env_report_proxy_payload = await _env_report_local_proxy_payload_async(args)
        if tool_name == "env_report" and env_report_proxy_payload is not None:
            err_msg = env_report_proxy_payload.get("error") if isinstance(env_report_proxy_payload, dict) else None
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, env_report_proxy_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(env_report_proxy_payload)}], "isError": False}}

        product_bundle_payload = await _product_bundle_local_tool(tool_name, args)
        if product_bundle_payload is not None:
            err_msg = product_bundle_payload.get("error") if isinstance(product_bundle_payload, dict) else None
            _broadcast_activity(tool_name, args, product_bundle_payload, 0, err_msg, source="external", client_id=client_id)
            if err_msg:
                return _rpc_error(rpc_id, -32603, err_msg, product_bundle_payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(product_bundle_payload)}], "isError": False}}

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
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
