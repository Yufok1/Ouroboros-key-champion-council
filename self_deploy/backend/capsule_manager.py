from __future__ import annotations

import asyncio
import gzip
import os
import signal
import subprocess
import sys
import time
import threading
from collections import deque
from pathlib import Path

import httpx


class CapsuleManager:
    def __init__(
        self,
        capsule_path: Path,
        capsule_gz_path: Path,
        mcp_port: int,
        capsule_download_url: str = "",
        log_max_lines: int = 2000,
    ):
        self.capsule_path = capsule_path
        self.capsule_gz_path = capsule_gz_path
        self.mcp_port = mcp_port
        self.capsule_download_url = capsule_download_url
        self.process: subprocess.Popen | None = None
        self.log_lines: deque[str] = deque(maxlen=log_max_lines)

    @property
    def mcp_base_url(self) -> str:
        return f"http://127.0.0.1:{self.mcp_port}"

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.is_running and self.process else None

    def ensure_capsule_file(self) -> bool:
        if self.capsule_path.exists():
            return True
        return self._rebuild_capsule_file()

    def _ensure_capsule_gz(self) -> bool:
        if self.capsule_gz_path.exists():
            return True
        if self.capsule_download_url and self._download_capsule_gz():
            self.log_lines.append(f"[download] capsule fetched: {self.capsule_gz_path}")
            return True
        return False

    def _extract_capsule_from_gz(self) -> bool:
        target = self.capsule_path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            with gzip.open(self.capsule_gz_path, "rb") as src, tmp.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            tmp.replace(target)
            return target.exists() and target.stat().st_size > 0
        except Exception as exc:
            self.log_lines.append(f"[error] capsule extract failed: {exc}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            return False

    def _rebuild_capsule_file(self) -> bool:
        if not self._ensure_capsule_gz():
            return False
        return self._extract_capsule_from_gz()

    def _download_capsule_gz(self) -> bool:
        target = self.capsule_gz_path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            with httpx.stream(
                "GET",
                self.capsule_download_url,
                timeout=180,
                follow_redirects=True,
            ) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        if chunk:
                            f.write(chunk)
            tmp.replace(target)
            return target.exists() and target.stat().st_size > 0
        except Exception as exc:
            self.log_lines.append(f"[error] capsule download failed: {exc}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            return False

    def _start_log_reader(self) -> None:
        assert self.process and self.process.stdout

        def _reader() -> None:
            try:
                for line in iter(self.process.stdout.readline, b""):
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    self.log_lines.append(decoded)
            except Exception as exc:
                self.log_lines.append(f"[capsule-log-reader-error] {exc}")

        threading.Thread(target=_reader, daemon=True).start()

    def start(self) -> bool:
        if self.is_running:
            return True

        if not self.ensure_capsule_file():
            self.log_lines.append(f"[error] capsule not found: {self.capsule_path}")
            return False

        env = {**os.environ, "MCP_PORT": str(self.mcp_port)}
        cmd = [sys.executable, "-u", str(self.capsule_path), "--mcp-remote", "--port", str(self.mcp_port)]

        popen_kwargs: dict = {
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }

        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            popen_kwargs["preexec_fn"] = os.setsid

        def _spawn() -> subprocess.Popen:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            self.log_lines.append(f"[start] capsule pid={proc.pid} mcp_port={self.mcp_port}")
            self.process = proc
            self._start_log_reader()
            return proc

        def _exited_quickly(seconds: float = 3.0) -> bool:
            deadline = time.time() + seconds
            while time.time() < deadline:
                if self.process is None:
                    return True
                if self.process.poll() is not None:
                    return True
                time.sleep(0.1)
            return False

        _spawn()
        if not _exited_quickly():
            return True

        code = self.process.poll() if self.process else None
        self.log_lines.append(f"[warn] capsule exited early (code={code}); attempting rebuild")
        self.process = None

        # Rebuild from gzip to recover from partial/corrupt extracted file.
        try:
            if self.capsule_path.exists():
                self.capsule_path.unlink()
        except Exception:
            pass
        if not self._rebuild_capsule_file():
            self.log_lines.append("[error] capsule rebuild failed")
            return False

        _spawn()
        if _exited_quickly():
            code = self.process.poll() if self.process else None
            self.log_lines.append(f"[error] capsule exited after rebuild (code={code})")
            self.process = None
            return False
        return True

    def stop(self, timeout: int = 10) -> None:
        if not self.process:
            return

        proc = self.process
        try:
            if proc.poll() is None:
                if os.name == "nt":
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                        proc.wait(timeout=3)
                    except Exception:
                        pass
                    if proc.poll() is None:
                        proc.terminate()
                else:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        proc.terminate()

                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        finally:
            self.process = None
            self.log_lines.append("[stop] capsule stopped")

    def restart(self) -> bool:
        self.stop()
        return self.start()

    async def wait_for_sse(self, timeout: int = 90) -> bool:
        """Wait for capsule SSE endpoint to become reachable."""
        for _ in range(timeout):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.head(f"{self.mcp_base_url}/sse", timeout=2)
                    if r.status_code in (200, 405):
                        return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    def tail(self, n: int = 100) -> list[str]:
        if n <= 0:
            return []
        return list(self.log_lines)[-n:]
