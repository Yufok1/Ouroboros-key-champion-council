from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx


DEFAULT_COCOON_ZIP_ENV = os.environ.get("COCOON_DEFAULT_ZIP", "").strip()
DEFAULT_COCOON_SEARCH_DIR = Path(
    os.environ.get("COCOON_DEFAULT_DIR", r"D:\End-Game\Convergence_Engine\Children")
)
DEFAULT_COCOON_ZIP = Path(
    DEFAULT_COCOON_ZIP_ENV or str(DEFAULT_COCOON_SEARCH_DIR / "cocoon_ensemble_20260428083531.zip")
)


def _latest_default_cocoon_zip() -> Path:
    if DEFAULT_COCOON_ZIP_ENV:
        return Path(DEFAULT_COCOON_ZIP_ENV).expanduser()
    try:
        candidates = [
            path
            for path in DEFAULT_COCOON_SEARCH_DIR.expanduser().glob("cocoon_ensemble_*.zip")
            if path.is_file()
        ]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    except Exception:
        pass
    return DEFAULT_COCOON_ZIP


COCOON_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "cocoon_import": {
        "description": "Import a Convergence Engine Cocoon ZIP into the managed Champion Council cocoon registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to a Cocoon ZIP or extracted Cocoon directory"},
                "cocoon_id": {"type": "string", "description": "Optional registry id; defaults to the archive stem"},
                "overwrite": {"type": "boolean", "description": "Replace an existing managed extraction with the same id"},
                "run_info": {"type": "boolean", "description": "Run cocoon.py --mode info after import"},
            },
        },
    },
    "cocoon_list": {
        "description": "List managed Cocoon imports and runtime status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "cocoon_info": {
        "description": "Inspect a managed Cocoon, Cocoon ZIP, or extracted Cocoon directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "path": {"type": "string", "description": "Optional ZIP or directory path to inspect without importing"},
                "run_info": {"type": "boolean", "description": "Run cocoon.py --mode info when a directory is available"},
            },
        },
    },
    "cocoon_start": {
        "description": "Start a managed Cocoon's native HTTP server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "path": {"type": "string", "description": "Optional ZIP path to auto-import first"},
                "port": {"type": "integer", "description": "Optional local Cocoon HTTP port"},
                "max_organisms": {"type": "integer", "description": "Optional organism load cap"},
                "voting": {"type": "string", "description": "Cocoon voting mode: majority|weighted|confidence"},
                "startup_timeout": {"type": "integer", "description": "Seconds to wait for /health"},
            },
        },
    },
    "cocoon_stop": {
        "description": "Stop a managed Cocoon process started by Champion Council.",
        "inputSchema": {
            "type": "object",
            "properties": {"cocoon_id": {"type": "string", "description": "Managed Cocoon id"}},
        },
    },
    "cocoon_chat": {
        "description": "Send a prompt to a managed Cocoon through its native /chat endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "prompt": {"type": "string", "description": "Prompt text"},
                "learn": {"type": "boolean", "description": "Allow Cocoon post-snapshot learning from the prompt; defaults false"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
            "required": ["prompt"],
        },
    },
    "cocoon_teach": {
        "description": "Teach a managed Cocoon new text through its native /teach endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "text": {"type": "string", "description": "Training text"},
                "reward": {"type": "number", "description": "Optional learning reward"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
            "required": ["text"],
        },
    },
    "cocoon_act": {
        "description": "Run Cocoon action inference through its native /act endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "state": {"type": "array", "items": {"type": "number"}},
                "explore": {"type": "boolean"},
                "auto_start": {"type": "boolean"},
            },
        },
    },
    "cocoon_learn": {
        "description": "Feed one RL transition to a managed Cocoon through its native /learn endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "state": {"type": "array", "items": {"type": "number"}},
                "action": {"type": "integer"},
                "reward": {"type": "number"},
                "next_state": {"type": "array", "items": {"type": "number"}},
                "done": {"type": "boolean"},
                "auto_start": {"type": "boolean"},
            },
            "required": ["state", "action", "reward", "next_state", "done"],
        },
    },
    "cocoon_run_game": {
        "description": "Run a Cocoon game lane synchronously and return captured output. Supports sphere and gym.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "game": {"type": "string", "description": "Game lane: sphere or gym"},
                "env": {"type": "string", "description": "Gym environment, e.g. CartPole-v1"},
                "episodes": {"type": "integer", "description": "Gym episode count"},
                "balls": {"type": "integer", "description": "Sphere arena ball count"},
                "misses": {"type": "integer", "description": "Sphere arena max misses before exit"},
                "train": {"type": "boolean", "description": "Enable game training where supported"},
                "headless": {"type": "boolean", "description": "Run without a display where supported"},
                "render": {"type": "boolean", "description": "Render Gym visually"},
                "max_organisms": {"type": "integer"},
                "voting": {"type": "string"},
                "timeout": {"type": "integer", "description": "Seconds before the run is killed"},
            },
        },
    },
    "cocoon_spawn_game": {
        "description": "Spawn a Cocoon game lane as a managed background process. Supports sphere and gym.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "game": {"type": "string", "description": "Game lane: sphere or gym"},
                "env": {"type": "string"},
                "episodes": {"type": "integer"},
                "balls": {"type": "integer"},
                "misses": {"type": "integer"},
                "train": {"type": "boolean"},
                "headless": {"type": "boolean"},
                "render": {"type": "boolean"},
                "max_organisms": {"type": "integer"},
                "voting": {"type": "string"},
            },
        },
    },
    "cocoon_game_status": {
        "description": "Read status and log tail for managed Cocoon game processes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Specific game run id; omit to list all"},
                "tail": {"type": "integer", "description": "Log tail byte limit"},
            },
        },
    },
    "cocoon_stop_game": {
        "description": "Stop a managed Cocoon game process.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "Game run id"}},
            "required": ["run_id"],
        },
    },
    "cocoon_vocab_check": {
        "description": "Check whether words exist in the Cocoon file vocabulary and live runtime vocabulary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "words": {"type": "array", "items": {"type": "string"}},
                "auto_start": {"type": "boolean"},
            },
        },
    },
    "cocoon_capabilities": {
        "description": "Report the Cocoon integration capability matrix and remaining connector seams.",
        "inputSchema": {
            "type": "object",
            "properties": {"cocoon_id": {"type": "string", "description": "Managed Cocoon id"}},
        },
    },
    "cocoon_curriculum": {
        "description": "Read a managed Cocoon's staged language/RL curriculum from its native /curriculum endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_training_logs": {
        "description": "Read recent post-export Cocoon learning trace entries from /training/logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "limit": {"type": "integer", "description": "Maximum log entries to return"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_score": {
        "description": "Submit an outside coach reward score to /curriculum/score without injecting prompt text as speaker dialogue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "event_type": {"type": "string"},
                "stage": {"type": "string"},
                "input": {"type": "string"},
                "target": {"type": "string"},
                "output": {"type": "string"},
                "reward": {"type": "number"},
                "score": {"type": "object"},
                "coach": {"type": "string"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_snapshot": {
        "description": "Read live symbolic/training state from a managed Cocoon's native /snapshot endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_save": {
        "description": "Persist live symbolic Cocoon state through its native /save endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "output_dir": {"type": "string", "description": "Output directory under the managed Cocoon directory"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_export": {
        "description": "Export learned live Cocoon state into an updated cocoon.py through the native /export endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "path": {"type": "string", "description": "Output path under the managed Cocoon directory"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_clone_from_live": {
        "description": "Fork a managed Cocoon directory and replace cocoon.py with a live-state export.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id to clone"},
                "new_cocoon_id": {"type": "string", "description": "New managed Cocoon id"},
                "overwrite": {"type": "boolean", "description": "Replace an existing clone with the same id"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_dreamer_observe": {
        "description": "Record a game/runtime observation through a Cocoon's native /dreamer/observe endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "game": {"type": "string"},
                "observation": {"type": "object"},
                "reward": {"type": "number"},
                "done": {"type": "boolean"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_dreamer_propose": {
        "description": "Ask a Cocoon for observation-driven game/training proposals through /dreamer/propose.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "env": {"type": "string", "description": "Optional Gym environment hint"},
                "auto_start": {"type": "boolean", "description": "Start the Cocoon server if needed"},
            },
        },
    },
    "cocoon_plug_slot": {
        "description": "Start a Cocoon and plug its OpenAI-compatible shim into the next council slot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cocoon_id": {"type": "string", "description": "Managed Cocoon id"},
                "path": {"type": "string", "description": "Optional ZIP path to auto-import first"},
                "slot_name": {"type": "string", "description": "Optional display name for the plugged slot"},
                "port": {"type": "integer", "description": "Optional native Cocoon HTTP port"},
                "max_organisms": {"type": "integer", "description": "Optional organism load cap"},
                "voting": {"type": "string", "description": "Cocoon voting mode: majority|weighted|confidence"},
            },
        },
    },
}


def _safe_slug(value: str, fallback: str = "cocoon") -> str:
    raw = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-_")
    return (slug or fallback)[:96]


def _json_loads_maybe(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in ("text", "input_text"):
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _bool_arg(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


def _int_arg(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except Exception:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


class CocoonManager:
    def __init__(
        self,
        root: Path,
        *,
        python_executable: str | None = None,
        web_port: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.registry_path = self.root / "registry.json"
        self.python_executable = python_executable or sys.executable
        self.web_port = web_port
        self._lock = asyncio.Lock()
        self._processes: dict[str, dict[str, Any]] = {}
        self._game_processes: dict[str, dict[str, Any]] = {}

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> dict[str, Any]:
        self._ensure_root()
        if not self.registry_path.exists():
            return {"version": 1, "default_id": "", "cocoons": {}}
        data = _read_json_file(self.registry_path)
        if not isinstance(data, dict):
            return {"version": 1, "default_id": "", "cocoons": {}}
        data.setdefault("version", 1)
        data.setdefault("default_id", "")
        data.setdefault("cocoons", {})
        if not isinstance(data["cocoons"], dict):
            data["cocoons"] = {}
        return data

    def _save_registry(self, data: dict[str, Any]) -> None:
        self._ensure_root()
        tmp = self.registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.registry_path)

    def _managed_dir(self, cocoon_id: str) -> Path:
        return self.root / _safe_slug(cocoon_id)

    def _default_path(self) -> Path:
        return _latest_default_cocoon_zip()

    def _managed_output_path(self, record: dict[str, Any], value: Any, default_name: str) -> tuple[Path | None, str | None]:
        base = Path(str(record.get("path") or "")).resolve()
        raw = str(value or "").strip()
        output = Path(raw).expanduser() if raw else Path(default_name)
        if not output.is_absolute():
            output = base / output
        try:
            resolved = output.resolve()
            if not _inside(resolved, base):
                return None, f"Refusing to write outside active managed Cocoon directory: {resolved}"
            resolved.parent.mkdir(parents=True, exist_ok=True)
            return resolved, None
        except Exception as exc:
            return None, str(exc)

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        return env

    def _normalize_zip_member(self, raw_name: str) -> Path:
        raw = str(raw_name or "").replace("\\", "/")
        if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
            raise ValueError(f"Unsafe ZIP member path: {raw_name}")
        pure = PurePosixPath(raw)
        parts = [p for p in pure.parts if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise ValueError(f"Unsafe ZIP member path: {raw_name}")
        return Path(*parts)

    def _extract_zip(self, zip_path: Path, dest: Path) -> dict[str, Any]:
        root = dest.resolve()
        root.mkdir(parents=True, exist_ok=True)
        seen: dict[str, int] = {}
        duplicates: dict[str, int] = {}
        files: list[str] = []
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = self._normalize_zip_member(info.filename)
                rel_key = rel.as_posix()
                seen[rel_key] = seen.get(rel_key, 0) + 1
                if seen[rel_key] > 1:
                    duplicates[rel_key] = seen[rel_key]
                target = (root / rel).resolve()
                if not _inside(target, root):
                    raise ValueError(f"Unsafe ZIP extraction target: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                files.append(rel_key)
        return {"file_count": len(files), "duplicates": duplicates, "files": files[:200]}

    def _inspect_zip(self, zip_path: Path) -> dict[str, Any]:
        names: list[str] = []
        duplicates: dict[str, int] = {}
        seen: dict[str, int] = {}
        metadata: Any = None
        vocab_count = 0
        knowledge_concepts = 0
        knowledge_relations = 0
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = self._normalize_zip_member(info.filename).as_posix()
                names.append(rel)
                seen[rel] = seen.get(rel, 0) + 1
                if seen[rel] > 1:
                    duplicates[rel] = seen[rel]
                if rel == "metadata.json":
                    metadata = _json_loads_maybe(zf.read(info).decode("utf-8", errors="replace"))
                elif rel == "vocabulary.json":
                    vocab = _json_loads_maybe(zf.read(info).decode("utf-8", errors="replace"))
                    if isinstance(vocab, dict):
                        word_to_id = vocab.get("word_to_id")
                        vocab_count = len(word_to_id) if isinstance(word_to_id, dict) else len(vocab)
                elif rel == "knowledge_web.json":
                    knowledge = _json_loads_maybe(zf.read(info).decode("utf-8", errors="replace"))
                    if isinstance(knowledge, dict):
                        concepts = knowledge.get("concepts")
                        relations = knowledge.get("relations")
                        knowledge_concepts = len(concepts) if isinstance(concepts, (dict, list)) else 0
                        knowledge_relations = len(relations) if isinstance(relations, (dict, list)) else 0
        return {
            "path": str(zip_path),
            "kind": "zip",
            "exists": zip_path.exists(),
            "size_bytes": zip_path.stat().st_size if zip_path.exists() else 0,
            "sha256": _sha256_file(zip_path) if zip_path.exists() else "",
            "files": names[:200],
            "file_count": len(names),
            "duplicates": duplicates,
            "required_files": {
                "cocoon.py": "cocoon.py" in names,
                "brain_ensemble.pt": "brain_ensemble.pt" in names,
                "vocabulary.json": "vocabulary.json" in names,
                "metadata.json": "metadata.json" in names,
            },
            "metadata": metadata if isinstance(metadata, dict) else {},
            "vocabulary_count": vocab_count,
            "knowledge_concepts": knowledge_concepts,
            "knowledge_relations": knowledge_relations,
        }

    def _run_info(self, cocoon_dir: Path, timeout: int = 60) -> dict[str, Any]:
        cocoon_py = cocoon_dir / "cocoon.py"
        if not cocoon_py.exists():
            return {"ok": False, "error": "cocoon.py not found"}
        try:
            proc = subprocess.run(
                [self.python_executable, str(cocoon_py), "--mode", "info", "--max-organisms", "1"],
                cwd=str(cocoon_dir),
                env=self._env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(5, timeout),
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-6000:],
                "stderr": proc.stderr[-3000:],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _inspect_dir(self, cocoon_dir: Path, *, run_info: bool = False) -> dict[str, Any]:
        files = [p.name for p in cocoon_dir.iterdir()] if cocoon_dir.exists() else []
        vocab = _read_json_file(cocoon_dir / "vocabulary.json")
        knowledge = _read_json_file(cocoon_dir / "knowledge_web.json")
        metadata = _read_json_file(cocoon_dir / "metadata.json")
        vocab_count = 0
        if isinstance(vocab, dict):
            word_to_id = vocab.get("word_to_id")
            vocab_count = len(word_to_id) if isinstance(word_to_id, dict) else len(vocab)
        knowledge_concepts = 0
        knowledge_relations = 0
        if isinstance(knowledge, dict):
            concepts = knowledge.get("concepts")
            relations = knowledge.get("relations")
            knowledge_concepts = len(concepts) if isinstance(concepts, (dict, list)) else 0
            knowledge_relations = len(relations) if isinstance(relations, (dict, list)) else 0
        info: dict[str, Any] = {
            "path": str(cocoon_dir),
            "kind": "directory",
            "exists": cocoon_dir.exists(),
            "files": files,
            "required_files": {
                "cocoon.py": (cocoon_dir / "cocoon.py").exists(),
                "brain_ensemble.pt": (cocoon_dir / "brain_ensemble.pt").exists(),
                "vocabulary.json": (cocoon_dir / "vocabulary.json").exists(),
                "metadata.json": (cocoon_dir / "metadata.json").exists(),
            },
            "metadata": metadata if isinstance(metadata, dict) else {},
            "vocabulary_count": vocab_count,
            "knowledge_concepts": knowledge_concepts,
            "knowledge_relations": knowledge_relations,
            "cocoon_py_size": (cocoon_dir / "cocoon.py").stat().st_size if (cocoon_dir / "cocoon.py").exists() else 0,
            "brain_size": (cocoon_dir / "brain_ensemble.pt").stat().st_size if (cocoon_dir / "brain_ensemble.pt").exists() else 0,
        }
        if run_info:
            info["runtime_info"] = self._run_info(cocoon_dir)
        return info

    def _log_tail(self, log_path: Path, limit: int = 5000) -> str:
        try:
            data = log_path.read_bytes()
            return data[-limit:].decode("utf-8", errors="replace")
        except Exception:
            return ""

    async def import_cocoon(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        source_path = Path(str(args.get("path") or "")).expanduser() if args.get("path") else self._default_path()
        if not source_path.exists():
            return {"error": f"Cocoon source not found: {source_path}", "default_path": str(self._default_path())}
        cocoon_id = _safe_slug(str(args.get("cocoon_id") or source_path.stem))
        dest = self._managed_dir(cocoon_id)
        overwrite = bool(args.get("overwrite", False))
        run_info = bool(args.get("run_info", True))
        async with self._lock:
            registry = self._load_registry()
            if dest.exists() and not overwrite:
                inspect = await asyncio.to_thread(self._inspect_dir, dest, run_info=run_info)
                record = dict(registry["cocoons"].get(cocoon_id) or {})
                record.update({
                    "id": cocoon_id,
                    "source_path": str(source_path),
                    "path": str(dest),
                    "updated_at": time.time(),
                    "inspect": inspect,
                })
                registry["cocoons"][cocoon_id] = record
                registry["default_id"] = registry.get("default_id") or cocoon_id
                self._save_registry(registry)
                return {"status": "ok", "reused": True, "cocoon_id": cocoon_id, "record": record}
            if dest.exists():
                if not _inside(dest, self.root):
                    return {"error": f"Refusing to overwrite outside manager root: {dest}"}
                await asyncio.to_thread(shutil.rmtree, dest)
            dest.mkdir(parents=True, exist_ok=True)
            if source_path.is_dir():
                for item in source_path.iterdir():
                    target = dest / item.name
                    if item.is_dir():
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
                extract = {"source": "directory", "file_count": len(list(dest.iterdir())), "duplicates": {}}
                source_hash = ""
            else:
                extract = await asyncio.to_thread(self._extract_zip, source_path, dest)
                source_hash = await asyncio.to_thread(_sha256_file, source_path)
            inspect = await asyncio.to_thread(self._inspect_dir, dest, run_info=run_info)
            record = {
                "id": cocoon_id,
                "source_path": str(source_path),
                "source_sha256": source_hash,
                "path": str(dest),
                "imported_at": time.time(),
                "updated_at": time.time(),
                "extract": extract,
                "inspect": inspect,
            }
            registry["cocoons"][cocoon_id] = record
            registry["default_id"] = cocoon_id
            self._save_registry(registry)
        return {"status": "ok", "reused": False, "cocoon_id": cocoon_id, "record": record}

    async def list_cocoons(self) -> dict[str, Any]:
        registry = self._load_registry()
        rows: list[dict[str, Any]] = []
        for cocoon_id, record in sorted(registry.get("cocoons", {}).items()):
            proc_info = self._processes.get(cocoon_id) or {}
            proc = proc_info.get("process")
            running = bool(proc and proc.poll() is None)
            row = {
                "id": cocoon_id,
                "path": record.get("path", ""),
                "source_path": record.get("source_path", ""),
                "vocabulary_count": ((record.get("inspect") or {}).get("vocabulary_count") or 0),
                "running": running,
                "port": proc_info.get("port") or record.get("port"),
                "pid": proc.pid if running else None,
            }
            rows.append(row)
        return {"status": "ok", "default_id": registry.get("default_id", ""), "cocoons": rows, "count": len(rows)}

    async def info(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        run_info = bool(args.get("run_info", False))
        if args.get("path"):
            path = Path(str(args.get("path"))).expanduser()
            if not path.exists():
                return {"error": f"Path not found: {path}"}
            if path.is_dir():
                inspect = await asyncio.to_thread(self._inspect_dir, path, run_info=run_info)
            else:
                inspect = await asyncio.to_thread(self._inspect_zip, path)
            return {"status": "ok", "inspect": inspect}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=False)
        if err:
            return {"error": err}
        inspect = await asyncio.to_thread(self._inspect_dir, Path(record["path"]), run_info=run_info)
        return {"status": "ok", "cocoon_id": record["id"], "inspect": inspect, "record": record}

    async def _get_record(self, cocoon_id: str = "") -> dict[str, Any] | None:
        registry = self._load_registry()
        records = registry.get("cocoons", {})
        wanted = _safe_slug(cocoon_id, "") if cocoon_id else str(registry.get("default_id") or "")
        if not wanted and len(records) == 1:
            wanted = next(iter(records.keys()))
        record = records.get(wanted) if wanted else None
        if isinstance(record, dict):
            record = dict(record)
            record["id"] = wanted
            return record
        return None

    async def _ensure_record(
        self,
        cocoon_id: str,
        args: dict[str, Any] | None = None,
        *,
        auto_import: bool = True,
    ) -> tuple[dict[str, Any] | None, str | None]:
        record = await self._get_record(cocoon_id)
        if record:
            return record, None
        args = args or {}
        if not auto_import and not args.get("path"):
            return None, "No managed Cocoon found. Run cocoon_import first."
        if auto_import or args.get("path"):
            import_args = {
                "path": args.get("path") or str(self._default_path()),
                "cocoon_id": cocoon_id or args.get("cocoon_id") or "",
                "run_info": False,
            }
            imported = await self.import_cocoon(import_args)
            if imported.get("error"):
                return None, str(imported.get("error"))
            record = await self._get_record(str(imported.get("cocoon_id") or cocoon_id or ""))
            if record:
                return record, None
        return None, "Unable to resolve Cocoon record."

    async def _health(self, port: int) -> dict[str, Any]:
        url = f"http://127.0.0.1:{port}/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
            data = resp.json() if resp.content else {}
            return {"ok": 200 <= resp.status_code < 300, "status_code": resp.status_code, "url": url, "data": data}
        except Exception as exc:
            return {"ok": False, "url": url, "error": str(exc)}

    async def start(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=True)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        cocoon_id = str(record["id"])
        proc_info = self._processes.get(cocoon_id) or {}
        proc = proc_info.get("process")
        if proc and proc.poll() is None:
            port = int(proc_info.get("port") or record.get("port") or 0)
            health = await self._health(port) if port else {"ok": False, "error": "missing port"}
            return {"status": "ok", "already_running": True, "cocoon_id": cocoon_id, "port": port, "pid": proc.pid, "health": health}
        old_port = int(record.get("port") or 0)
        if old_port:
            old_health = await self._health(old_port)
            if old_health.get("ok"):
                return {"status": "ok", "already_running": True, "cocoon_id": cocoon_id, "port": old_port, "pid": None, "health": old_health}
        port = int(args.get("port") or 0) or self._find_free_port()
        cocoon_dir = Path(str(record.get("path") or ""))
        if not (cocoon_dir / "cocoon.py").exists():
            return {"error": f"cocoon.py not found for {cocoon_id}", "path": str(cocoon_dir)}
        cmd = [self.python_executable, "-u", "cocoon.py", "--mode", "serve", "--port", str(port)]
        if args.get("max_organisms") not in (None, ""):
            cmd.extend(["--max-organisms", str(int(args.get("max_organisms")))])
        voting = str(args.get("voting") or "").strip()
        if voting:
            cmd.extend(["--voting", voting])
        log_path = cocoon_dir / "cocoon_server.log"
        log_file = log_path.open("ab")
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cocoon_dir),
                env=self._env(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception as exc:
            log_file.close()
            return {"error": f"Failed to start Cocoon: {exc}", "cmd": cmd}
        self._processes[cocoon_id] = {"process": proc, "port": port, "log_path": str(log_path)}
        registry = self._load_registry()
        if cocoon_id in registry.get("cocoons", {}):
            registry["cocoons"][cocoon_id]["port"] = port
            registry["cocoons"][cocoon_id]["last_started_at"] = time.time()
            self._save_registry(registry)
        timeout = max(1, int(args.get("startup_timeout") or 25))
        deadline = time.time() + timeout
        health: dict[str, Any] = {"ok": False, "error": "startup timeout"}
        while time.time() < deadline:
            if proc.poll() is not None:
                health = {"ok": False, "error": f"process exited with code {proc.returncode}"}
                break
            health = await self._health(port)
            if health.get("ok"):
                break
            await asyncio.sleep(0.4)
        return {
            "status": "ok" if health.get("ok") else "error",
            "cocoon_id": cocoon_id,
            "port": port,
            "pid": proc.pid,
            "health": health,
            "base_url": f"http://127.0.0.1:{port}",
            "log_path": str(log_path),
            "log_tail": "" if health.get("ok") else self._log_tail(log_path),
        }

    async def stop(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=False)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        cocoon_id = str(record["id"])
        proc_info = self._processes.get(cocoon_id) or {}
        proc = proc_info.get("process")
        if not proc or proc.poll() is not None:
            return {"status": "ok", "cocoon_id": cocoon_id, "stopped": False, "message": "No managed process is running"}
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, 5)
        except Exception:
            proc.kill()
            await asyncio.to_thread(proc.wait)
        return {"status": "ok", "cocoon_id": cocoon_id, "stopped": True, "returncode": proc.returncode}

    async def _ensure_started(self, args: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=True)
        if err or not record:
            return None, {"error": err or "Cocoon record unavailable"}
        port = int(record.get("port") or 0)
        if port:
            health = await self._health(port)
            if health.get("ok"):
                return {"record": record, "port": port, "base_url": f"http://127.0.0.1:{port}", "health": health}, None
        if args.get("auto_start", True) is False:
            return None, {"error": "Cocoon is not running and auto_start is false", "cocoon_id": record["id"]}
        started = await self.start(args)
        if started.get("error") or started.get("status") == "error":
            return None, started
        return {"record": record, "port": int(started["port"]), "base_url": str(started["base_url"]), "health": started.get("health")}, None

    def _decode_native_response(self, resp: httpx.Response) -> tuple[Any, dict[str, Any]]:
        if not resp.content:
            return {}, {}
        try:
            return resp.json(), {}
        except Exception as exc:
            return {}, {"text_preview": resp.text[:1000], "json_error": str(exc)}

    async def _post_native(self, port: int, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"http://127.0.0.1:{port}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
            data, decode_meta = self._decode_native_response(resp)
            result = {"status_code": resp.status_code, "url": url, "data": data, **decode_meta}
            if 200 <= resp.status_code < 300:
                return {"status": "ok", **result}
            return {"error": f"HTTP {resp.status_code}", **result}
        except Exception as exc:
            return {"error": str(exc), "url": url}

    def _unsupported_native_contract(self, payload: dict[str, Any], endpoint: str) -> dict[str, Any]:
        if payload.get("status_code") == 404:
            payload = dict(payload)
            payload["unsupported"] = True
            payload["message"] = (
                f"{endpoint} is not available on this Cocoon build. "
                "Re-export from the newer Convergence compiler to enable the curriculum/runtime contract."
            )
        return payload

    async def _get_native(self, port: int, endpoint: str) -> dict[str, Any]:
        url = f"http://127.0.0.1:{port}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
            data, decode_meta = self._decode_native_response(resp)
            result = {"status_code": resp.status_code, "url": url, "data": data, **decode_meta}
            if 200 <= resp.status_code < 300:
                return {"status": "ok", **result}
            return {"error": f"HTTP {resp.status_code}", **result}
        except Exception as exc:
            return {"error": str(exc), "url": url}

    async def chat(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        prompt = str(args.get("prompt") or "")
        if not prompt:
            return {"error": "Missing prompt"}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        reply = await self._post_native(
            int(runtime["port"]),
            "/chat",
            {"prompt": prompt, "learn": _bool_arg(args.get("learn"), False)},
        )
        reply["cocoon_id"] = runtime["record"]["id"]
        return reply

    async def teach(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        text = str(args.get("text") or "")
        if not text:
            return {"error": "Missing text"}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        return await self._post_native(
            int(runtime["port"]),
            "/teach",
            {"text": text, "reward": float(args.get("reward", 0.5) or 0.5)},
        )

    async def act(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        return await self._post_native(
            int(runtime["port"]),
            "/act",
            {"state": args.get("state") or [], "explore": bool(args.get("explore", False))},
        )

    async def learn(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        payload = {
            "state": args.get("state") or [],
            "action": _int_arg(args.get("action"), 0),
            "reward": float(args.get("reward", 0.0) or 0.0),
            "next_state": args.get("next_state") or [],
            "done": _bool_arg(args.get("done"), False),
        }
        return await self._post_native(int(runtime["port"]), "/learn", payload)

    def _build_game_command(self, record: dict[str, Any], args: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        game = str(args.get("game") or args.get("mode") or "sphere").strip().lower()
        cmd = [self.python_executable, "-u", "cocoon.py"]
        meta: dict[str, Any] = {
            "cocoon_id": record.get("id"),
            "game": game,
            "warnings": [],
        }
        if game in ("sphere", "arena", "swarm", "swarm_defense"):
            balls = _int_arg(args.get("balls"), 1, minimum=1, maximum=5)
            misses = _int_arg(args.get("misses"), 3, minimum=1)
            headless = _bool_arg(args.get("headless"), True)
            train = _bool_arg(args.get("train"), False)
            cmd.extend(["--mode", "sphere", "--balls", str(balls), "--misses", str(misses)])
            if headless:
                cmd.append("--headless")
            if train:
                cmd.append("--train")
                meta["warnings"].append("Native sphere training is live, but persistence still depends on native save/export behavior.")
            meta.update({"game": "sphere", "balls": balls, "misses": misses, "headless": headless, "train": train})
        elif game in ("gym", "cartpole", "gymnasium"):
            env_name = str(args.get("env") or ("CartPole-v1" if game != "cartpole" else "CartPole-v1"))
            episodes = _int_arg(args.get("episodes"), 1, minimum=1)
            render = _bool_arg(args.get("render"), False)
            train = _bool_arg(args.get("train"), False)
            cmd.extend(["--mode", "gym", "--env", env_name, "--episodes", str(episodes)])
            if render:
                cmd.append("--render")
            if not train:
                cmd.append("--no-learn")
            else:
                meta["warnings"].append("Native gym training may prompt to save; connector runs non-interactively and does not guarantee persistence yet.")
            meta.update({"game": "gym", "env": env_name, "episodes": episodes, "render": render, "train": train})
        else:
            raise ValueError(f"Unsupported Cocoon game lane: {game}. Supported: sphere, gym")
        if args.get("max_organisms") not in (None, ""):
            cmd.extend(["--max-organisms", str(_int_arg(args.get("max_organisms"), 1, minimum=1))])
        voting = str(args.get("voting") or "").strip()
        if voting:
            cmd.extend(["--voting", voting])
        return cmd, meta

    async def run_game(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=True)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        cocoon_dir = Path(str(record.get("path") or ""))
        if not (cocoon_dir / "cocoon.py").exists():
            return {"error": f"cocoon.py not found for {record.get('id')}", "path": str(cocoon_dir)}
        try:
            cmd, meta = self._build_game_command(record, args)
        except Exception as exc:
            return {"error": str(exc)}
        timeout = _int_arg(args.get("timeout"), 120, minimum=5)
        started = time.time()
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(cocoon_dir),
                env=self._env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "returncode": proc.returncode,
                "duration_ms": int((time.time() - started) * 1000),
                "cmd": cmd,
                **meta,
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-4000:],
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "timeout",
                "error": f"Cocoon game exceeded {timeout}s timeout",
                "cmd": cmd,
                **meta,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "cmd": cmd, **meta}

    async def spawn_game(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=True)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        cocoon_dir = Path(str(record.get("path") or ""))
        if not (cocoon_dir / "cocoon.py").exists():
            return {"error": f"cocoon.py not found for {record.get('id')}", "path": str(cocoon_dir)}
        try:
            cmd, meta = self._build_game_command(record, args)
        except Exception as exc:
            return {"error": str(exc)}
        run_id = _safe_slug(f"{record.get('id')}-{meta.get('game')}-{int(time.time() * 1000)}", "cocoon-game")
        log_path = cocoon_dir / f"{run_id}.log"
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            if meta.get("headless", False) or not meta.get("render", False):
                creationflags = subprocess.CREATE_NO_WINDOW
        try:
            with log_path.open("ab") as log_file:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cocoon_dir),
                    env=self._env(),
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
        except Exception as exc:
            return {"status": "error", "error": str(exc), "cmd": cmd, **meta}
        self._game_processes[run_id] = {
            "process": proc,
            "cmd": cmd,
            "log_path": str(log_path),
            "started_at": time.time(),
            **meta,
        }
        return {
            "status": "ok",
            "run_id": run_id,
            "pid": proc.pid,
            "cmd": cmd,
            "log_path": str(log_path),
            **meta,
        }

    async def game_status(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        tail = _int_arg(args.get("tail"), 5000, minimum=0, maximum=50000)
        wanted = str(args.get("run_id") or "").strip()
        rows: list[dict[str, Any]] = []
        for run_id, info in sorted(self._game_processes.items()):
            if wanted and run_id != wanted:
                continue
            proc = info.get("process")
            returncode = proc.poll() if proc else None
            running = bool(proc and returncode is None)
            log_path = Path(str(info.get("log_path") or ""))
            rows.append({
                "run_id": run_id,
                "running": running,
                "returncode": returncode,
                "pid": proc.pid if proc and running else None,
                "cocoon_id": info.get("cocoon_id"),
                "game": info.get("game"),
                "cmd": info.get("cmd"),
                "started_at": info.get("started_at"),
                "log_path": str(log_path),
                "log_tail": self._log_tail(log_path, tail) if tail else "",
            })
        if wanted and not rows:
            return {"status": "missing", "run_id": wanted, "games": []}
        return {"status": "ok", "count": len(rows), "games": rows}

    async def stop_game(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        run_id = str(args.get("run_id") or "").strip()
        if not run_id:
            return {"error": "Missing run_id"}
        info = self._game_processes.get(run_id)
        if not info:
            return {"status": "missing", "run_id": run_id}
        proc = info.get("process")
        if not proc or proc.poll() is not None:
            return {"status": "ok", "run_id": run_id, "stopped": False, "returncode": proc.returncode if proc else None}
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, 5)
        except Exception:
            proc.kill()
            await asyncio.to_thread(proc.wait)
        return {"status": "ok", "run_id": run_id, "stopped": True, "returncode": proc.returncode}

    async def vocab_check(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=False)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        words = args.get("words")
        if not isinstance(words, list) or not words:
            words = ["a", "an", "the", "and", "to", "of", "in", "it", "is", "but", "then", "not", "can", "tool", "cocoon", "council"]
        normalized = [str(w).strip().lower() for w in words if str(w).strip()]
        cocoon_dir = Path(str(record.get("path") or ""))
        vocab = _read_json_file(cocoon_dir / "vocabulary.json")
        file_word_to_id = vocab.get("word_to_id", {}) if isinstance(vocab, dict) and isinstance(vocab.get("word_to_id"), dict) else {}
        runtime_words: set[str] | None = None
        runtime_vocab_size: int | None = None
        runtime_error = None
        if _bool_arg(args.get("auto_start"), True):
            runtime, runtime_err = await self._ensure_started({"cocoon_id": record["id"]})
            if runtime_err or not runtime:
                runtime_error = runtime_err
            else:
                live = await self._get_native(int(runtime["port"]), "/vocab")
                data = live.get("data") if isinstance(live.get("data"), dict) else {}
                live_words = data.get("words")
                runtime_vocab_size = data.get("vocab_size") if isinstance(data, dict) else None
                if isinstance(live_words, list):
                    runtime_words = {str(w).lower() for w in live_words}
                elif live.get("error"):
                    runtime_error = live
        checks = []
        for word in normalized:
            checks.append({
                "word": word,
                "file_present": word in file_word_to_id,
                "file_id": file_word_to_id.get(word),
                "runtime_present": (word in runtime_words) if runtime_words is not None else None,
            })
        return {
            "status": "ok",
            "cocoon_id": record["id"],
            "file_vocab_size": len(file_word_to_id),
            "runtime_vocab_size": runtime_vocab_size,
            "runtime_error": runtime_error,
            "checks": checks,
        }

    async def capabilities(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        record, err = await self._ensure_record(str(args.get("cocoon_id") or ""), args, auto_import=False)
        cocoon_id = record.get("id") if record else str(args.get("cocoon_id") or "")
        native_contract: dict[str, Any] | None = None
        if record and args.get("auto_start"):
            runtime, runtime_err = await self._ensure_started(args)
            if runtime and not runtime_err:
                native_contract = await self._get_native(int(runtime["port"]), "/capabilities")
                native_contract = self._unsupported_native_contract(native_contract, "/capabilities")
        return {
            "status": "ok" if record else "partial",
            "cocoon_id": cocoon_id,
            "record_error": err,
            "confirmed": {
                "managed_import": bool(record),
                "native_http_chat": True,
                "native_http_teach": True,
                "native_http_act": True,
                "native_http_learn": True,
                "slot_plugging": True,
                "shared_runtime_slot_replication": True,
                "independent_clone_import": True,
                "headless_sphere_game": True,
                "gym_cartpole_game": True,
                "curriculum_runtime_contract": bool(
                    native_contract and not native_contract.get("error") and not native_contract.get("unsupported")
                ),
            },
            "active_seams": {
                "persistent_post_runtime_learning": "Native teach/learn updates live memory; durable export/save requires a newer Cocoon build with /save and /export.",
                "tool_use": "Not native. Cocoon is RL/game-oriented; Council can wrap it, but it does not currently emit reliable tool-call JSON.",
                "embeddings": "RemoteProviderProxy advertises encode generically; Cocoon shim does not yet provide a real embedding lane.",
                "visual_game_processes": "Headless game spawning is safe. Visible pygame spawning may need an interactive desktop window policy.",
                "dreamer_bridge": "Council can call Cocoon /dreamer/observe and /dreamer/propose when the runtime exposes them; normalized game telemetry is still a follow-up.",
            },
            "recommended_next_connectors": [
                "Regenerate Cocoon ZIPs with the current Convergence compiler so /curriculum, /snapshot, /save, and /export exist.",
                "cocoon_game_observation to normalize game telemetry into Council/Dreamer state",
                "convergence_adapter to operate the full remote Convergence facility as a facade slot",
            ],
            "manager_tools": sorted(COCOON_TOOL_SPECS.keys()),
            "native_contract": native_contract,
        }

    async def curriculum(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime, err = await self._ensure_started(args or {})
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        result = await self._get_native(int(runtime["port"]), "/curriculum")
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/curriculum")

    async def training_logs(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        limit = _int_arg(args.get("limit"), 100, minimum=1, maximum=1000)
        result = await self._get_native(int(runtime["port"]), f"/training/logs?limit={limit}")
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/training/logs")

    async def score(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        payload = {
            "event_type": str(args.get("event_type") or "curriculum_score"),
            "stage": str(args.get("stage") or "curriculum"),
            "input": str(args.get("input") or ""),
            "target": str(args.get("target") or ""),
            "output": str(args.get("output") or ""),
            "reward": float(args.get("reward", 0.0) or 0.0),
            "coach": str(args.get("coach") or "champion_council"),
        }
        if isinstance(args.get("score"), dict):
            payload["score"] = args["score"]
        result = await self._post_native(int(runtime["port"]), "/curriculum/score", payload)
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/curriculum/score")

    async def snapshot(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime, err = await self._ensure_started(args or {})
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        result = await self._get_native(int(runtime["port"]), "/snapshot")
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/snapshot")

    async def save(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        output_dir, path_err = self._managed_output_path(runtime["record"], args.get("output_dir"), "live_state")
        if path_err or not output_dir:
            return {"error": path_err or "Invalid output_dir"}
        result = await self._post_native(int(runtime["port"]), "/save", {"output_dir": str(output_dir)})
        result["cocoon_id"] = runtime["record"]["id"]
        result["output_dir"] = str(output_dir)
        return self._unsupported_native_contract(result, "/save")

    async def export(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        output_path, path_err = self._managed_output_path(runtime["record"], args.get("path"), "evolved_cocoon.py")
        if path_err or not output_path:
            return {"error": path_err or "Invalid path"}
        result = await self._post_native(int(runtime["port"]), "/export", {"path": str(output_path)})
        result["cocoon_id"] = runtime["record"]["id"]
        result["path"] = str(output_path)
        return self._unsupported_native_contract(result, "/export")

    async def clone_from_live(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        source_record = runtime["record"]
        source_id = str(source_record.get("id") or "cocoon")
        clone_id = _safe_slug(str(args.get("new_cocoon_id") or args.get("clone_id") or f"{source_id}-live-{int(time.time())}"))
        source_dir = Path(str(source_record.get("path") or "")).resolve()
        dest = self._managed_dir(clone_id).resolve()
        overwrite = bool(args.get("overwrite", False))
        if not _inside(source_dir, self.root.resolve()):
            return {"error": f"Source Cocoon is outside manager root: {source_dir}"}
        if dest.exists() and not overwrite:
            return {"error": f"Managed clone already exists: {clone_id}", "cocoon_id": clone_id, "path": str(dest)}
        if dest.exists():
            if not _inside(dest, self.root.resolve()):
                return {"error": f"Refusing to overwrite outside manager root: {dest}"}
            await asyncio.to_thread(shutil.rmtree, dest)
        await asyncio.to_thread(shutil.copytree, source_dir, dest)
        export_result = await self._post_native(int(runtime["port"]), "/export", {"path": str(dest / "cocoon.py")})
        export_result = self._unsupported_native_contract(export_result, "/export")
        if export_result.get("error"):
            if _inside(dest, self.root.resolve()) and dest.exists():
                await asyncio.to_thread(shutil.rmtree, dest)
            return {"error": export_result.get("error"), "cocoon_id": clone_id, "export": export_result}
        inspect = await asyncio.to_thread(self._inspect_dir, dest, run_info=False)
        async with self._lock:
            registry = self._load_registry()
            record = {
                "id": clone_id,
                "source_path": f"live_clone:{source_id}",
                "source_cocoon_id": source_id,
                "path": str(dest),
                "imported_at": time.time(),
                "updated_at": time.time(),
                "inspect": inspect,
                "clone": {"source_cocoon_id": source_id, "export": export_result},
            }
            registry["cocoons"][clone_id] = record
            registry["default_id"] = clone_id
            self._save_registry(registry)
        return {"status": "ok", "cocoon_id": clone_id, "source_cocoon_id": source_id, "record": record}

    async def dreamer_observe(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        payload = {
            "game": str(args.get("game") or "unknown"),
            "observation": args.get("observation") if isinstance(args.get("observation"), dict) else args,
            "reward": args.get("reward"),
            "done": _bool_arg(args.get("done"), False),
        }
        result = await self._post_native(int(runtime["port"]), "/dreamer/observe", payload)
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/dreamer/observe")

    async def dreamer_propose(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        runtime, err = await self._ensure_started(args)
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        payload: dict[str, Any] = {}
        if args.get("env"):
            payload["env"] = str(args.get("env"))
        result = await self._post_native(int(runtime["port"]), "/dreamer/propose", payload)
        result["cocoon_id"] = runtime["record"]["id"]
        return self._unsupported_native_contract(result, "/dreamer/propose")

    async def vocab(self, cocoon_id: str = "") -> dict[str, Any]:
        runtime, err = await self._ensure_started({"cocoon_id": cocoon_id})
        if err or not runtime:
            return err or {"error": "Cocoon runtime unavailable"}
        return await self._get_native(int(runtime["port"]), "/vocab")

    async def plug_slot(
        self,
        args: dict[str, Any] | None,
        plug_callback: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None,
    ) -> dict[str, Any]:
        args = args or {}
        if not self.web_port:
            return {"error": "Cocoon OpenAI shim web_port is not configured"}
        started = await self.start(args)
        if started.get("error") or started.get("status") == "error":
            return started
        cocoon_id = str(started["cocoon_id"])
        model_name = f"cocoon:{cocoon_id}"
        model_url = f"http://127.0.0.1:{self.web_port}/api/cocoon/{quote(cocoon_id)}/v1?model={quote(model_name)}"
        plug_args: dict[str, Any] = {"model_id": model_url}
        if args.get("slot_name"):
            plug_args["slot_name"] = str(args.get("slot_name"))
        if plug_callback is None:
            return {"status": "ok", "cocoon_id": cocoon_id, "model_id": model_url, "plug_args": plug_args}
        plug_result = await plug_callback("plug_model", plug_args)
        return {
            "status": "ok",
            "cocoon_id": cocoon_id,
            "native_port": started.get("port"),
            "model_id": model_url,
            "plug_args": plug_args,
            "plug_result": plug_result,
        }

    async def openai_models(self, cocoon_id: str) -> dict[str, Any]:
        record, err = await self._ensure_record(cocoon_id, {}, auto_import=True)
        if err or not record:
            return {"error": err or "Cocoon record unavailable"}
        model_id = f"cocoon:{record['id']}"
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": int(record.get("imported_at") or time.time()),
                    "owned_by": "champion-council-cocoon",
                }
            ],
        }

    async def openai_chat(self, cocoon_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") if isinstance(payload, dict) else []
        prompt = ""
        if isinstance(messages, list) and messages:
            user_messages = [m for m in messages if isinstance(m, dict) and str(m.get("role") or "") == "user"]
            selected = user_messages[-1] if user_messages else messages[-1]
            prompt = _content_to_text(selected.get("content") if isinstance(selected, dict) else selected)
        if not prompt:
            prompt = _content_to_text(payload.get("prompt") if isinstance(payload, dict) else "")
        chat_payload = await self.chat(
            {
                "cocoon_id": cocoon_id,
                "prompt": prompt,
                "learn": _bool_arg(payload.get("learn"), False) if isinstance(payload, dict) else False,
                "auto_start": True,
            }
        )
        if chat_payload.get("error"):
            return chat_payload
        data = chat_payload.get("data") if isinstance(chat_payload.get("data"), dict) else {}
        content = str(data.get("response") or "")
        model = str(payload.get("model") or f"cocoon:{cocoon_id}")
        created = int(time.time())
        return {
            "id": f"chatcmpl-cocoon-{created}",
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(content.split()),
                "total_tokens": len(prompt.split()) + len(content.split()),
            },
            "cocoon": {
                "id": cocoon_id,
                "semantic_reward": data.get("semantic_reward"),
                "vp_value": data.get("vp_value"),
                "vocab_size": data.get("vocab_size"),
                "all_responses": data.get("all_responses"),
                "native": data,
            },
        }

    async def handle_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        plug_callback: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ) -> dict[str, Any] | None:
        args = args or {}
        if tool_name == "cocoon_import":
            return await self.import_cocoon(args)
        if tool_name == "cocoon_list":
            return await self.list_cocoons()
        if tool_name == "cocoon_info":
            return await self.info(args)
        if tool_name == "cocoon_start":
            return await self.start(args)
        if tool_name == "cocoon_stop":
            return await self.stop(args)
        if tool_name == "cocoon_chat":
            return await self.chat(args)
        if tool_name == "cocoon_teach":
            return await self.teach(args)
        if tool_name == "cocoon_act":
            return await self.act(args)
        if tool_name == "cocoon_learn":
            return await self.learn(args)
        if tool_name == "cocoon_run_game":
            return await self.run_game(args)
        if tool_name == "cocoon_spawn_game":
            return await self.spawn_game(args)
        if tool_name == "cocoon_game_status":
            return await self.game_status(args)
        if tool_name == "cocoon_stop_game":
            return await self.stop_game(args)
        if tool_name == "cocoon_vocab_check":
            return await self.vocab_check(args)
        if tool_name == "cocoon_capabilities":
            return await self.capabilities(args)
        if tool_name == "cocoon_curriculum":
            return await self.curriculum(args)
        if tool_name == "cocoon_training_logs":
            return await self.training_logs(args)
        if tool_name == "cocoon_score":
            return await self.score(args)
        if tool_name == "cocoon_snapshot":
            return await self.snapshot(args)
        if tool_name == "cocoon_save":
            return await self.save(args)
        if tool_name == "cocoon_export":
            return await self.export(args)
        if tool_name == "cocoon_clone_from_live":
            return await self.clone_from_live(args)
        if tool_name == "cocoon_dreamer_observe":
            return await self.dreamer_observe(args)
        if tool_name == "cocoon_dreamer_propose":
            return await self.dreamer_propose(args)
        if tool_name == "cocoon_plug_slot":
            return await self.plug_slot(args, plug_callback)
        return None
