from __future__ import annotations

import asyncio
import gzip
import os
import signal
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

import httpx


class CapsuleManager:
    def __init__(self, capsule_path: Path, capsule_gz_path: Path, mcp_port: int, log_max_lines: int = 2000):
        self.capsule_path = capsule_path
        self.capsule_gz_path = capsule_gz_path
        self.mcp_port = mcp_port
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

        if self.capsule_gz_path.exists():
            self.capsule_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(self.capsule_gz_path, "rb") as src:
                self.capsule_path.write_bytes(src.read())
            return self.capsule_path.exists()

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

        self.process = subprocess.Popen(cmd, **popen_kwargs)
        self.log_lines.append(f"[start] capsule pid={self.process.pid} mcp_port={self.mcp_port}")
        self._start_log_reader()
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
