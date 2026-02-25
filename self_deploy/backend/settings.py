from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


PERSISTENCE_MODES = ("local", "hf", "both")


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (does not override existing env vars)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_port: int
    mcp_port: int
    mcp_base_url: str
    capsule_path: Path
    capsule_gz_path: Path
    capsule_download_url: str
    frontend_dir: Path
    data_dir: Path
    activity_log_max: int
    persistence_mode: Literal["local", "hf", "both"]
    autosave_interval: int
    save_cooldown: int
    log_level: str

    # Integration/env passthrough
    hf_token: str
    space_author_name: str
    space_id: str


def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[1]  # self_deploy/
    default_env = base_dir / "config" / ".env"
    _load_env_file(default_env)

    app_port = int(os.environ.get("APP_PORT", "7866"))
    mcp_port = int(os.environ.get("MCP_PORT", "8766"))
    app_env = os.environ.get("APP_ENV", "development")

    capsule_raw = os.environ.get("CAPSULE_PATH", "./capsule/champion_gen8.py")
    capsule_path = (base_dir / capsule_raw).resolve() if not Path(capsule_raw).is_absolute() else Path(capsule_raw)

    gz_raw = os.environ.get("CAPSULE_GZ_PATH", "./capsule/capsule.gz")
    capsule_gz_path = (base_dir / gz_raw).resolve() if not Path(gz_raw).is_absolute() else Path(gz_raw)
    capsule_download_url = os.environ.get(
        "CAPSULE_DOWNLOAD_URL",
        "https://huggingface.co/spaces/tostido/Champion_Council/resolve/main/capsule/capsule.gz",
    ).strip()

    mcp_base = os.environ.get("MCP_BASE_URL", f"http://127.0.0.1:{mcp_port}")

    mode_raw = os.environ.get("PERSISTENCE_MODE", "local").strip().lower()
    persistence_mode = mode_raw if mode_raw in PERSISTENCE_MODES else "local"

    data_raw = os.environ.get("DATA_DIR", "./data")
    data_dir = (base_dir / data_raw).resolve() if not Path(data_raw).is_absolute() else Path(data_raw)

    frontend_raw = os.environ.get("FRONTEND_DIR", "./frontend")
    frontend_dir = (base_dir / frontend_raw).resolve() if not Path(frontend_raw).is_absolute() else Path(frontend_raw)

    return Settings(
        app_env=app_env,
        app_port=app_port,
        mcp_port=mcp_port,
        mcp_base_url=mcp_base,
        capsule_path=capsule_path,
        capsule_gz_path=capsule_gz_path,
        capsule_download_url=capsule_download_url,
        frontend_dir=frontend_dir,
        data_dir=data_dir,
        activity_log_max=int(os.environ.get("ACTIVITY_LOG_MAX", "500")),
        persistence_mode=persistence_mode,  # type: ignore[arg-type]
        autosave_interval=int(os.environ.get("AUTOSAVE_INTERVAL", "300")),
        save_cooldown=int(os.environ.get("SAVE_COOLDOWN", "120")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        hf_token=os.environ.get("HF_TOKEN", ""),
        space_author_name=os.environ.get("SPACE_AUTHOR_NAME", ""),
        space_id=os.environ.get("SPACE_ID", ""),
    )
