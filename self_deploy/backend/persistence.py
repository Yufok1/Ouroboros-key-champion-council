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

from .postprocessing import normalize_workflow_nodes


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


class PersistenceManager:
    """Dual-mode persistence manager: local filesystem + optional HF dataset sync."""

    def __init__(
        self,
        mode: str,
        data_dir: Path,
        hf_token: str = "",
        space_author_name: str = "",
        space_id: str = "",
        save_cooldown: int = 120,
    ):
        self.mode = (mode or "local").strip().lower()
        if self.mode not in ("local", "hf", "both"):
            self.mode = "local"

        self.data_dir = data_dir
        self.hf_token = hf_token or os.environ.get("HF_TOKEN", "")
        self.space_author_name = space_author_name or os.environ.get("SPACE_AUTHOR_NAME", "")
        self.space_id = space_id or os.environ.get("SPACE_ID", "")
        self.save_cooldown = save_cooldown

        self._save_lock = asyncio.Lock()
        self._last_save_ts = 0.0
        self._autosave_task: asyncio.Task | None = None

        self._hf_api = None
        self._repo_id: str | None = None

        self.bag_shrink_guard_enabled = str(os.environ.get("PERSIST_BAG_SHRINK_GUARD", "1")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        try:
            ratio = float(os.environ.get("PERSIST_BAG_SHRINK_RATIO", "0.70"))
        except Exception:
            ratio = 0.70
        self.bag_shrink_guard_ratio = min(0.99, max(0.05, ratio))
        try:
            min_baseline = int(os.environ.get("PERSIST_BAG_SHRINK_MIN_BASELINE", "40"))
        except Exception:
            min_baseline = 40
        self.bag_shrink_guard_min_baseline = max(1, min_baseline)
        self._bag_guard_baseline_count: int | None = None

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_local_dirs()
        self._log(
            f"initialized mode={self.mode} local={self.local_enabled} "
            f"hf={self.hf_enabled} data_dir={self.data_dir}"
        )

    def _log(self, message: str) -> None:
        print(f"[PERSIST] {message}")

    # ------------------------------------------------------------------
    # Status/config
    # ------------------------------------------------------------------

    @property
    def local_enabled(self) -> bool:
        return self.mode in ("local", "both")

    @property
    def hf_enabled(self) -> bool:
        return self.mode in ("hf", "both") and bool(self.hf_token)

    def _ensure_local_dirs(self) -> None:
        for rel in LOCAL_LAYOUT.values():
            (self.data_dir / rel).parent.mkdir(parents=True, exist_ok=True)

    def _read_meta_bag_count(self, path: Path | None) -> int | None:
        if not path or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            for key in ("bag_count", "bag_items", "saved", "total"):
                raw = data.get(key)
                try:
                    val = int(raw)
                except Exception:
                    continue
                if val >= 0:
                    return val
        except Exception:
            return None
        return None

    def _extract_bag_count(self, bag_result: dict | list | None, bag_path: Path) -> int | None:
        if isinstance(bag_result, dict):
            for key in ("saved", "count", "total", "items"):
                raw = bag_result.get(key)
                try:
                    val = int(raw)
                except Exception:
                    continue
                if val >= 0:
                    return val
        if bag_path.exists():
            try:
                payload = json.loads(bag_path.read_text(encoding="utf-8"))
                if isinstance(payload, (dict, list)):
                    return len(payload)
            except Exception:
                return None
        return None

    def _seed_bag_guard_baseline(self, count: int | None) -> None:
        if count is None:
            return
        try:
            count_i = int(count)
        except Exception:
            return
        if count_i < 0:
            return
        if self._bag_guard_baseline_count is None:
            self._bag_guard_baseline_count = count_i
            return
        self._bag_guard_baseline_count = max(self._bag_guard_baseline_count, count_i)

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "local_enabled": self.local_enabled,
            "hf_enabled": self.hf_enabled,
            "repo_id": self._get_repo_id(),
            "has_hf_token": bool(self.hf_token),
            "data_dir": str(self.data_dir),
            "last_save_ts": self._last_save_ts,
            "autosave_running": self._autosave_task is not None,
            "bag_shrink_guard": {
                "enabled": self.bag_shrink_guard_enabled,
                "ratio": self.bag_shrink_guard_ratio,
                "min_baseline": self.bag_shrink_guard_min_baseline,
                "baseline_count": self._bag_guard_baseline_count,
            },
        }

    # ------------------------------------------------------------------
    # HF helpers
    # ------------------------------------------------------------------

    def _get_hf_api(self):
        if not self.hf_enabled:
            return None
        if self._hf_api is None:
            from huggingface_hub import HfApi

            self._hf_api = HfApi(token=self.hf_token)
        return self._hf_api

    def _get_repo_id(self) -> str | None:
        if self._repo_id:
            return self._repo_id

        author = self.space_author_name
        if not author and "/" in self.space_id:
            author = self.space_id.split("/", 1)[0]

        if not author and self.hf_enabled:
            try:
                api = self._get_hf_api()
                info = api.whoami() if api else {}
                author = info.get("name", "")
            except Exception:
                author = ""

        if not author:
            return None

        self._repo_id = f"{author}/{STATE_REPO_SUFFIX}"
        return self._repo_id

    def _ensure_hf_repo(self) -> bool:
        if not self.hf_enabled:
            return False

        repo_id = self._get_repo_id()
        if not repo_id:
            return False

        try:
            api = self._get_hf_api()
            api.create_repo(
                repo_id=repo_id,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
            self._log(f"hf repo ready: {repo_id}")
            return True
        except Exception as exc:
            self._log(f"hf repo ensure failed ({repo_id}): {exc}")
            return False

    # ------------------------------------------------------------------
    # Capsule tool helper
    # ------------------------------------------------------------------

    async def _call_tool(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        name: str,
        args: dict,
    ) -> dict | list | None:
        try:
            result = await call_tool_fn(name, args)
            if isinstance(result, dict) and result.get("error"):
                self._log(f"tool {name} returned error: {result.get('error')}")
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
            self._log(f"tool {name} exception: {exc}")
            return None

    async def _collect_state_files(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        tmpdir: Path,
    ) -> dict[str, Path]:
        files: dict[str, Path] = {}
        success_signals = 0

        # 1) Brain
        brain_path = tmpdir / BRAIN_FILE
        result = await self._call_tool(call_tool_fn, "save_state", {"path": str(brain_path)})
        if result is not None:
            success_signals += 1
        if result is not None and brain_path.exists():
            files[BRAIN_FILE] = brain_path

        # 2) FelixBag
        bag_path = tmpdir / BAG_FILE
        result = await self._call_tool(call_tool_fn, "save_bag", {"file_path": str(bag_path)})
        bag_count = self._extract_bag_count(result, bag_path)
        if result is not None:
            success_signals += 1
        if result is not None and bag_path.exists():
            files[BAG_FILE] = bag_path

        # 3) Workflows
        wf_path = tmpdir / WORKFLOWS_FILE
        workflows: list[dict] = []
        wf_list = await self._call_tool(call_tool_fn, "workflow_list", {})
        if wf_list is not None:
            success_signals += 1
        if isinstance(wf_list, dict) and isinstance(wf_list.get("workflows"), list):
            for wf in wf_list["workflows"]:
                wf_id = wf.get("id") or wf.get("workflow_id")
                if not wf_id:
                    continue
                wf_def = await self._call_tool(call_tool_fn, "workflow_get", {"workflow_id": wf_id})
                if isinstance(wf_def, dict) and wf_def.get("nodes"):
                    workflows.append(wf_def)
            wf_path.write_text(json.dumps(workflows, indent=2), encoding="utf-8")
            files[WORKFLOWS_FILE] = wf_path

        # 4) Slot manifest
        slots_path = tmpdir / SLOTS_FILE
        slot_manifest = []
        slots_result = await self._call_tool(call_tool_fn, "list_slots", {})
        if slots_result is not None:
            success_signals += 1
        if isinstance(slots_result, dict):
            all_ids = slots_result.get("all_ids", [])
            total = slots_result.get("total", len(all_ids))
            for i in range(total):
                name = all_ids[i] if i < len(all_ids) else f"slot_{i}"
                if name == f"slot_{i}":
                    continue
                slot_info = await self._call_tool(call_tool_fn, "slot_info", {"slot": i})
                model_id = None
                if isinstance(slot_info, dict):
                    model_id = slot_info.get("model_source") or slot_info.get("model_id") or slot_info.get("model")
                slot_manifest.append({"index": i, "name": name, "model_id": model_id})

            slots_path.write_text(json.dumps(slot_manifest, indent=2), encoding="utf-8")
            files[SLOTS_FILE] = slots_path

        # If capsule is unavailable, skip creating placeholder local persistence files.
        if success_signals == 0:
            return {}

        # 5) Metadata
        meta_path = tmpdir / META_FILE
        meta = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "workflow_count": len(workflows),
            "slot_count": len(slot_manifest),
            "bag_count": bag_count,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        files[META_FILE] = meta_path

        return files

    # ------------------------------------------------------------------
    # Save / Restore
    # ------------------------------------------------------------------

    async def save_state(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        *,
        force: bool = False,
    ) -> bool:
        async with self._save_lock:
            now = time.time()
            if not force and (now - self._last_save_ts) < self.save_cooldown:
                remaining = int(self.save_cooldown - (now - self._last_save_ts))
                self._log(f"save skipped by cooldown ({remaining}s remaining)")
                return False

            tmpdir = Path(tempfile.mkdtemp(prefix="cc_self_deploy_save_"))
            try:
                self._log(f"save start force={force} tmpdir={tmpdir}")
                files = await self._collect_state_files(call_tool_fn, tmpdir)
                if not files:
                    self._log("save aborted: no state files collected")
                    return False
                self._log(f"collected files: {', '.join(sorted(files.keys()))}")

                current_bag_count = self._read_meta_bag_count(files.get(META_FILE))
                baseline = self._bag_guard_baseline_count
                if baseline is None:
                    baseline = self._read_meta_bag_count((self.data_dir / LOCAL_LAYOUT[META_FILE]))
                    self._seed_bag_guard_baseline(baseline)
                    baseline = self._bag_guard_baseline_count

                if (
                    self.bag_shrink_guard_enabled
                    and not force
                    and baseline is not None
                    and baseline >= self.bag_shrink_guard_min_baseline
                    and current_bag_count is not None
                ):
                    allowed_floor = max(0, int(baseline * self.bag_shrink_guard_ratio))
                    if current_bag_count < allowed_floor:
                        self._log(
                            "save blocked by bag shrink guard "
                            f"(current={current_bag_count}, baseline={baseline}, floor={allowed_floor})"
                        )
                        return False

                # Local save
                if self.local_enabled:
                    for filename, src in files.items():
                        rel = LOCAL_LAYOUT.get(filename, Path(filename))
                        dest = self.data_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dest)
                        self._log(f"local save: {filename} -> {dest}")

                # HF sync (optional)
                if self.hf_enabled and self._ensure_hf_repo():
                    api = self._get_hf_api()
                    repo_id = self._get_repo_id()
                    for filename, src in files.items():
                        api.upload_file(
                            path_or_fileobj=str(src),
                            path_in_repo=filename,
                            repo_id=repo_id,
                            repo_type="dataset",
                            commit_message=f"self_deploy autosave {filename} @ {datetime.now(timezone.utc).isoformat()}",
                        )
                        self._log(f"hf upload: {filename} -> {repo_id}")

                self._last_save_ts = time.time()
                if current_bag_count is not None:
                    if force:
                        self._bag_guard_baseline_count = int(current_bag_count)
                    else:
                        self._seed_bag_guard_baseline(current_bag_count)
                self._log("save complete")
                return True
            except Exception as exc:
                self._log(f"save failed: {exc}")
                return False
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    async def _restore_from_files(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        files: dict[str, Path],
    ) -> int:
        restored = 0

        # 1) Brain
        brain = files.get(BRAIN_FILE)
        if brain and brain.exists():
            result = await self._call_tool(call_tool_fn, "import_brain", {"path": str(brain)})
            if result is not None:
                restored += 1

        # 2) Bag
        bag = files.get(BAG_FILE)
        if bag and bag.exists():
            result = await self._call_tool(call_tool_fn, "load_bag", {"file_path": str(bag)})
            if result is not None:
                restored += 1

        # 3) Workflows
        workflows_file = files.get(WORKFLOWS_FILE)
        if workflows_file and workflows_file.exists():
            try:
                workflows = json.loads(workflows_file.read_text(encoding="utf-8"))
                for wf_def in workflows:
                    normalized = normalize_workflow_nodes(wf_def)
                    await self._call_tool(call_tool_fn, "workflow_create", {"definition": normalized})
                restored += 1
            except Exception:
                pass

        # 4) Slot manifest
        slot_file = files.get(SLOTS_FILE)
        if slot_file and slot_file.exists():
            try:
                manifest = json.loads(slot_file.read_text(encoding="utf-8"))
                for slot_entry in manifest:
                    model_id = slot_entry.get("model_id")
                    slot_name = slot_entry.get("name") or ""
                    if not model_id:
                        continue
                    await self._call_tool(call_tool_fn, "hub_plug", {"model_id": model_id, "slot_name": slot_name})
                restored += 1
            except Exception:
                pass

        return restored

    async def restore_state(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
    ) -> bool:
        restored = 0

        # Local restore first
        if self.local_enabled:
            local_files = {
                filename: self.data_dir / rel
                for filename, rel in LOCAL_LAYOUT.items()
            }
            local_meta_count = self._read_meta_bag_count(local_files.get(META_FILE))
            self._seed_bag_guard_baseline(local_meta_count)
            self._log(f"restore local from {self.data_dir} (bag_count={local_meta_count})")
            restored += await self._restore_from_files(call_tool_fn, local_files)
            self._log(f"restore local complete (restored={restored})")

        # HF restore (optional)
        if self.hf_enabled and self._get_repo_id():
            api = self._get_hf_api()
            repo_id = self._get_repo_id()
            tmpdir = Path(tempfile.mkdtemp(prefix="cc_self_deploy_restore_"))
            try:
                try:
                    api.repo_info(repo_id=repo_id, repo_type="dataset")
                except Exception:
                    self._log(f"restore hf skipped: repo unavailable ({repo_id})")
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
                        path = Path(downloaded)
                        if path.exists():
                            hf_files[filename] = path
                    except Exception as exc:
                        self._log(f"restore hf file skipped ({filename}): {exc}")
                        continue

                hf_meta_count = self._read_meta_bag_count(hf_files.get(META_FILE))
                self._seed_bag_guard_baseline(hf_meta_count)
                restored += await self._restore_from_files(call_tool_fn, hf_files)
                self._log(f"restore hf complete (restored={restored}, bag_count={hf_meta_count})")
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        self._log(f"restore complete restored={restored}")
        return restored > 0

    async def restore_state_revision(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        revision: str,
        *,
        promote_after_restore: bool = False,
    ) -> dict:
        rev = str(revision or "").strip()
        if not rev:
            return {"status": "error", "error": "Missing revision"}
        if not (self.hf_enabled and self._get_repo_id()):
            return {"status": "error", "error": "HF persistence unavailable"}

        api = self._get_hf_api()
        repo_id = self._get_repo_id()
        tmpdir = Path(tempfile.mkdtemp(prefix="cc_self_deploy_restore_rev_"))
        restored = 0
        downloaded_files: list[str] = []
        meta_count = None
        promote_ok: bool | None = None

        try:
            try:
                api.repo_info(repo_id=repo_id, repo_type="dataset")
            except Exception as exc:
                return {"status": "error", "error": f"repo unavailable: {exc}", "revision": rev, "repo_id": repo_id}

            hf_files: dict[str, Path] = {}
            for filename in (BRAIN_FILE, BAG_FILE, WORKFLOWS_FILE, SLOTS_FILE, META_FILE):
                try:
                    downloaded = api.hf_hub_download(
                        repo_id=repo_id,
                        repo_type="dataset",
                        filename=filename,
                        revision=rev,
                        local_dir=str(tmpdir),
                    )
                    p = Path(downloaded)
                    if p.exists():
                        hf_files[filename] = p
                        downloaded_files.append(filename)
                except Exception as exc:
                    self._log(f"restore revision file skipped ({filename} @ {rev}): {exc}")

            meta_count = self._read_meta_bag_count(hf_files.get(META_FILE))
            self._seed_bag_guard_baseline(meta_count)
            restored = await self._restore_from_files(call_tool_fn, hf_files)

            if restored > 0 and promote_after_restore:
                promote_ok = await self.save_state(call_tool_fn, force=True)

            return {
                "status": "restored" if restored > 0 else "failed",
                "revision": rev,
                "repo_id": repo_id,
                "restored": restored,
                "meta_bag_count": meta_count,
                "downloaded_files": downloaded_files,
                "promote_after_restore": bool(promote_after_restore),
                "promote_ok": promote_ok,
            }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    async def _autosave_loop(self, call_tool_fn, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                self._log("autosave tick")
                await self.save_state(call_tool_fn, force=False)
            except Exception as exc:
                self._log(f"autosave error: {exc}")

    def start_autosave(
        self,
        call_tool_fn: Callable[[str, dict], Awaitable[dict]],
        interval: int = 300,
    ) -> None:
        if self._autosave_task is not None:
            return
        self._autosave_task = asyncio.create_task(self._autosave_loop(call_tool_fn, interval))
        self._log(f"autosave started interval={interval}s")

    def stop_autosave(self) -> None:
        if self._autosave_task:
            self._autosave_task.cancel()
            self._autosave_task = None
            self._log("autosave stopped")

    def is_available(self) -> bool:
        if self.mode == "local":
            return True
        if self.mode == "hf":
            return self.hf_enabled and bool(self._get_repo_id())
        return self.local_enabled or (self.hf_enabled and bool(self._get_repo_id()))
