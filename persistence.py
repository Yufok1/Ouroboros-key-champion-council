"""
Per-user persistence via HuggingFace Dataset repos.

Each Space owner gets a private dataset repo: {username}/champion-council-state
On save:  brain state, FelixBag, workflows, slot manifest → uploaded to dataset
On load:  pull from dataset → restore into capsule via MCP tools

Requires HF_TOKEN with write access (set as Space secret).
"""
import os
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STATE_REPO_SUFFIX = "champion-council-state"
BRAIN_FILE = "brain_state.pkl"
BAG_FILE = "bag_export.json"
WORKFLOWS_FILE = "workflows.json"
SLOTS_FILE = "slot_manifest.json"

_hf_api = None
_repo_id: str | None = None
_save_lock = asyncio.Lock()
_last_save_ts: float = 0
SAVE_COOLDOWN = 120  # minimum seconds between auto-saves


def _get_api():
    global _hf_api
    if _hf_api is None:
        from huggingface_hub import HfApi
        _hf_api = HfApi()
    return _hf_api


def _get_repo_id() -> str | None:
    """Derive the per-user dataset repo id from Space environment."""
    global _repo_id
    if _repo_id:
        return _repo_id

    # HF injects SPACE_AUTHOR_NAME for the Space owner
    author = os.environ.get("SPACE_AUTHOR_NAME", "")
    if not author:
        # Fallback: try to get from SPACE_ID (format: "author/space-name")
        space_id = os.environ.get("SPACE_ID", "")
        if "/" in space_id:
            author = space_id.split("/")[0]

    if not author:
        # Last resort: try whoami
        try:
            api = _get_api()
            info = api.whoami()
            author = info.get("name", "")
        except Exception:
            pass

    if not author:
        print("[PERSIST] Cannot determine HF username — persistence disabled")
        return None

    _repo_id = f"{author}/{STATE_REPO_SUFFIX}"
    return _repo_id


def _ensure_repo() -> bool:
    """Create the private dataset repo if it doesn't exist."""
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
        print(f"[PERSIST] Dataset repo ready: {repo_id}")
        return True
    except Exception as e:
        print(f"[PERSIST] Failed to create/verify repo {repo_id}: {e}")
        return False



# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

async def _call_capsule_tool(call_tool_fn, name: str, args: dict) -> dict | None:
    """Call a capsule MCP tool, return parsed result or None."""
    try:
        result = await call_tool_fn(name, args)
        if isinstance(result, dict) and "error" in result:
            print(f"[PERSIST] Tool {name} error: {result['error']}")
            return None
        # Unwrap MCP envelope
        if isinstance(result, dict) and "result" in result:
            content = result["result"].get("content", [])
            if content and isinstance(content[0], dict):
                text = content[0].get("text", "")
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return {"text": text}
        return result
    except Exception as e:
        print(f"[PERSIST] Tool {name} failed: {e}")
        return None


