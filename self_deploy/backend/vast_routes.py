from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import APIRouter

from .activity import parse_mcp_result, ActivityHub


class VastService:
    def __init__(self, call_tool_fn: Callable[[str, dict], Awaitable[dict]], activity_hub: ActivityHub):
        self.call_tool_fn = call_tool_fn
        self.activity_hub = activity_hub
        self.cache = {"data": None, "ts": 0.0}

    async def state(self) -> dict:
        now = time.time()
        if self.cache["data"] and (now - self.cache["ts"]) < 5:
            return self.cache["data"]

        result = await self.call_tool_fn("vast_instances", {})
        parsed = parse_mcp_result(result.get("result"))

        status_raw = await self.call_tool_fn("get_status", {})
        status = parse_mcp_result(status_raw.get("result")) or {}

        vast_activity = [
            {
                "tool": entry.get("tool", ""),
                "status": "error" if entry.get("error") else "ok",
                "duration": entry.get("durationMs", 0),
                "timestamp": entry.get("timestamp", 0),
            }
            for entry in self.activity_hub.log
            if entry.get("tool", "").startswith("vast_")
        ][-10:]

        fleet = {
            "instances": parsed if isinstance(parsed, (list, dict)) else [],
            "activity": vast_activity,
            "slots_filled": status.get("slots_filled", 0) if isinstance(status, dict) else 0,
        }

        self.cache["data"] = fleet
        self.cache["ts"] = now
        return fleet


def create_vast_router(call_tool_fn: Callable[[str, dict], Awaitable[dict]], activity_hub: ActivityHub) -> APIRouter:
    router = APIRouter(prefix="/api/vast", tags=["vast"])
    svc = VastService(call_tool_fn, activity_hub)

    @router.get("/state")
    async def vast_state():
        return await svc.state()

    return router
