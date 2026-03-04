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
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlsplit, urlunsplit, unquote

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

HF_ROUTER_BASE = os.environ.get("HF_ROUTER_BASE", "https://router.huggingface.co").rstrip("/")


def _hf_router_token(explicit: str | None = None) -> str | None:
    token = (explicit or "").strip()
    if token:
        return token
    if getattr(settings, "hf_token", None):
        val = str(settings.hf_token).strip()
        if val:
            return val
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACEHUB_API_TOKEN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


def _broadcast_agent_inner_calls(tool_name: str, result, duration_ms: int, source: str = "external", client_id: str | None = None):
    """Extract inner tool_calls from agent_chat results and broadcast each as a separate activity entry."""
    if tool_name != "agent_chat":
        return
    parsed = _parse_mcp_result_payload(result) if isinstance(result, dict) else None
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
        activity_hub.add_entry(
            tool=tc_tool,
            args=tc_args,
            result=tc_result_content,
            duration_ms=duration_ms,
            error=str(tc_error) if tc_error else None,
            source="agent-inner",
            client_id=client_id,
        )
        print(f"[AGENT-INNER] Broadcast {i+1}/{len(tool_calls)}: {tc_tool} (iter={tc_iteration}, slot={slot_idx}/{slot_name})")


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
    # Explicit header wins
    client_id = request.headers.get("x-client-id") or request.headers.get("x-mcp-client")
    if client_id:
        return client_id.strip()[:64]

    ua = (request.headers.get("user-agent") or "").strip()
    ua_lower = ua.lower()

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
    if "modelcontextprotocol" in ua_lower or "mcp" in ua_lower:
        return "mcp-client"

    if ua and "/" in ua:
        agent_name = ua.split("/")[0].strip().lower()[:24]
        if agent_name and agent_name not in ("mozilla", "python-requests", "python"):
            return agent_name

    if "python" in ua_lower or "httpx" in ua_lower or "aiohttp" in ua_lower:
        return "python-client"

    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and len(auth) > 20:
        return "hf-authenticated"

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
    if origin and not _is_same_origin_request(origin, request):
        return "external"
    if referer and not _is_same_origin_request(referer, request):
        return "external"
    if not origin and not referer:
        return "external"

    return fallback


def _parse_mcp_result_payload(result: dict | None) -> dict | None:
    if not result or not isinstance(result, dict):
        return None
    content = result.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
    return result


async def _slot_ready_guard(tool_name: str, args: dict | None) -> dict | None:
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
    info = _parse_mcp_result_payload((info_raw or {}).get("result") if isinstance(info_raw, dict) else None) or {}
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


