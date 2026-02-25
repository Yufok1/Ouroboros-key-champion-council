from __future__ import annotations

import json
import time
from typing import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .activity import parse_mcp_result


DEFAULT_DREAMER_CONFIG = {
    "rewards": {
        "hold_accept": 1.0,
        "hold_override": -0.5,
        "bag_induct": 0.8,
        "bag_forget": -0.3,
        "workflow_save": 1.0,
        "workflow_success": 0.5,
        "workflow_failure": -0.5,
        "tool_success": 0.1,
        "tool_error": -0.2,
        "mutation_kept": 0.3,
        "mutation_reverted": -0.1,
        "normalize": True,
    },
    "training": {
        "enabled": True,
        "auto_train": True,
        "world_model_frequency": 32,
        "critic_frequency": 32,
        "full_cycle_frequency": 64,
        "batch_size": 32,
        "noise_scale": 0.005,
        "gamma": 0.99,
        "lambda": 0.95,
        "critic_target_tau": 0.02,
        "timeout_budget_seconds": 30,
    },
    "imagination": {
        "horizon": 15,
        "n_actions": 8,
        "auto_imagine_on_train": True,
    },
    "buffers": {
        "reward_buffer_max": 5000,
        "obs_buffer_max": 1000,
        "value_history_max": 200,
        "reward_rate_window": 100,
    },
    "architecture": {
        "critic_hidden_dim": 256,
        "reward_head_hidden_dim": 128,
        "continue_head_hidden_dim": 64,
        "latent_dim": 5120,
    },
}


class DreamerService:
    def __init__(self, call_tool_fn: Callable[[str, dict], Awaitable[dict]]):
        self.call_tool_fn = call_tool_fn
        self.cache = {"data": None, "ts": 0.0}
        self.history = {
            "critic_loss": [],
            "reward_counts": [],
            "fitness": [],
        }
        self.last_cycle = 0

    async def state(self) -> dict:
        now = time.time()
        if self.cache["data"] and (now - self.cache["ts"]) < 3:
            return self.cache["data"]

        status_raw = await self.call_tool_fn("get_status", {})
        rssm_raw = await self.call_tool_fn("show_rssm", {})
        weights_raw = await self.call_tool_fn("show_weights", {})
        lora_raw = await self.call_tool_fn("show_lora", {})

        status = parse_mcp_result(status_raw.get("result")) or {}
        rssm = parse_mcp_result(rssm_raw.get("result")) or {}
        weights = parse_mcp_result(weights_raw.get("result")) or {}
        lora = parse_mcp_result(lora_raw.get("result")) or {}

        dreamer = status.get("dreamer", {}) if isinstance(status, dict) else {}

        cycles = dreamer.get("training_cycles", 0)
        if cycles > self.last_cycle and dreamer.get("last_train"):
            lt = dreamer["last_train"]
            self.history["critic_loss"].append(
                {
                    "ts": now,
                    "cycle": cycles,
                    "baseline": lt.get("critic_baseline_loss"),
                    "perturbed": lt.get("critic_perturbed_loss"),
                    "accepted": lt.get("accepted"),
                }
            )
            if len(self.history["critic_loss"]) > 200:
                self.history["critic_loss"] = self.history["critic_loss"][-200:]
            self.last_cycle = cycles

        self.history["reward_counts"].append({"ts": now, "count": dreamer.get("reward_count", 0)})
        self.history["fitness"].append({"ts": now, "value": dreamer.get("fitness", 0)})

        for key in ("reward_counts", "fitness"):
            if len(self.history[key]) > 200:
                self.history[key] = self.history[key][-200:]

        result = {
            "dreamer": dreamer,
            "rssm": rssm.get("metrics", {}).get("other", {}) if isinstance(rssm, dict) else {},
            "weights": weights,
            "lora": lora,
            "history": self.history,
            "generation": status.get("generation") if isinstance(status, dict) else None,
            "fitness": status.get("fitness") if isinstance(status, dict) else None,
        }

        self.cache["data"] = result
        self.cache["ts"] = now
        return result

    async def get_config(self) -> dict:
        result = await self.call_tool_fn("bag_get", {"key": "dreamer_config"})
        parsed = parse_mcp_result(result.get("result"))

        if isinstance(parsed, dict) and "value" in parsed:
            try:
                return {"config": json.loads(parsed["value"]), "source": "bag"}
            except (json.JSONDecodeError, TypeError):
                pass

        return {"config": DEFAULT_DREAMER_CONFIG, "source": "defaults"}

    async def save_config(self, config: dict) -> dict:
        result = await self.call_tool_fn(
            "bag_induct",
            {
                "key": "dreamer_config",
                "content": json.dumps(config),
                "item_type": "config",
            },
        )
        parsed = parse_mcp_result(result.get("result"))
        return {"status": "saved", "result": parsed}

    async def reset_config(self) -> dict:
        await self.call_tool_fn("bag_forget", {"key": "dreamer_config"})
        return {"status": "reset", "config": DEFAULT_DREAMER_CONFIG}


def create_dreamer_router(call_tool_fn: Callable[[str, dict], Awaitable[dict]]) -> APIRouter:
    router = APIRouter(prefix="/api/dreamer", tags=["dreamer"])
    svc = DreamerService(call_tool_fn)

    @router.get("/state")
    async def dreamer_state():
        return await svc.state()

    @router.get("/config")
    async def dreamer_config_get():
        return await svc.get_config()

    @router.post("/config")
    async def dreamer_config_save(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

        config = body.get("config", body)
        return await svc.save_config(config)

    @router.post("/config/reset")
    async def dreamer_config_reset():
        return await svc.reset_config()

    return router
