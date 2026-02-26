from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
import os


def _extract_capsule(gz_path: Path, capsule_path: Path) -> bool:
    capsule_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = capsule_path.with_suffix(capsule_path.suffix + ".tmp")
    try:
        with gzip.open(gz_path, "rb") as src, tmp.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        tmp.replace(capsule_path)
        return capsule_path.exists() and capsule_path.stat().st_size > 0
    except Exception as exc:
        print(f"[capsule-bootstrap] extract failed: {exc}", file=sys.stderr)
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def _download_capsule(url: str, gz_path: Path) -> bool:
    gz_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = gz_path.with_suffix(gz_path.suffix + ".tmp")
    try:
        with urllib.request.urlopen(url, timeout=180) as resp, tmp.open("wb") as dst:
            shutil.copyfileobj(resp, dst)
        tmp.replace(gz_path)
        return gz_path.exists() and gz_path.stat().st_size > 0
    except Exception as exc:
        print(f"[capsule-bootstrap] download failed: {exc}", file=sys.stderr)
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def _ensure_capsule(capsule_path: Path, capsule_gz_path: Path, fallback_gz_path: Path, download_url: str) -> bool:
    if capsule_path.exists():
        return True

    if capsule_gz_path.exists() and _extract_capsule(capsule_gz_path, capsule_path):
        return True

    if fallback_gz_path.exists():
        capsule_gz_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(fallback_gz_path, capsule_gz_path)
        except Exception as exc:
            print(f"[capsule-bootstrap] fallback copy failed: {exc}", file=sys.stderr)
        if capsule_gz_path.exists() and _extract_capsule(capsule_gz_path, capsule_path):
            return True

    if download_url and _download_capsule(download_url, capsule_gz_path):
        return _extract_capsule(capsule_gz_path, capsule_path)

    return False


def main() -> int:
    capsule_path = Path(os.environ.get("CAPSULE_PATH", "/app/capsule/champion_gen8.py"))
    capsule_gz_path = Path(os.environ.get("CAPSULE_GZ_PATH", "/app/capsule/capsule.gz"))
    fallback_gz_path = Path(os.environ.get("CAPSULE_BOOTSTRAP_GZ_PATH", "/app/bootstrap/capsule.gz"))
    download_url = os.environ.get(
        "CAPSULE_DOWNLOAD_URL",
        "https://huggingface.co/spaces/tostido/Champion_Council/resolve/main/capsule/capsule.gz",
    ).strip()
    mcp_port = os.environ.get("MCP_PORT", "8766")

    if not _ensure_capsule(capsule_path, capsule_gz_path, fallback_gz_path, download_url):
        print(
            "[capsule-bootstrap] champion_gen8.py is missing and could not be restored "
            "from local gzip, fallback mount, or download URL.",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, "-u", str(capsule_path), "--mcp-remote", "--port", str(mcp_port)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
