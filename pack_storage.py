"""
Champion Council asset pack dataset sync for Space runtimes.

Purpose:
- Keep the Space repo lean while preserving the existing `/static/assets/packs/...`
  browser/runtime contract.
- Resolve heavy pack manifests and assets from a private HF dataset repo when they
  are not present in the Space repo checkout.

Dataset layout:
- packs/index.json
- packs/<pack_id>/manifest.json
- packs/<pack_id>/<asset files...>
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path, PurePosixPath
from typing import Any


PACKS_REPO_SUFFIX = os.environ.get("PACKS_REPO_SUFFIX", "champion-council-packs").strip() or "champion-council-packs"
PACKS_DATASET_ROOT = os.environ.get("PACKS_DATASET_ROOT", "packs").strip().strip("/") or "packs"
PACKS_SYNC_ON_START = str(os.environ.get("PACKS_SYNC_ON_START", "0")).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
PACKS_SYNC_COOLDOWN = max(5, int(os.environ.get("PACKS_SYNC_COOLDOWN", "300")))

_LOCAL_PACKS_ROOT = Path("static") / "assets" / "packs"
_hf_api = None
_repo_id: str | None = None
_sync_lock = asyncio.Lock()
_last_sync_ts: float = 0.0
_last_sync_ok = False
_last_sync_error = ""


def _log(msg: str) -> None:
    print(f"[PACKS] {msg}")


def _env_token() -> str:
    return (
        os.environ.get("HF_TOKEN", "")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN", "")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN", "")
    ).strip()


def _candidate_cache_dirs() -> list[Path]:
    explicit = os.environ.get("PACKS_DATA_DIR", "").strip()
    if explicit:
        return [Path(explicit)]
    candidates: list[Path] = []
    if Path("/data").exists():
        candidates.append(Path("/data/champion-council-packs"))
    candidates.append(Path("./data/champion-council-packs"))
    return candidates


def _resolve_cache_dir() -> tuple[Path, bool]:
    for cand in _candidate_cache_dirs():
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return cand, True
        except Exception:
            continue
    return Path("./data/champion-council-packs"), False


_CACHE_DIR, _CACHE_WRITABLE = _resolve_cache_dir()
_HF_TOKEN = _env_token()
_HF_ENABLED = bool(_HF_TOKEN)


def _cache_dataset_root() -> Path:
    return _CACHE_DIR / PACKS_DATASET_ROOT


def _local_index_path() -> Path:
    return _LOCAL_PACKS_ROOT / "index.json"


def _cache_index_path() -> Path:
    return _cache_dataset_root() / "index.json"


def _count_manifests(root: Path) -> int:
    if not root.exists():
        return 0
    try:
        return sum(1 for _ in root.glob("*/manifest.json"))
    except Exception:
        return 0


def _get_api():
    global _hf_api
    if not _HF_ENABLED:
        return None
    if _hf_api is None:
        from huggingface_hub import HfApi

        _hf_api = HfApi(token=_HF_TOKEN)
    return _hf_api


def _derive_author() -> str:
    author = os.environ.get("PACKS_REPO_OWNER", "").strip()
    if author:
        return author
    author = os.environ.get("SPACE_AUTHOR_NAME", "").strip()
    if author:
        return author
    space_id = os.environ.get("SPACE_ID", "").strip()
    if "/" in space_id:
        return space_id.split("/", 1)[0].strip()
    if _HF_ENABLED:
        try:
            api = _get_api()
            info = api.whoami() if api else {}
            return str(info.get("name", "")).strip()
        except Exception:
            return ""
    return ""


def get_repo_id() -> str | None:
    global _repo_id
    configured = os.environ.get("PACKS_REPO_ID", "").strip()
    if configured:
        return configured
    if _repo_id:
        return _repo_id
    author = _derive_author()
    if not author:
        return None
    _repo_id = f"{author}/{PACKS_REPO_SUFFIX}"
    return _repo_id


def ensure_repo() -> bool:
    if not _HF_ENABLED:
        return False
    repo_id = get_repo_id()
    if not repo_id:
        return False
    api = _get_api()
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
        _log(f"hf pack repo reachable: {repo_id}")
        return True
    except Exception as info_exc:
        try:
            api.create_repo(
                repo_id=repo_id,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
            _log(f"hf pack repo ready: {repo_id}")
            return True
        except Exception as create_exc:
            _log(f"hf pack repo ensure failed ({repo_id}): info={info_exc}; create={create_exc}")
            return False


def _normalize_relative_path(value: str) -> str | None:
    text = str(value or "").replace("\\", "/").strip().lstrip("/")
    if not text:
        return None
    try:
        pure = PurePosixPath(text)
    except Exception:
        return None
    parts = [part for part in pure.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _candidate_runtime_paths(relative_path: str) -> list[Path]:
    rel = _normalize_relative_path(relative_path)
    if not rel:
        return []
    return [
        _LOCAL_PACKS_ROOT / Path(rel),
        _cache_dataset_root() / Path(rel),
    ]


async def sync_runtime_packs(force: bool = False) -> dict[str, Any]:
    global _last_sync_ts, _last_sync_ok, _last_sync_error

    async with _sync_lock:
        now = time.time()
        if not force and _last_sync_ok and (now - _last_sync_ts) < PACKS_SYNC_COOLDOWN:
            return status()
        if not (_HF_ENABLED and ensure_repo()):
            _last_sync_ok = False
            _last_sync_error = "HF dataset repo unavailable"
            return status()

        repo_id = get_repo_id()
        try:
            from huggingface_hub import snapshot_download

            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                token=_HF_TOKEN,
                local_dir=str(_CACHE_DIR),
                allow_patterns=[f"{PACKS_DATASET_ROOT}/*"],
            )
            _last_sync_ts = time.time()
            _last_sync_ok = _cache_index_path().exists()
            _last_sync_error = ""
            _log(f"pack dataset sync complete: {repo_id}")
        except Exception as exc:
            _last_sync_ts = time.time()
            _last_sync_ok = False
            _last_sync_error = str(exc)
            _log(f"pack dataset sync failed ({repo_id}): {exc}")
        return status()


async def bootstrap_runtime_packs() -> dict[str, Any]:
    if _local_index_path().exists():
        return status()
    if _cache_index_path().exists():
        return status()
    if _HF_ENABLED and get_repo_id():
        return await sync_runtime_packs(force=False)
    if PACKS_SYNC_ON_START:
        return await sync_runtime_packs(force=False)
    return status()


async def resolve_runtime_pack_file(relative_path: str) -> Path | None:
    candidates = _candidate_runtime_paths(relative_path)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    if _HF_ENABLED:
        rel = _normalize_relative_path(relative_path)
        repo_id = get_repo_id()
        if rel and repo_id:
            try:
                from huggingface_hub import hf_hub_download

                _CACHE_DIR.mkdir(parents=True, exist_ok=True)
                hf_hub_download(
                    repo_id=repo_id,
                    repo_type="dataset",
                    filename=f"{PACKS_DATASET_ROOT}/{rel}",
                    token=_HF_TOKEN,
                    local_dir=str(_CACHE_DIR),
                )
            except Exception as exc:
                _log(f"pack file resolve failed ({repo_id}:{rel}): {exc}")
        for candidate in _candidate_runtime_paths(relative_path):
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def status() -> dict[str, Any]:
    repo_id = get_repo_id()
    local_root = _LOCAL_PACKS_ROOT.resolve()
    cache_root = _cache_dataset_root().resolve()
    return {
        "available": bool(_CACHE_WRITABLE or _local_index_path().exists() or _cache_index_path().exists()),
        "hf_enabled": _HF_ENABLED,
        "has_hf_token": bool(_HF_TOKEN),
        "repo_id": repo_id,
        "dataset_root": PACKS_DATASET_ROOT,
        "sync_on_start": PACKS_SYNC_ON_START,
        "local_static_root": str(local_root),
        "local_index_exists": _local_index_path().exists(),
        "local_manifest_count": _count_manifests(_LOCAL_PACKS_ROOT),
        "cache_root": str(cache_root),
        "cache_writable": _CACHE_WRITABLE,
        "cache_index_exists": _cache_index_path().exists(),
        "cache_manifest_count": _count_manifests(_cache_dataset_root()),
        "last_sync_ts": _last_sync_ts,
        "last_sync_ok": _last_sync_ok,
        "last_sync_error": _last_sync_error,
    }
