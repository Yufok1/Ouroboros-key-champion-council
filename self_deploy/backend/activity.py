from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any


SILENT_TOOLS = frozenset([
    "get_status",
    "list_slots",
    "bag_catalog",
    "workflow_list",
    "verify_integrity",
    "get_cached",
    "get_identity",
    "feed",
    "get_capabilities",
    "get_help",
    "get_onboarding",
    "get_quickstart",
    "hub_tasks",
    "list_tools",
    "heartbeat",
    "api_health",
])


def parse_mcp_result(result: dict | None) -> dict | list | str | None:
    """Extract JSON payload from MCP text envelope if present."""
    if not result:
        return None

    if not isinstance(result, dict):
        return result

    # Prefer already-structured payload when present.
    structured = result.get("structuredContent")
    if structured is not None:
        return structured

    content = result.get("content")
    if isinstance(content, list) and content:
        text_chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue

            if "json" in item:
                return item.get("json")

            text = item.get("text")
            if isinstance(text, str) and text.strip():
                text_chunks.append(text)

        if text_chunks:
            joined_text = "\n".join(text_chunks).strip()
            try:
                return json.loads(joined_text)
            except (json.JSONDecodeError, TypeError):
                return {"text": joined_text}
    return result


class ActivityHub:
    def __init__(self, max_entries: int = 500, suppress_silent_tools: bool | None = None):
        self.max_entries = max_entries
        self.log: list[dict[str, Any]] = []
        self.subscribers: list[asyncio.Queue] = []
        self._next_event_id = 1
        self.session_id = os.environ.get("ACTIVITY_SESSION_ID", "").strip() or uuid.uuid4().hex
        if suppress_silent_tools is None:
            suppress_silent_tools = (
                os.environ.get("ACTIVITY_SUPPRESS_SILENT_TOOLS", "0").strip().lower()
                in ("1", "true", "yes", "on")
            )
        self.suppress_silent_tools = suppress_silent_tools

    @staticmethod
    def _coerce_event_id(value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None

    def add_entry(
        self,
        tool: str,
        args: dict,
        result: dict | None,
        duration_ms: int,
        error: str | None,
        source: str = "external",
        client_id: str | None = None,
    ) -> None:
        # Suppress hydration activity entirely.
        if source == "hydration":
            return
        # Optional noise suppression for internal/webui tools.
        if self.suppress_silent_tools and tool in SILENT_TOOLS and source not in ("external", "agent-inner"):
            return

        category = tool.split("_")[0] if tool else "other"
        parsed = parse_mcp_result(result)

        entry = {
            "tool": tool,
            "category": category,
            "args": args or {},
            "result": parsed,
            "error": error,
            "durationMs": duration_ms,
            "timestamp": int(time.time() * 1000),
            "source": source,
            "clientId": client_id,
            "eventId": self._next_event_id,
            "sessionId": self.session_id,
        }
        self._next_event_id += 1

        self.log.append(entry)
        if len(self.log) > self.max_entries:
            self.log.pop(0)

        dead: list[asyncio.Queue] = []
        for q in self.subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                # Slow subscribers should drop oldest buffered item rather than
                # get unsubscribed immediately during short bursts.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(entry)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                self.subscribers.remove(q)
            except ValueError:
                pass

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.log[-limit:]

    def recent_since(self, event_id: str | int | None, limit: int = 500) -> list[dict[str, Any]]:
        parsed_id = self._coerce_event_id(event_id)
        if parsed_id is None:
            return self.recent(limit)

        entries: list[dict[str, Any]] = []
        for entry in self.log:
            entry_id = self._coerce_event_id(entry.get("eventId"))
            if entry_id is not None and entry_id > parsed_id:
                entries.append(entry)
        if len(entries) > limit:
            entries = entries[-limit:]
        return entries

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self.subscribers.remove(q)
        except ValueError:
            pass

    async def stream(
        self,
        q: asyncio.Queue,
        heartbeat_seconds: int = 15,
        after_event_id: int | None = None,
    ):
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=heartbeat_seconds)
                except asyncio.TimeoutError:
                    # SSE keepalive to prevent idle disconnects in browsers/proxies.
                    yield ": ping\n\n"
                    continue

                if after_event_id is not None:
                    entry_id = self._coerce_event_id(entry.get("eventId"))
                    if entry_id is not None and entry_id <= after_event_id:
                        continue

                try:
                    payload = json.dumps(entry)
                except (TypeError, ValueError) as exc:
                    entry_safe = {k: v for k, v in entry.items() if k != "result"}
                    entry_safe["result"] = {"_serialization_error": str(exc)}
                    payload = json.dumps(entry_safe)
                event_id = entry.get("eventId")
                if event_id is not None:
                    yield f"id: {event_id}\n"
                yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(q)
