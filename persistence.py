"""
Champion Council persistence (Space runtime).

Goals:
- Keep FelixBag/workflows/slots/brain durable across Space restarts and code pushes.
- Work without HF_TOKEN (local-first snapshots, ideally on /data when available).
- Optionally sync the same snapshots to a private HF dataset repo.

Mode selection (env):
- PERSISTENCE_MODE=local | hf | both   (default: both)
- PERSISTENCE_DATA_DIR=/path           (default: /data/champion-council-state if possible)
- AUTOSAVE_INTERVAL=seconds            (server controls loop interval)
- SAVE_COOLDOWN=seconds                (default: 30)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable


# ---------------------------------------------------------------------------
# Files / layout
# ---------------------------------------------------------------------------

STATE_REPO_SUFFIX = "champion-council-state"
BRAIN_FILE = "brain_state.pkl"
BAG_FILE = "bag_export.json"
WORKFLOWS_FILE = "workflows.json"
SLOTS_FILE = "slot_manifest.json"
META_FILE = "state_meta.json"

LOCAL_LAYOUT = {
    BRAIN_FILE: Path("brain") / BRAIN_FILE,
    BAG_FILE: Path("bag") / BAG_FILE,
    WORKFLOWS_FILE: Path("workflows") / WORKFLOWS_FILE,
    SLOTS_FILE: Path("slots") / SLOTS_FILE,
    META_FILE: Path("config") / META_FILE,
}


# ---------------------------------------------------------------------------
# Global state / config
# ---------------------------------------------------------------------------

_VALID_MODES = ("local", "hf", "both")
_MODE = os.environ.get("PERSISTENCE_MODE", "both").strip().lower()
if _MODE not in _VALID_MODES:
    _MODE = "both"

SAVE_COOLDOWN = int(os.environ.get("SAVE_COOLDOWN", "30"))

_hf_api = None
_repo_id: str | None = None
_save_lock = asyncio.Lock()
_last_save_ts: float = 0.0
_autosave_task: asyncio.Task | None = None


def _log(msg: str) -> None:
    print(f"[PERSIST] {msg}")


def _env_token() -> str:
    return (
        os.environ.get("HF_TOKEN", "")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN", "")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")
    ).strip()


def _candidate_data_dirs() -> list[Path]:
    explicit = os.environ.get("PERSISTENCE_DATA_DIR", "").strip()
    if explicit:
        return [Path(explicit)]

    candidates: list[Path] = []

    # HF Spaces persistent storage location (when enabled)
    if Path("/data").exists():
        candidates.append(Path("/data/champion-council-state"))

    # Local fallback in repo working directory
    candidates.append(Path("./data/champion-council-state"))

    return candidates


def _resolve_data_dir() -> tuple[Path, bool]:
    for cand in _candidate_data_dirs():
        try:
            cand.mkdir(parents=True, exist_ok=True)
            test = cand / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return cand, True
        except Exception:
            continue
    return Path("./data/champion-council-state"), False


_DATA_DIR, _DATA_WRITABLE = _resolve_data_dir()
_LOCAL_ENABLED = (_MODE in ("local", "both")) and _DATA_WRITABLE
_HF_TOKEN = _env_token()
_HF_ENABLED = (_MODE in ("hf", "both")) and bool(_HF_TOKEN)

if _LOCAL_ENABLED:
    for rel in LOCAL_LAYOUT.values():
        (_DATA_DIR / rel).parent.mkdir(parents=True, exist_ok=True)

_log(
    "initialized "
    f"mode={_MODE} local_enabled={_LOCAL_ENABLED} hf_enabled={_HF_ENABLED} data_dir={_DATA_DIR}"
)


# ---------------------------------------------------------------------------
# HF helpers
# ---------------------------------------------------------------------------


def _get_api():
    global _hf_api
    if not _HF_ENABLED:
        return None
    if _hf_api is None:
        from huggingface_hub import HfApi

        _hf_api = HfApi(token=_HF_TOKEN)
    return _hf_api


def _get_repo_id() -> str | None:
    """Derive per-owner dataset repo: {author}/champion-council-state."""
    global _repo_id
    if _repo_id:
        return _repo_id

    author = os.environ.get("SPACE_AUTHOR_NAME", "")
    if not author:
        space_id = os.environ.get("SPACE_ID", "")
        if "/" in space_id:
            author = space_id.split("/", 1)[0]

    if not author and _HF_ENABLED:
        try:
            api = _get_api()
            info = api.whoami() if api else {}
            author = info.get("name", "")
        except Exception:
            author = ""

    if not author:
        return None

    _repo_id = f"{author}/{STATE_REPO_SUFFIX}"
    return _repo_id


def _ensure_repo() -> bool:
    if not _HF_ENABLED:
        return False
    repo_id = _get_repo_id()
    if not repo_id:
        return False
    try:
        api = _get_api()
        api.create_repo(
            repo_id=repo_id,
            repo_type="dataset",
            private=True,
            exist_ok=True,
        )
        _log(f"hf repo ready: {repo_id}")
        return True
    except Exception as exc:
        _log(f"hf repo ensure failed ({repo_id}): {exc}")
        return False


# ---------------------------------------------------------------------------
# Capsule helpers
# ---------------------------------------------------------------------------

CallToolFn = Callable[[str, dict], Awaitable[dict]]


async def _call_capsule_tool(call_tool_fn: CallToolFn, name: str, args: dict) -> dict | list | None:
    """Call a capsule MCP tool and return parsed payload (best effort)."""
    try:
        result = await call_tool_fn(name, args)
        if isinstance(result, dict) and result.get("error"):
            _log(f"tool {name} returned error: {result.get('error')}")
            return None
        if isinstance(result, dict) and "result" in result:
            content = result["result"].get("content", [])
            if content and isinstance(content[0], dict):
                text = content[0].get("text", "")
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return {"text": text}
        return result if isinstance(result, (dict, list)) else None
    except Exception as exc:
        _log(f"tool {name} exception: {exc}")
        return None


def _normalize_workflow_nodes(defn: dict) -> dict:
    out = dict(defn or {})
    nodes = out.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "tool_call":
                node["type"] = "tool"
            t = node.get("tool_name") or node.get("tool")
            if t:
                node["tool_name"] = t
                node["tool"] = t
    out["nodes"] = nodes
    return out


async def _collect_state_files(call_tool_fn: CallToolFn, tmpdir: Path) -> dict[str, Path]:
    """Export all runtime state into temp files; return filename -> path."""
    files: dict[str, Path] = {}
    success_signals = 0

    # 1) Brain
    brain_path = tmpdir / BRAIN_FILE
    brain_result = await _call_capsule_tool(call_tool_fn, "save_state", {"path": str(brain_path)})
    if brain_result is not None:
        success_signals += 1
    if brain_result is not None and brain_path.exists():
        files[BRAIN_FILE] = brain_path

    # 2) FelixBag
    bag_path = tmpdir / BAG_FILE
    bag_result = await _call_capsule_tool(call_tool_fn, "save_bag", {"file_path": str(bag_path)})
    if bag_result is not None:
        success_signals += 1
    if bag_result is not None and bag_path.exists():
        files[BAG_FILE] = bag_path

    # 3) Workflows
    workflows: list[dict] = []
    wf_path = tmpdir / WORKFLOWS_FILE
    wf_list = await _call_capsule_tool(call_tool_fn, "workflow_list", {})
    if wf_list is not None:
        success_signals += 1
    if isinstance(wf_list, dict) and isinstance(wf_list.get("workflows"), list):
        for wf in wf_list["workflows"]:
            wf_id = wf.get("id") or wf.get("workflow_id")
            if not wf_id:
                continue
            wf_def = await _call_capsule_tool(call_tool_fn, "workflow_get", {"workflow_id": wf_id})
            if isinstance(wf_def, dict) and wf_def.get("nodes"):
                workflows.append(wf_def)
        wf_path.write_text(json.dumps(workflows, indent=2), encoding="utf-8")
        files[WORKFLOWS_FILE] = wf_path

    # 4) Slot manifest
    slots_path = tmpdir / SLOTS_FILE
    slot_manifest = []
    slots_result = await _call_capsule_tool(call_tool_fn, "list_slots", {})
    if slots_result is not None:
        success_signals += 1
    if isinstance(slots_result, dict):
        all_ids = slots_result.get("all_ids", [])
        total = slots_result.get("total", len(all_ids))
        for i in range(total):
            name = all_ids[i] if i < len(all_ids) else f"slot_{i}"
            if name == f"slot_{i}":
                continue
            slot_info = await _call_capsule_tool(call_tool_fn, "slot_info", {"slot": i})
            model_id = None
            if isinstance(slot_info, dict):
                model_id = slot_info.get("model_source") or slot_info.get("model_id") or slot_info.get("model")
            slot_manifest.append({"index": i, "name": name, "model_id": model_id})

        slots_path.write_text(json.dumps(slot_manifest, indent=2), encoding="utf-8")
        files[SLOTS_FILE] = slots_path

    # No capsule responses at all? don't overwrite previous persistence snapshot.
    if success_signals == 0:
        return {}

    # 5) Metadata
    meta_path = tmpdir / META_FILE
    meta = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "mode": _MODE,
        "local_enabled": _LOCAL_ENABLED,
        "hf_enabled": _HF_ENABLED,
        "workflow_count": len(workflows),
        "slot_count": len(slot_manifest),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    files[META_FILE] = meta_path

    return files


def _local_file_map() -> dict[str, Path]:
    return {name: _DATA_DIR / rel for name, rel in LOCAL_LAYOUT.items()}


def _read_meta_timestamp(path: Path | None) -> float | None:
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("saved_at")
        if not raw:
            return None
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


async def _restore_from_files(call_tool_fn: CallToolFn, files: dict[str, Path]) -> int:
    restored = 0

    # 1) Brain
    brain = files.get(BRAIN_FILE)
    if brain and brain.exists():
        result = await _call_capsule_tool(call_tool_fn, "import_brain", {"path": str(brain)})
        if result is not None:
            restored += 1

    # 2) Bag
    bag = files.get(BAG_FILE)
    if bag and bag.exists():
        result = await _call_capsule_tool(call_tool_fn, "load_bag", {"file_path": str(bag)})
        if result is not None:
            restored += 1

    # 3) Workflows
    workflows_file = files.get(WORKFLOWS_FILE)
    if workflows_file and workflows_file.exists():
        try:
            workflows = json.loads(workflows_file.read_text(encoding="utf-8"))
            wf_ok = 0
            for wf_def in workflows:
                normalized = _normalize_workflow_nodes(wf_def if isinstance(wf_def, dict) else {})
                if not normalized.get("id"):
                    continue

                # Create-first, update-on-conflict fallback.
                created = await _call_capsule_tool(
                    call_tool_fn,
                    "workflow_create",
                    {"definition": json.dumps(normalized)},
                )
                if created is not None and not (isinstance(created, dict) and created.get("error")):
                    wf_ok += 1
                    continue

                await _call_capsule_tool(
                    call_tool_fn,
                    "workflow_update",
                    {
                        "workflow_id": normalized.get("id"),
                        "definition": json.dumps(normalized),
                    },
                )
                wf_ok += 1

            if wf_ok > 0:
                restored += 1
        except Exception as exc:
            _log(f"workflow restore failed: {exc}")

    # 4) Slot manifest
    slot_file = files.get(SLOTS_FILE)
    if slot_file and slot_file.exists():
        try:
            manifest = json.loads(slot_file.read_text(encoding="utf-8"))
            plug_attempts = 0
            for slot_entry in manifest:
                if not isinstance(slot_entry, dict):
                    continue
                model_id = slot_entry.get("model_id")
                slot_name = slot_entry.get("name") or ""
                if not model_id:
                    continue
                await _call_capsule_tool(
                    call_tool_fn,
                    "hub_plug",
                    {"model_id": model_id, "slot_name": slot_name},
                )
                plug_attempts += 1
            if plug_attempts > 0:
                restored += 1
        except Exception as exc:
            _log(f"slot restore failed: {exc}")

    return restored


# ---------------------------------------------------------------------------
# Public API used by server.py
# ---------------------------------------------------------------------------


async def save_state(call_tool_fn: CallToolFn, force: bool = False) -> bool:
    """Save state to local snapshot and/or HF dataset according to mode."""
    global _last_save_ts

    async with _save_lock:
        now = time.time()
        if not force and (now - _last_save_ts) < SAVE_COOLDOWN:
            remaining = int(SAVE_COOLDOWN - (now - _last_save_ts))
            _log(f"save skipped by cooldown ({remaining}s remaining)")
            return False

        tmpdir = Path(tempfile.mkdtemp(prefix="cc_space_save_"))
        try:
            files = await _collect_state_files(call_tool_fn, tmpdir)
            if not files:
                _log("save aborted: no state files collected")
                return False

            # Local snapshot
            if _LOCAL_ENABLED:
                for filename, src in files.items():
                    dest = _DATA_DIR / LOCAL_LAYOUT.get(filename, Path(filename))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    _log(f"local save: {filename} -> {dest}")

            # Optional HF sync
            if _HF_ENABLED and _ensure_repo():
                api = _get_api()
                repo_id = _get_repo_id()
                for filename, src in files.items():
                    api.upload_file(
                        path_or_fileobj=str(src),
                        path_in_repo=filename,
                        repo_id=repo_id,
                        repo_type="dataset",
                        commit_message=f"autosave {filename} @ {datetime.now(timezone.utc).isoformat()}",
                    )
                    _log(f"hf upload: {filename} -> {repo_id}")

            _last_save_ts = time.time()
            _log("save complete")
            return True
        except Exception as exc:
            _log(f"save failed: {exc}")
            return False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


async def restore_state(call_tool_fn: CallToolFn) -> bool:
    """Restore state from local snapshot and/or HF sync snapshot.

    In "both" mode, we avoid stale HF overrides by comparing state_meta timestamps.
    HF restore only applies when HF snapshot is newer than local snapshot.
    """
    restored = 0
    local_meta_ts = None

    # Local restore
    if _LOCAL_ENABLED:
        local_files = _local_file_map()
        local_meta_ts = _read_meta_timestamp(local_files.get(META_FILE))
        restored += await _restore_from_files(call_tool_fn, local_files)
        _log(f"local restore complete (restored={restored}, meta_ts={local_meta_ts})")

    # HF restore
    if _HF_ENABLED and _get_repo_id():
        api = _get_api()
        repo_id = _get_repo_id()
        tmpdir = Path(tempfile.mkdtemp(prefix="cc_space_restore_"))
        try:
            try:
                api.repo_info(repo_id=repo_id, repo_type="dataset")
            except Exception:
                _log(f"hf restore skipped: repo unavailable ({repo_id})")
                return restored > 0

            hf_files: dict[str, Path] = {}
            for filename in (BRAIN_FILE, BAG_FILE, WORKFLOWS_FILE, SLOTS_FILE, META_FILE):
                try:
                    downloaded = api.hf_hub_download(
                        repo_id=repo_id,
                        repo_type="dataset",
                        filename=filename,
                        local_dir=str(tmpdir),
                    )
                    p = Path(downloaded)
                    if p.exists():
                        hf_files[filename] = p
                except Exception as exc:
                    _log(f"hf restore file skipped ({filename}): {exc}")

            hf_meta_ts = _read_meta_timestamp(hf_files.get(META_FILE))

            apply_hf = True
            if local_meta_ts is not None and hf_meta_ts is not None and hf_meta_ts <= local_meta_ts:
                apply_hf = False

            if apply_hf:
                restored += await _restore_from_files(call_tool_fn, hf_files)
                _log(f"hf restore complete (restored={restored}, meta_ts={hf_meta_ts})")
            else:
                _log(
                    "hf restore skipped: local snapshot is newer/equal "
                    f"(local_ts={local_meta_ts}, hf_ts={hf_meta_ts})"
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    _log(f"restore complete restored={restored}")
    return restored > 0


async def _autosave_loop(call_tool_fn: CallToolFn, interval: int = 60):
    while True:
        await asyncio.sleep(interval)
        try:
            _log("autosave tick")
            await save_state(call_tool_fn, force=False)
        except Exception as exc:
            _log(f"autosave error: {exc}")


def start_autosave(call_tool_fn: CallToolFn, interval: int = 60):
    global _autosave_task
    if _autosave_task is not None:
        return
    _autosave_task = asyncio.create_task(_autosave_loop(call_tool_fn, interval))
    _log(f"autosave started interval={interval}s")


def stop_autosave():
    global _autosave_task
    if _autosave_task:
        _autosave_task.cancel()
        _autosave_task = None
        _log("autosave stopped")


def is_available() -> bool:
    if _MODE == "local":
        return _LOCAL_ENABLED
    if _MODE == "hf":
        return _HF_ENABLED and bool(_get_repo_id())
    return _LOCAL_ENABLED or (_HF_ENABLED and bool(_get_repo_id()))


def status() -> dict:
    data_dir_norm = str(_DATA_DIR).replace("\\", "/")
    durable_local_volume = data_dir_norm.startswith("/data/") or data_dir_norm == "/data"
    durable_hf_sync = _HF_ENABLED and bool(_get_repo_id())
    durable_across_redeploy = ("local" in (_MODE, "both") and durable_local_volume and _LOCAL_ENABLED) or durable_hf_sync

    warning = ""
    if not durable_across_redeploy:
        warning = (
            "Persistence is runtime-local only (ephemeral across Space rebuild/push). "
            "Enable HF Space Persistent Storage (/data) or set HF_TOKEN for dataset sync."
        )

    return {
        "mode": _MODE,
        "available": is_available(),
        "local_enabled": _LOCAL_ENABLED,
        "hf_enabled": _HF_ENABLED,
        "repo_id": _get_repo_id(),
        "has_hf_token": bool(_HF_TOKEN),
        "data_dir": str(_DATA_DIR),
        "data_writable": _DATA_WRITABLE,
        "durable_local_volume": durable_local_volume,
        "durable_hf_sync": durable_hf_sync,
        "durable_across_redeploy": durable_across_redeploy,
        "warning": warning,
        "save_cooldown": SAVE_COOLDOWN,
        "last_save_ts": _last_save_ts,
        "autosave_running": _autosave_task is not None,
    }
