from __future__ import annotations

import asyncio
import time
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


class MCPClient:
    """Managed MCP SDK session with reconnect semantics."""

    def __init__(self, mcp_base_url: str):
        self.mcp_base_url = mcp_base_url.rstrip("/")
        self._session: ClientSession | None = None
        self._lock = asyncio.Lock()

        self._sse_cm = None
        self._session_cm = None
        self._read_stream = None
        self._write_stream = None

        # Reconnect throttling (exponential backoff)
        self._reconnect_attempts = 0
        self._next_retry_ts = 0.0

        # Rich instructions from capsule handshake (populated during connect)
        self.capsule_instructions: str | None = None

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def reconnect_state(self) -> dict[str, Any]:
        now = time.time()
        retry_in = max(0.0, self._next_retry_ts - now)
        return {
            "attempts": self._reconnect_attempts,
            "retry_in_seconds": round(retry_in, 2),
            "next_retry_ts": self._next_retry_ts,
        }

    async def connect(self, force: bool = False) -> bool:
        async with self._lock:
            if self._session is not None:
                return True

            now = time.time()
            if not force and now < self._next_retry_ts:
                return False

            try:
                self._sse_cm = sse_client(f"{self.mcp_base_url}/sse")
                self._read_stream, self._write_stream = await self._sse_cm.__aenter__()

                self._session_cm = ClientSession(self._read_stream, self._write_stream)
                self._session = await self._session_cm.__aenter__()

                result = await self._session.initialize()

                # Cache the capsule's rich MCP instructions (built by
                # _build_mcp_instructions() in champion_gen8.py).
                _instr = getattr(result, 'instructions', None)
                if _instr is None and hasattr(result, 'model_dump'):
                    _instr = result.model_dump().get('instructions')
                if _instr and isinstance(_instr, str) and len(_instr) > 100:
                    self.capsule_instructions = _instr

                # Successful reconnect clears backoff state.
                self._reconnect_attempts = 0
                self._next_retry_ts = 0.0
                return True
            except Exception:
                await self._disconnect_inner()

                self._reconnect_attempts = min(self._reconnect_attempts + 1, 16)
                delay = min(2 ** self._reconnect_attempts, 30)
                self._next_retry_ts = time.time() + delay
                return False

    async def _disconnect_inner(self) -> None:
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None

        if self._sse_cm:
            try:
                await self._sse_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._sse_cm = None

        self._session = None

    async def disconnect(self) -> None:
        async with self._lock:
            await self._disconnect_inner()

    async def ensure_session(self) -> ClientSession | None:
        if self._session is not None:
            return self._session
        ok = await self.connect()
        return self._session if ok else None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        session = await self.ensure_session()
        if not session:
            return {"error": "MCP session not available", "reconnect": self.reconnect_state}

        try:
            result = await session.call_tool(name, arguments)
            return {
                "result": {
                    "content": [
                        {"type": c.type, "text": c.text if hasattr(c, "text") else str(c)}
                        for c in (result.content or [])
                    ],
                    "isError": getattr(result, "isError", None) or getattr(result, "is_error", False),
                }
            }
        except Exception as exc:
            await self.disconnect()
            return {"error": str(exc), "reconnect": self.reconnect_state}

    async def list_tools(self) -> dict[str, Any]:
        session = await self.ensure_session()
        if not session:
            return {"error": "MCP session not available", "reconnect": self.reconnect_state}

        try:
            result = await session.list_tools()
            return {
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": getattr(t, "inputSchema", None)
                            or getattr(t, "input_schema", {}),
                        }
                        for t in (result.tools or [])
                    ]
                }
            }
        except Exception as exc:
            await self.disconnect()
            return {"error": str(exc), "reconnect": self.reconnect_state}
