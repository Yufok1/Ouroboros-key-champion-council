from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter

from .activity import parse_mcp_result, ActivityHub


def _normalize_vast_instances(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("instances", "data", "results", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        if any(k in payload for k in ("id", "instance_id", "ssh_host", "ssh_port", "gpu", "gpu_name", "public_ip")):
            return [payload]
    return []


def _ssh_bootstrap_status() -> dict:
    ssh_dir = Path.home() / ".ssh"
    private_key = ssh_dir / "id_rsa"
    public_key = ssh_dir / "id_rsa.pub"
    return {
        "dir": str(ssh_dir),
        "private_key": private_key.exists(),
        "public_key": public_key.exists(),
        "private_key_secret_configured": bool(os.environ.get("SSH_PRIVATE_KEY", "").strip()),
    }


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
        instances = _normalize_vast_instances(parsed)

        status_raw = await self.call_tool_fn("get_status", {})
        status = parse_mcp_result(status_raw.get("result")) or {}

        vast_activity = [
            {
                "tool": entry.get("tool", ""),
                "status": "error" if entry.get("error") else "ok",
                "duration": entry.get("durationMs", 0),
                "timestamp": entry.get("timestamp", 0),
                "error": entry.get("error"),
            }
            for entry in self.activity_hub.log
            if entry.get("tool", "").startswith("vast_")
        ][-10:]

        fleet = {
            "instances": instances,
            "activity": vast_activity,
            "slots_filled": status.get("slots_filled", 0) if isinstance(status, dict) else 0,
            "ssh": _ssh_bootstrap_status(),
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