async def save_state(call_tool_fn) -> bool:
    """Save all capsule state to the HF dataset repo.

    Args:
        call_tool_fn: async function(tool_name, args) -> dict that calls MCP tools
    """
    import time as _time
    global _last_save_ts

    async with _save_lock:
        now = _time.time()
        if now - _last_save_ts < SAVE_COOLDOWN:
            print(f"[PERSIST] Save cooldown ({int(SAVE_COOLDOWN - (now - _last_save_ts))}s remaining)")
            return False

        if not _ensure_repo():
            return False

        repo_id = _get_repo_id()
        api = _get_api()
        tmpdir = Path(tempfile.mkdtemp(prefix="cc_persist_"))
        saved_files = []

        try:
            # 1. Brain state
            brain_path = tmpdir / BRAIN_FILE
            result = await _call_capsule_tool(call_tool_fn, "save_state", {"path": str(brain_path)})
            if result and brain_path.exists():
                saved_files.append((brain_path, BRAIN_FILE))
                print(f"[PERSIST] Brain state saved ({brain_path.stat().st_size:,} bytes)")

            # 2. FelixBag
            bag_path = tmpdir / BAG_FILE
            result = await _call_capsule_tool(call_tool_fn, "save_bag", {"file_path": str(bag_path)})
            if result and bag_path.exists():
                saved_files.append((bag_path, BAG_FILE))
                print(f"[PERSIST] Bag saved ({bag_path.stat().st_size:,} bytes)")

            # 3. Workflows — export all definitions
            wf_list = await _call_capsule_tool(call_tool_fn, "workflow_list", {})
            workflows = []
            if wf_list and isinstance(wf_list.get("workflows"), list):
                for wf in wf_list["workflows"]:
                    wf_id = wf.get("id") or wf.get("workflow_id")
                    if wf_id:
                        wf_def = await _call_capsule_tool(call_tool_fn, "workflow_get", {"workflow_id": wf_id})
                        if wf_def and "nodes" in wf_def:
                            workflows.append(wf_def)
            wf_path = tmpdir / WORKFLOWS_FILE
            wf_path.write_text(json.dumps(workflows, indent=2))
            saved_files.append((wf_path, WORKFLOWS_FILE))
            print(f"[PERSIST] {len(workflows)} workflows saved")

            # 4. Slot manifest — which models are plugged where
            slots_result = await _call_capsule_tool(call_tool_fn, "list_slots", {})
            slot_manifest = []
            if slots_result:
                all_ids = slots_result.get("all_ids", [])
                total = slots_result.get("total", len(all_ids))
                for i in range(total):
                    name = all_ids[i] if i < len(all_ids) else f"slot_{i}"
                    default_name = f"slot_{i}"
                    if name != default_name:
                        # Non-default name means a model was plugged and renamed
                        # Try to get full slot info
                        slot_info = await _call_capsule_tool(call_tool_fn, "slot_info", {"slot": i})
                        model_id = None
                        if slot_info:
                            model_id = (slot_info.get("model_source")
                                       or slot_info.get("model_id")
                                       or slot_info.get("model"))
                        slot_manifest.append({
                            "index": i,
                            "name": name,
                            "model_id": model_id,
                        })

            manifest_path = tmpdir / SLOTS_FILE
            manifest_path.write_text(json.dumps(slot_manifest, indent=2))
            saved_files.append((manifest_path, SLOTS_FILE))
            print(f"[PERSIST] {len(slot_manifest)} plugged slots saved")

            # 5. Upload all files to dataset repo
            for local_path, repo_path in saved_files:
                api.upload_file(
                    path_or_fileobj=str(local_path),
                    path_in_repo=repo_path,
                    repo_id=repo_id,
                    repo_type="dataset",
                    commit_message=f"Auto-save {repo_path} at {datetime.now(timezone.utc).isoformat()}",
                )

            _last_save_ts = _time.time()
            print(f"[PERSIST] ✓ State saved to {repo_id} ({len(saved_files)} files)")
            return True

        except Exception as e:
            print(f"[PERSIST] Save failed: {e}")
            return False
        finally:
            # Cleanup temp files
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Restore helpers
# ---------------------------------------------------------------------------