def _normalize_remote_provider_model_id(model_id: str) -> tuple[str, bool]:
    """Normalize remote provider URLs for capsule compatibility.

    Capsule-side remote provider parsing is intentionally simple. Normalize here
    so all client paths (/api/tool + MCP) behave consistently:
      - decode percent-encoded model/key query values
      - strip trailing /v1 so capsule appends /v1/* only once
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
        normalized_tokens: list[str] = []
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

    if tool_name == "plug_model" and isinstance(patched.get("model_id"), str):
        normalized, changed = _normalize_remote_provider_model_id(patched.get("model_id"))
        if changed:
            patched["model_id"] = normalized

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

    if tool_name == "materialize":
        _ensure_parent_dir_for_path(patched.get("output_path"))
    elif tool_name == "save_bag":
        _ensure_parent_dir_for_path(patched.get("file_path"))
    elif tool_name == "bag_export":
        _ensure_parent_dir_for_path(patched.get("output_path"))

    return patched


async def _call_tool(name: str, arguments: dict) -> dict:
    return await mcp_client.call_tool(name, arguments)


async def _list_tools() -> dict:
    tools = await mcp_client.list_tools()
    if isinstance(tools, dict):
        res = tools.get("result") if isinstance(tools.get("result"), dict) else {}
        if "tools" in res and isinstance(res.get("tools"), list):
            res["tools"] = _agent_augment_tools_list(res.get("tools") or [])
            tools["result"] = res
    return tools


def _ssh_key_paths() -> tuple[Path, Path, Path]:
    ssh_dir = Path.home() / ".ssh"
    return ssh_dir, ssh_dir / "id_rsa", ssh_dir / "id_rsa.pub"


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
    """Ensure ~/.ssh/id_rsa exists for Vast tools."""
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
    if private_secret:
        if _write_ssh_file(private_key, private_secret, 0o600):
            print("[INIT] Loaded SSH private key from SSH_PRIVATE_KEY")
        if public_secret:
            _write_ssh_file(public_key, public_secret, 0o644)

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
        else:
            print("[WARN] ssh-keygen not found and SSH_PRIVATE_KEY is not set; Vast SSH tools may fail")

    if private_key.exists():
        try:
            os.chmod(private_key, 0o600)
        except OSError:
            pass
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
# when clients timeout locally and retry while first call is still running.
_SLOT_SERIAL_TOOLS = frozenset({"invoke_slot", "chat", "agent_chat", "generate", "classify"})

# Emit immediate activity "start" entries for long-running calls so UI isn't blank.
_LIVE_START_TOOLS = frozenset({"agent_chat", "invoke_slot", "chat", "generate", "classify", "plug_model", "hub_plug"})

# Track last chat slot to avoid cross-slot shared-history bleed.
_last_chat_slot: int | None = None

_slot_exec_gate = asyncio.Lock()
_slot_exec_locks: dict[int, asyncio.Lock] = {}
_slot_exec_active: dict[int, dict] = {}


# ═══════════════════════════════════════════════════════════════════════
# SERVER-SIDE AGENT ORCHESTRATOR
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
                "granted_tools": {"type": "array", "description": "Optional delegated granted tools"},
            },
            "required": ["slot", "message"],
        },
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
                "priority": {"type": "string", "description": "Optional priority label"},
            },
            "required": ["message"],
        },
    },
    "agent_chat_sessions": {
        "description": "List active/recent agent_chat sessions with queue depth and state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer", "description": "Optional slot filter"},
                "active_only": {"type": "boolean", "description": "Show only active sessions"},
                "limit": {"type": "integer", "description": "Max sessions to return"},
            },
        },
    },
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


_agent_sessions: dict[str, dict] = {}


def _agent_session_snapshot(args: dict | None = None) -> dict:
    args = args or {}
    slot_filter = args.get("slot")
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
        try:
            slot = int(sess.get("slot"))
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


def _agent_select_session(session_id: str = "", slot: int | None = None, active_preferred: bool = True) -> tuple[str | None, dict | None]:
    sid = str(session_id or "").strip()
    if sid and sid in _agent_sessions and isinstance(_agent_sessions.get(sid), dict):
        return sid, _agent_sessions.get(sid)

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
    target_slot = None
    if args.get("slot") is not None:
        try:
            target_slot = int(args.get("slot"))
        except Exception:
            target_slot = None

    sid, session = _agent_select_session(req_session_id, target_slot, active_preferred=True)
    if not sid or not isinstance(session, dict):
        return {
            "error": "No matching agent_chat session found",
            "session_id": req_session_id or None,
            "slot": target_slot,
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


def _agent_decode_keys(text: str) -> str:
    """Decode __docv2__ encoded keys to human-readable /slash/paths for display."""
    import re
    def _rep(m):
        raw = m.group(0)
        body = raw[len("__docv2__"):]
        if body.endswith("__k"):
            body = body[:-3]
        return "/" + body.replace("~s", "/")
    return re.sub(r'__docv2__[^"}\s,\]]+', _rep, text)


async def _agent_delegate_call(
    caller_slot: int,
    caller_session_id: str,
    caller_depth: int,
    called_args: dict,
    source: str,
    client_id: str | None,
    call_tool_fn=None,
    list_tools_fn=None,
    parse_result_fn=None,
    normalize_args_fn=None,
    broadcast_fn=None,
) -> tuple[dict | None, str | None]:
    import uuid as _uuid

    _parse = parse_result_fn or _parse_mcp_result_payload

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
    if isinstance(called_args.get("granted_tools"), list) and called_args.get("granted_tools"):
        delegate_args["granted_tools"] = called_args.get("granted_tools")

    claim, busy = await _claim_slot_execution("agent_chat", {"slot": target_slot, "session_id": delegate_session_id}, source="agent-inner", client_id=client_id)
    if busy:
        return {"slot_busy": busy}, busy.get("error") or "delegate target busy"

    try:
        delegated = await _server_side_agent_chat(
            delegate_args,
            source="agent-inner",
            client_id=client_id,
            call_tool_fn=call_tool_fn,
            list_tools_fn=list_tools_fn,
            parse_result_fn=parse_result_fn,
            normalize_args_fn=normalize_args_fn,
            broadcast_fn=broadcast_fn,
        )
    finally:
        await _release_slot_execution(claim)

    if isinstance(delegated, dict) and delegated.get("error"):
        return delegated, str(delegated.get("error"))

    payload = None
    if isinstance(delegated, dict):
        payload = _parse(delegated.get("result"))
        if payload is None:
            payload = delegated
    else:
        payload = delegated

    return payload, None


async def _server_side_agent_chat(
    args: dict, source: str = "webui", client_id: str | None = None,
    call_tool_fn=None, list_tools_fn=None, parse_result_fn=None,
    normalize_args_fn=None, broadcast_fn=None,
) -> dict:
    """Run the agent tool-call loop at the proxy layer."""
    import uuid as _uuid

    _call = call_tool_fn or _call_tool
    _list = list_tools_fn or _list_tools
    _parse = parse_result_fn or _parse_mcp_result_payload
    _norm = normalize_args_fn or _normalize_proxy_tool_args

    def _bcast(**kw):
        if broadcast_fn:
            broadcast_fn(**kw)

    slot = int(args.get("slot", 0))
    message = str(args.get("message", "")).strip()
    max_iterations = int(args.get("max_iterations", 5))
    max_tokens = int(args.get("max_tokens", 0)) or 2048
    reset = bool(args.get("reset", False))
    session_id = str(args.get("session_id", "")).strip()
    granted_tools = args.get("granted_tools")

    if not message:
        return {"error": "message is required"}

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
            "chat_messages": [],
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

    slot_info_raw = await _call("slot_info", {"slot": slot})
    slot_info = _parse(slot_info_raw.get("result")) or {}
    slot_name = slot_info.get("name", f"slot_{slot}") if isinstance(slot_info, dict) else f"slot_{slot}"
    plugged = bool(slot_info.get("plugged")) if isinstance(slot_info, dict) else False
    if not plugged:
        return {"error": f"Slot {slot} is not plugged. Plug a model first."}

    session["active"] = True
    session["last_active_ts"] = int(time.time() * 1000)
    session["updated_ts"] = session["last_active_ts"]
    _agent_sessions[session_id] = session

    # Build tool descriptions
    tools_raw = await _list()
    all_tools = (tools_raw.get("result", {}).get("tools") or []) if isinstance(tools_raw, dict) else []
    granted_set = set(granted)
    td_lines = []
    for t in all_tools:
        name = t.get("name", "")
        if name not in granted_set:
            continue
        desc = (t.get("description") or "").strip().split("\n")[0][:120]
        schema = t.get("inputSchema", {})
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        req = set(schema.get("required", [])) if isinstance(schema, dict) else set()
        params = []
        for pn, pi in props.items():
            pt = pi.get("type", "any") if isinstance(pi, dict) else "any"
            params.append(f"{pn}: {pt}" + (" (required)" if pn in req else ""))
        td_lines.append(f"- {name}({', '.join(params)}): {desc}")
    tool_descriptions = "\n".join(td_lines) if td_lines else "(no tool descriptions)"

    system_prompt = (
        f"You are {slot_name}, an AI agent in council slot {slot}.\n"
        "Respond with EXACTLY ONE JSON object per turn.\n\n"
        f"AVAILABLE TOOLS:\n{tool_descriptions}\n\n"
        "To call a tool: {\"tool\": \"name\", \"args\": {\"param\": \"value\"}}\n"
        "When done: {\"final_answer\": \"your answer\"}\n\n"
        "Rules:\n"
        "- ONE tool at a time — never batch multiple calls\n"
        "- After EVERY tool result, evaluate: did it succeed? what did you learn? what next?\n"
        "- If a tool failed, decide whether to retry, skip, or adjust\n"
        "- For cross-slot autonomous work, prefer agent_delegate instead of inventing callback loops\n"
        "- Never invoke your own slot for delegation\n"
        "- You may receive [LIVE UPDATE] messages mid-run; incorporate them immediately\n"
        "- Always end with final_answer summarizing outcomes\n"
    )

    chat_messages = session.get("chat_messages", [])
    if not chat_messages:
        chat_messages = [{"role": "system", "content": system_prompt}]

    session["turns"].append({"role": "user", "content": message, "ts": int(time.time() * 1000)})
    chat_messages.append({"role": "user", "content": message})

    tool_calls_log = []
    final_answer = None
    iterations_used = 0
    loop_start = time.time()

    _bcast(
        tool="agent_chat", args=args,
        result={"_phase": "start", "state": "running", "session_id": session_id,
                "slot": slot, "name": slot_name, "max_iterations": max_iterations},
        duration_ms=0, error=None, source=source, client_id=client_id,
    )

    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        step_start = time.time()

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
                _bcast(
                    tool="agent_chat_inject",
                    args={
                        "session_id": session_id,
                        "slot": slot,
                        "delivered": delivered_count,
                        "iteration": iterations_used,
                        "_agent_session": session_id,
                        "_agent_caller_slot": slot,
                    },
                    result={"_phase": "delivered", "delivered": delivered_count, "session_id": session_id},
                    duration_ms=0,
                    error=None,
                    source="agent-inner",
                    client_id=client_id,
                )

        if iteration == max_iterations - 1:
            chat_messages.append({
                "role": "user",
                "content": 'This is your LAST iteration. You MUST respond with {"final_answer": "your answer"} now.'
            })

        invoke_args = {"slot": slot, "text": message, "mode": "generate", "messages": chat_messages, "max_tokens": max_tokens}
        try:
            model_raw = await _call("invoke_slot", invoke_args)
            model_parsed = _parse(model_raw.get("result"))
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
        step_ms = int((time.time() - step_start) * 1000)

        _bcast(
            tool="agent_chat",
            args={
                "_phase": "reasoning",
                "iteration": iterations_used,
                "session_id": session_id,
                "_agent_session": session_id,
                "slot": slot,
                "_agent_caller_slot": slot,
                "_agent_caller_name": slot_name,
            },
            result={"content": [{"type": "text", "text": json.dumps({
                "iteration": iterations_used, "model_output_preview": _agent_decode_keys(model_output[:300]) if "__docv2__" in model_output[:300] else model_output[:300], "step_ms": step_ms,
            })}]},
            duration_ms=step_ms, error=None, source="agent-inner", client_id=client_id,
        )

        chat_messages.append({"role": "assistant", "content": model_output})

        parsed = None
        if isinstance(model_output, str):
            stripped = model_output.strip()
            import re as _re_agent
            if "<think>" in stripped:
                stripped = _re_agent.sub(r"<think>[\s\S]*?</think>\s*", "", stripped).strip()
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
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

        if parsed is None:
            final_answer = model_output.strip() if model_output.strip() else "Model returned empty response."
            break

        if "final_answer" in parsed:
            final_answer = parsed["final_answer"]
            break

        if "tool" in parsed:
            called_tool = str(parsed["tool"]).strip()
            called_args = parsed.get("args", {})
            if not isinstance(called_args, dict):
                try:
                    called_args = json.loads(str(called_args)) if isinstance(called_args, str) else {}
                except Exception:
                    called_args = {}

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

            if called_tool not in granted:
                denial = f"Tool '{called_tool}' is NOT in your granted tools."
                chat_messages.append({"role": "user", "content": denial})
                tool_calls_log.append({"tool": called_tool, "args": called_args, "result": "DENIED", "iteration": iteration})
                continue

            if called_tool == "invoke_slot" and int(called_args.get("slot", -1)) == slot:
                guard_msg = f"Self-invocation blocked: invoke_slot(slot={slot}). Choose a different slot or use agent_delegate for structured cross-slot orchestration."
                chat_messages.append({"role": "user", "content": guard_msg})
                tool_calls_log.append({"tool": called_tool, "args": called_args, "result": "DENIED - " + guard_msg, "iteration": iteration})
                continue

            if called_tool in ("agent_delegate", "agent_chat_inject", "agent_chat_sessions"):
                normalized_args = dict(called_args)
            else:
                normalized_args = _norm(called_tool, called_args)
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

            _bcast(
                tool=called_tool, args=display_args,
                result={"_phase": "start", "state": "running", "_agent_session": session_id, "_agent_iteration": iterations_used},
                duration_ms=0, error=None, source="agent-inner", client_id=client_id,
            )

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
                        call_tool_fn=_call,
                        list_tools_fn=_list,
                        parse_result_fn=_parse,
                        normalize_args_fn=_norm,
                        broadcast_fn=broadcast_fn,
                    )
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result is not None else ""
                else:
                    tool_raw = await _call(called_tool, normalized_args)
                    tool_result = _parse(tool_raw.get("result"))
                    tool_error = tool_raw.get("error") or (tool_result.get("error") if isinstance(tool_result, dict) else None)
                    tool_result_str = json.dumps(tool_result, indent=2, default=str) if tool_result else ""
            except Exception as e:
                tool_result = None
                tool_error = str(e)
                tool_result_str = f"ERROR: {e}"
            tool_ms = int((time.time() - tool_start) * 1000)

            _display_result_str = _agent_decode_keys(tool_result_str) if "__docv2__" in tool_result_str else tool_result_str

            _bcast(
                tool=called_tool, args=display_args,
                result={"content": [{"type": "text", "text": _display_result_str[:2000]}]} if _display_result_str else None,
                duration_ms=tool_ms, error=str(tool_error) if tool_error else None,
                source="agent-inner", client_id=client_id,
            )

            tool_calls_log.append({
                "tool": called_tool, "args": called_args,
                "result": tool_result_str[:500] if tool_result_str else "",
                "error": str(tool_error) if tool_error else None,
                "duration_ms": tool_ms, "iteration": iteration,
            })

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
            final_answer = json.dumps(parsed, default=str)
            break

    if final_answer is None:
        final_answer = f"Agent reached max iterations ({max_iterations}) without final answer."

    total_ms = int((time.time() - loop_start) * 1000)

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
    result_text = json.dumps(envelope, indent=2, default=str)
    return {
        "result": {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        }
    }


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
        "runtime": "self_deploy",
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    started_capsule = False

    # Startup
    _ensure_vast_ssh_keys()

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

    raw_body = dict(body) if isinstance(body, dict) else {}

    if tool_name in ("workflow_create", "workflow_update") and "definition" in body:
        body["definition"] = normalize_workflow_nodes(body["definition"])

    body = _normalize_proxy_tool_args(tool_name, body if isinstance(body, dict) else {})

    body_source = _normalize_activity_source(body.pop("__source", None) if isinstance(body, dict) else None)
    source = body_source or _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)

    # Local virtual orchestrator tools (proxy-side; not forwarded to capsule).
    if tool_name == "agent_chat_inject":
        payload = _agent_inject_message(body if isinstance(body, dict) else {}, source=source, client_id=client_id)
        err = payload.get("error") if isinstance(payload, dict) else None
        activity_hub.add_entry(
            tool=tool_name,
            args=body if isinstance(body, dict) else {},
            result=payload,
            duration_ms=0,
            error=err,
            source=source,
            client_id=client_id,
        )
        if err:
            return JSONResponse(status_code=404, content=payload)
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

    if tool_name == "agent_chat_sessions":
        payload = _agent_session_snapshot(body if isinstance(body, dict) else {})
        activity_hub.add_entry(
            tool=tool_name,
            args=body if isinstance(body, dict) else {},
            result=payload,
            duration_ms=0,
            error=None,
            source=source,
            client_id=client_id,
        )
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
        payload, err = await _agent_delegate_call(
            caller_slot,
            caller_session_id,
            caller_depth,
            raw,
            source=source,
            client_id=client_id,
            call_tool_fn=_call_tool,
            list_tools_fn=_list_tools,
            parse_result_fn=_parse_mcp_result_payload,
            normalize_args_fn=_normalize_proxy_tool_args,
            broadcast_fn=lambda **kw: activity_hub.add_entry(**kw),
        )
        duration_ms = int((time.time() - started) * 1000)
        out = payload if isinstance(payload, dict) else {"result": payload}
        if err:
            if isinstance(out, dict):
                out.setdefault("error", err)
            activity_hub.add_entry(tool=tool_name, args=raw, result=out, duration_ms=duration_ms, error=err, source=source, client_id=client_id)
            return JSONResponse(status_code=409, content=out)
        activity_hub.add_entry(tool=tool_name, args=raw, result=out, duration_ms=duration_ms, error=None, source=source, client_id=client_id)
        return {"result": {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}}

    slot_guard = await _slot_ready_guard(tool_name, body if isinstance(body, dict) else {})
    if slot_guard:
        error_msg = slot_guard.get("error") or f"Slot readiness guard blocked {tool_name}"
        payload = {"error": error_msg, "slot_guard": slot_guard}
        activity_hub.add_entry(
            tool=tool_name,
            args=body if isinstance(body, dict) else {},
            result=payload,
            duration_ms=0,
            error=error_msg,
            source=source,
            client_id=client_id,
        )
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
            activity_hub.add_entry(
                tool=tool_name,
                args=body if isinstance(body, dict) else {},
                result=payload,
                duration_ms=0,
                error=error_msg,
                source=source,
                client_id=client_id,
            )
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
        activity_hub.add_entry(
            tool=tool_name,
            args=call_args,
            result=payload,
            duration_ms=0,
            error=error_msg,
            source=source,
            client_id=client_id,
        )
        return JSONResponse(status_code=409, content=payload)

    if tool_name in _LIVE_START_TOOLS:
        activity_hub.add_entry(
            tool=tool_name,
            args=call_args,
            result={"_phase": "start", "state": "running"},
            duration_ms=0,
            error=None,
            source=source,
            client_id=client_id,
        )

    # ── Server-side agent orchestration ──────────────────────────
    if tool_name == "agent_chat":
        try:
            orchestrated = await _server_side_agent_chat(
                call_args, source=source, client_id=client_id,
                call_tool_fn=_call_tool, list_tools_fn=_list_tools,
                parse_result_fn=_parse_mcp_result_payload,
                normalize_args_fn=_normalize_proxy_tool_args,
                broadcast_fn=lambda **kw: activity_hub.add_entry(**kw),
            )
            activity_hub.add_entry(
                tool="agent_chat", args=call_args,
                result=orchestrated.get("result"),
                duration_ms=0,
                error=orchestrated.get("error"),
                source=source, client_id=client_id,
            )
            if orchestrated.get("error"):
                return JSONResponse(status_code=503, content=orchestrated)
            return orchestrated
        finally:
            await _release_slot_execution(claim)

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
                probe = _parse_mcp_result_payload(result.get("result"))
                probe_err = str(result.get("error") or (probe.get("error") if isinstance(probe, dict) else "") or "")
                if "not found" in probe_err.lower():
                    retry_args = dict(call_args)
                    if tool_name in ("file_read", "file_info"):
                        retry_args.pop("key", None)
                        retry_args["path"] = raw_key
                    else:
                        retry_args["key"] = raw_key
                    retry = await _call_tool(tool_name_effective, retry_args)
                    retry_probe = _parse_mcp_result_payload(retry.get("result"))
                    retry_err = str(retry.get("error") or (retry_probe.get("error") if isinstance(retry_probe, dict) else "") or "")
                    if not retry_err:
                        result = retry

        result = await postprocess_tool_result(tool_name, call_args, result, _call_tool, activity_hub=activity_hub)

        duration_ms = int((time.time() - start) * 1000)
        error_str = result.get("error") if isinstance(result.get("error"), str) else None
        activity_hub.add_entry(
            tool=tool_name,
            args=call_args,
            result=result.get("result"),
            duration_ms=duration_ms,
            error=error_str,
            source=source,
            client_id=client_id,
        )
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
    activity_hub.add_entry(
        tool="list_tools",
        args={},
        result=result.get("result"),
        duration_ms=duration_ms,
        error=error_str,
        source=source,
        client_id=client_id,
    )
    if "error" in result and isinstance(result.get("error"), str):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/api/health")
async def health(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    start = time.time()
    latest_event_id = activity_hub.log[-1].get("eventId") if activity_hub.log else None
    payload = {
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
    cap = _runtime_capacity_snapshot()
    payload["runtime_capacity"] = {
        "memory_used_percent": ((cap.get("memory") or {}).get("used_percent")),
        "memory_free_gb": ((cap.get("memory") or {}).get("free_gb")),
        "gpu_available": ((cap.get("gpu") or {}).get("available")),
        "gpu_free_gb": ((cap.get("gpu") or {}).get("free_gb")),
    }
    duration_ms = int((time.time() - start) * 1000)
    activity_hub.add_entry(
        tool="api_health",
        args={},
        result={"content": [{"type": "text", "text": json.dumps(payload)}]},
        duration_ms=duration_ms,
        error=None,
        source=source,
        client_id=client_id,
    )
    return payload


@app.get("/api/runtime/capacity")
async def runtime_capacity(request: Request):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    start = time.time()
    payload = _runtime_capacity_snapshot(force=True)
    duration_ms = int((time.time() - start) * 1000)
    activity_hub.add_entry(
        tool="api_runtime_capacity",
        args={},
        result={"content": [{"type": "text", "text": json.dumps(payload)}]},
        duration_ms=duration_ms,
        error=None,
        source=source,
        client_id=client_id,
    )
    return payload


@app.get("/api/capsule-log")
async def capsule_log():
    return {"lines": capsule_manager.tail(100)}


@app.get("/api/agent_chat/sessions")
async def api_agent_chat_sessions(request: Request, slot: int | None = None, active_only: bool = False, limit: int = 50):
    source = _infer_activity_source(request, fallback="webui")
    client_id = _extract_client_id(request)
    args = {"active_only": bool(active_only), "limit": int(limit)}
    if slot is not None:
        args["slot"] = int(slot)
    payload = _agent_session_snapshot(args)
    activity_hub.add_entry(
        tool="agent_chat_sessions",
        args=args,
        result=payload,
        duration_ms=0,
        error=None,
        source=source,
        client_id=client_id,
    )
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
    activity_hub.add_entry(
        tool="agent_chat_inject",
        args=body,
        result=payload,
        duration_ms=0,
        error=(err if isinstance(err, str) and err else None),
        source=source,
        client_id=client_id,
    )
    if isinstance(payload, dict) and payload.get("error"):
        return JSONResponse(status_code=404, content=payload)
    return payload


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


async def _hf_router_proxy_impl(request: Request, subpath: str, provider: str = "auto"):
    token_hint = request.query_params.get("token") or request.query_params.get("hf_token")
    token = _hf_router_token(token_hint)
    if not token:
        return JSONResponse(
            status_code=401,
            content={
                "error": "HF token not configured",
                "hint": "Set HF_TOKEN in environment (or pass hf_token query for direct testing).",
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

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.request(
                method,
                target,
                params=fwd_params,
                content=body_bytes if method in ("POST", "PUT", "PATCH") else None,
                headers=headers,
            )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"HF router proxy failed: {exc}"})

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


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy():
    return (settings.frontend_dir / "privacy.html").read_text(encoding="utf-8")


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
                                                client_id=pending.client_id,
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
    _mcp_client_id = _extract_client_id(request)

    _, rpc_calls_raw = parse_rpc_tool_calls(body)
    rpc_calls = [
        {"tool": tool, "args": args, "rpc_id": rpc_id}
        for tool, args, rpc_id in rpc_calls_raw
    ]
    body = normalize_rpc_workflow(body, normalize_workflow_nodes)

    # Slot readiness guard for external MCP calls.
    blocked_calls = []
    for call in rpc_calls:
        sg = await _slot_ready_guard(call.get("tool") or "", call.get("args") if isinstance(call, dict) else {})
        if sg:
            blocked_calls.append((call, sg))

    if blocked_calls:
        for call, sg in blocked_calls:
            err = sg.get("error") or "Slot readiness guard blocked request"
            activity_hub.add_entry(
                tool=call.get("tool") or "",
                args=call.get("args") or {},
                result={"slot_guard": sg},
                duration_ms=0,
                error=err,
                source="external",
                client_id=_mcp_client_id,
            )

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
                        pending_calls.store(session_id, rpc_id, call["tool"], call["args"], start, client_id=_mcp_client_id)
                    else:
                        # Notifications (no JSON-RPC id) cannot be matched on SSE response.
                        activity_hub.add_entry(
                            call["tool"],
                            call["args"],
                            None,
                            duration_ms,
                            None,
                            source="external",
                            client_id=_mcp_client_id,
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
                        client_id=_mcp_client_id,
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
                        client_id=_mcp_client_id,
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
                        client_id=_mcp_client_id,
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
                client_id=_mcp_client_id,
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
                client_id=_mcp_client_id,
            )
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.post("/mcp/sse")
async def mcp_streamable_http(request: Request):
    """Handle MCP Streamable HTTP transport without requiring long-lived SSE."""
    body_bytes = await request.body()
    if not body_bytes:
        return JSONResponse(status_code=400, content={"error": "Empty body"})

    try:
        payload = json.loads(body_bytes)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    client_id = _extract_client_id(request)

    if isinstance(payload, dict):
        result = await _handle_streamable_rpc(payload, client_id)
        if result is None:
            return Response(status_code=202)
        return JSONResponse(content=result)

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


async def _handle_streamable_rpc(obj: dict, client_id: str | None) -> dict | None:
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

    if method == "initialize":
        session = await mcp_client.ensure_session()
        if not session:
            return _rpc_error(rpc_id, -32603, "Failed to connect to capsule MCP")
        # Return the capsule's REAL instructions (built by _build_mcp_instructions()
        # in champion_gen8.py) — cached during mcp_client.connect().
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
                "instructions": mcp_client.capsule_instructions or _fallback_instructions,
            },
        }

    if isinstance(method, str) and method.startswith("notifications/"):
        return None

    if method == "tools/list":
        tools = await _list_tools()
        if isinstance(tools, dict) and tools.get("error"):
            return _rpc_error(rpc_id, -32603, str(tools.get("error")))
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": (tools or {}).get("result", {}),
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        if not isinstance(tool_name, str) or not tool_name:
            return _rpc_error(rpc_id, -32602, "Invalid request parameters", "Missing tool name")

        args = params.get("arguments", {})
        if not isinstance(args, dict):
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    args = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    args = {}
            else:
                args = {}

        if tool_name in ("workflow_create", "workflow_update") and "definition" in args:
            args = dict(args)
            args["definition"] = normalize_workflow_nodes(args["definition"])

        args = _normalize_proxy_tool_args(tool_name, args)

        # Local virtual orchestrator tools (proxy-side).
        if tool_name == "agent_chat_inject":
            payload = _agent_inject_message(args, source="external", client_id=client_id)
            err_msg = payload.get("error") if isinstance(payload, dict) else None
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result=payload,
                duration_ms=0,
                error=err_msg,
                source="external",
                client_id=client_id,
            )
            if err_msg:
                return _rpc_error(rpc_id, -32012, err_msg, payload)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}}

        if tool_name == "agent_chat_sessions":
            payload = _agent_session_snapshot(args)
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result=payload,
                duration_ms=0,
                error=None,
                source="external",
                client_id=client_id,
            )
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
            payload, err_msg = await _agent_delegate_call(
                caller_slot,
                caller_session_id,
                caller_depth,
                args,
                source="external",
                client_id=client_id,
                call_tool_fn=_call_tool,
                list_tools_fn=_list_tools,
                parse_result_fn=_parse_mcp_result_payload,
                normalize_args_fn=_normalize_proxy_tool_args,
                broadcast_fn=lambda **kw: activity_hub.add_entry(**kw),
            )
            duration_ms = int((time.time() - started) * 1000)
            out = payload if isinstance(payload, dict) else {"result": payload}
            if err_msg:
                if isinstance(out, dict):
                    out.setdefault("error", err_msg)
                activity_hub.add_entry(tool=tool_name, args=args, result=out, duration_ms=duration_ms, error=err_msg, source="external", client_id=client_id)
                return _rpc_error(rpc_id, -32013, err_msg, out)
            activity_hub.add_entry(tool=tool_name, args=args, result=out, duration_ms=duration_ms, error=None, source="external", client_id=client_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}}

        capacity_guard = None
        if tool_name in _CAPACITY_GUARD_TOOLS:
            runtime_capacity = _runtime_capacity_snapshot()
            capacity_guard = _capacity_guard_decision(tool_name, args, runtime_capacity)
            if capacity_guard.get("action") == "block":
                err_msg = f"Capacity guard blocked {tool_name}"
                payload = {
                    "capacity_guard": capacity_guard,
                    "runtime_capacity": runtime_capacity,
                }
                activity_hub.add_entry(
                    tool=tool_name,
                    args=args,
                    result=payload,
                    duration_ms=0,
                    error=err_msg,
                    source="external",
                    client_id=client_id,
                )
                return _rpc_error(rpc_id, -32011, err_msg, payload)

        slot_guard = await _slot_ready_guard(tool_name, args)
        if slot_guard:
            err_msg = slot_guard.get("error") or f"Slot readiness guard blocked {tool_name}"
            payload = {"slot_guard": slot_guard}
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result=payload,
                duration_ms=0,
                error=err_msg,
                source="external",
                client_id=client_id,
            )
            return _rpc_error(rpc_id, -32010, err_msg, payload)

        claim, busy_guard = await _claim_slot_execution(tool_name, args, "external", client_id)
        if busy_guard:
            err_msg = busy_guard.get("error") or f"Slot busy while calling {tool_name}"
            payload = {"slot_busy": busy_guard}
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result=payload,
                duration_ms=0,
                error=err_msg,
                source="external",
                client_id=client_id,
            )
            return _rpc_error(rpc_id, -32011, err_msg, payload)

        if tool_name in _LIVE_START_TOOLS:
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result={"_phase": "start", "state": "running"},
                duration_ms=0,
                error=None,
                source="external",
                client_id=client_id,
            )

        # ── Server-side agent orchestration for MCP transport ──
        if tool_name == "agent_chat":
            try:
                orchestrated = await _server_side_agent_chat(
                    args, source="external", client_id=client_id,
                    call_tool_fn=_call_tool, list_tools_fn=_list_tools,
                    parse_result_fn=_parse_mcp_result_payload,
                    normalize_args_fn=_normalize_proxy_tool_args,
                    broadcast_fn=lambda **kw: activity_hub.add_entry(**kw),
                )
                activity_hub.add_entry(
                    tool="agent_chat", args=args,
                    result=orchestrated.get("result"),
                    duration_ms=0,
                    error=orchestrated.get("error"),
                    source="external", client_id=client_id,
                )
                if orchestrated.get("error"):
                    return _rpc_error(rpc_id, -32603, orchestrated["error"])
                return {"jsonrpc": "2.0", "id": rpc_id, "result": orchestrated.get("result", orchestrated)}
            finally:
                await _release_slot_execution(claim)

        start = time.time()
        try:
            result = await _call_tool(tool_name, args)
            result = await postprocess_tool_result(tool_name, args, result, _call_tool, activity_hub=activity_hub)
            duration_ms = int((time.time() - start) * 1000)

            error_str = result.get("error") if isinstance(result.get("error"), str) else None
            activity_hub.add_entry(
                tool=tool_name,
                args=args,
                result=result.get("result") if isinstance(result, dict) else result,
                duration_ms=duration_ms,
                error=error_str,
                source="external",
                client_id=client_id,
            )
            _broadcast_agent_inner_calls(tool_name, result.get("result") if isinstance(result, dict) else result, duration_ms, source="external", client_id=client_id)

            if error_str:
                return _rpc_error(rpc_id, -32603, error_str)

            out = result.get("result", result) if isinstance(result, dict) else result
            if capacity_guard and isinstance(out, dict):
                out = dict(out)
                out["capacity_guard"] = capacity_guard
            return {"jsonrpc": "2.0", "id": rpc_id, "result": out}
        finally:
            await _release_slot_execution(claim)

    return _rpc_error(rpc_id, -32601, f"Method not found: {method}")


def _rpc_error(rpc_id, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": err}


# Mount after explicit routes.
app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")

# Compatibility alias for resources some clients may request.
app.mount("/media", StaticFiles(directory=str(settings.frontend_dir)), name="media")

# Register route groups.
app.include_router(create_dreamer_router(_call_tool))
app.include_router(create_vast_router(_call_tool, activity_hub))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.app_port)