async def restore_state(call_tool_fn) -> bool:
    """Restore capsule state from the HF dataset repo.

    Args:
        call_tool_fn: async function(tool_name, args) -> dict that calls MCP tools
    """
    repo_id = _get_repo_id()
    if not repo_id:
        return False

    api = _get_api()
    tmpdir = Path(tempfile.mkdtemp(prefix="cc_restore_"))
    restored = []

    try:
        # Check if repo exists
        try:
            api.repo_info(repo_id=repo_id, repo_type="dataset")
        except Exception:
            print(f"[PERSIST] No state repo found ({repo_id}) — starting fresh")
            return False

        # 1. Brain state
        try:
            brain_path = api.hf_hub_download(
                repo_id=repo_id, repo_type="dataset",
                filename=BRAIN_FILE, local_dir=str(tmpdir),
            )
            if brain_path and Path(brain_path).exists():
                result = await _call_capsule_tool(call_tool_fn, "import_brain", {"path": brain_path})
                if result and not result.get("error"):
                    restored.append("brain")
                    print(f"[PERSIST] Brain state restored")
        except Exception as e:
            print(f"[PERSIST] Brain restore skipped: {e}")

        # 2. FelixBag
        try:
            bag_path = api.hf_hub_download(
                repo_id=repo_id, repo_type="dataset",
                filename=BAG_FILE, local_dir=str(tmpdir),
            )
            if bag_path and Path(bag_path).exists():
                result = await _call_capsule_tool(call_tool_fn, "load_bag", {"file_path": bag_path})
                if result and not result.get("error"):
                    restored.append("bag")
                    print(f"[PERSIST] FelixBag restored")
        except Exception as e:
            print(f"[PERSIST] Bag restore skipped: {e}")

        # 3. Workflows
        try:
            wf_path = api.hf_hub_download(
                repo_id=repo_id, repo_type="dataset",
                filename=WORKFLOWS_FILE, local_dir=str(tmpdir),
            )
            if wf_path and Path(wf_path).exists():
                workflows = json.loads(Path(wf_path).read_text())
                wf_count = 0
                for wf_def in workflows:
                    # Ensure tool_name normalization
                    for node in wf_def.get("nodes", []):
                        t = node.get("tool_name") or node.get("tool")
                        if t:
                            node["tool_name"] = t
                            node["tool"] = t
                        if node.get("type") == "tool_call":
                            node["type"] = "tool"
                    result = await _call_capsule_tool(
                        call_tool_fn, "workflow_create",
                        {"definition": json.dumps(wf_def)}
                    )
                    if result and not result.get("error"):
                        wf_count += 1
                restored.append(f"{wf_count} workflows")
                print(f"[PERSIST] {wf_count} workflows restored")
        except Exception as e:
            print(f"[PERSIST] Workflow restore skipped: {e}")

        # 4. Slot manifest — re-plug models
        try:
            manifest_path = api.hf_hub_download(
                repo_id=repo_id, repo_type="dataset",
                filename=SLOTS_FILE, local_dir=str(tmpdir),
            )
            if manifest_path and Path(manifest_path).exists():
                manifest = json.loads(Path(manifest_path).read_text())
                plug_count = 0
                for slot_entry in manifest:
                    model_id = slot_entry.get("model_id")
                    slot_name = slot_entry.get("name")
                    if model_id:
                        print(f"[PERSIST] Re-plugging slot {slot_entry['index']}: {model_id} as '{slot_name}'")
                        result = await _call_capsule_tool(
                            call_tool_fn, "hub_plug",
                            {"model_id": model_id, "slot_name": slot_name or ""}
                        )
                        if result and not result.get("error"):
                            plug_count += 1
                        else:
                            print(f"[PERSIST] Failed to re-plug {model_id}: {result}")
                restored.append(f"{plug_count} models")
                print(f"[PERSIST] {plug_count} models re-plugged")
        except Exception as e:
            print(f"[PERSIST] Slot restore skipped: {e}")

        print(f"[PERSIST] ✓ Restore complete: {', '.join(restored) if restored else 'nothing to restore'}")
        return len(restored) > 0

    except Exception as e:
        print(f"[PERSIST] Restore failed: {e}")
        return False
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Periodic auto-save (runs as background task)
# ---------------------------------------------------------------------------

_autosave_task: asyncio.Task | None = None

async def _autosave_loop(call_tool_fn, interval: int = 300):
    """Background loop that saves state every `interval` seconds."""
    import time as _time
    while True:
        await asyncio.sleep(interval)
        try:
            print("[PERSIST] Auto-save triggered")
            await save_state(call_tool_fn)
        except Exception as e:
            print(f"[PERSIST] Auto-save error: {e}")


def start_autosave(call_tool_fn, interval: int = 300):
    """Start the background auto-save loop."""
    global _autosave_task
    if _autosave_task is not None:
        return
    loop = asyncio.get_event_loop()
    _autosave_task = loop.create_task(_autosave_loop(call_tool_fn, interval))
    print(f"[PERSIST] Auto-save started (every {interval}s)")


def stop_autosave():
    """Cancel the background auto-save loop."""
    global _autosave_task
    if _autosave_task:
        _autosave_task.cancel()
        _autosave_task = None
        print("[PERSIST] Auto-save stopped")


def is_available() -> bool:
    """Check if persistence is configured (HF token + username available)."""
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        return False
    return _get_repo_id() is not None
