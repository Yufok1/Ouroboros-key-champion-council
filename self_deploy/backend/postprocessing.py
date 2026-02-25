from __future__ import annotations

import json
from typing import Awaitable, Callable

from .activity import parse_mcp_result


def normalize_workflow_nodes(definition: str | dict) -> str:
    """Ensure workflow nodes include both tool and tool_name fields.

    Also normalizes legacy node type tool_call -> tool.
    """
    try:
        defn = json.loads(definition) if isinstance(definition, str) else definition
        nodes = defn.get("nodes", [])
        changed = False

        for node in nodes:
            if node.get("type") == "tool_call":
                node["type"] = "tool"
                changed = True

            tool_name = node.get("tool_name") or node.get("tool")
            if tool_name:
                if "tool_name" not in node:
                    node["tool_name"] = tool_name
                    changed = True
                if "tool" not in node:
                    node["tool"] = tool_name
                    changed = True

        if changed:
            return json.dumps(defn)
        return definition if isinstance(definition, str) else json.dumps(definition)
    except Exception:
        return definition if isinstance(definition, str) else json.dumps(definition)


async def postprocess_tool_result(
    tool_name: str,
    args: dict,
    result: dict,
    call_tool_fn: Callable[[str, dict], Awaitable[dict]],
) -> dict:
    """Apply compatibility patches for known capsule/tool edge cases."""
    parsed = parse_mcp_result(result.get("result"))

    def _return_parsed(payload: dict | list | str) -> dict:
        return {"result": {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": True}}

    # If the capsule returns an error payload in content text, keep MCP isError
    # aligned so callers can reliably branch on transport-success/tool-error.
    if isinstance(parsed, dict) and "error" in parsed:
        if isinstance(result.get("result"), dict):
            result["result"]["isError"] = True

    # get_genesis may fail with NoneType in some capsule states.
    if tool_name == "get_genesis":
        error_str = str(result.get("error") or "")
        parsed_str = str(parsed or "")
        if "NoneType" in error_str or "NoneType" in parsed_str:
            safe = {
                "genesis_hash": None,
                "lineage": [],
                "note": "Genesis data not initialized for this capsule instance",
            }
            return {"result": {"content": [{"type": "text", "text": json.dumps(safe)}]}}

    # compare / debate may fail for chat templates that reject system role.
    if tool_name in ("compare", "debate") and isinstance(parsed, dict):
        comparisons = parsed.get("comparisons", [])
        transcript = parsed.get("transcript", [])
        patched = False

        for entry in comparisons:
            err = entry.get("error")
            if err == "System role not supported" or (
                entry.get("status") == "error" and "System role" in str(err)
            ):
                slot_idx = entry.get("slot")
                if slot_idx is None:
                    continue
                retry = await call_tool_fn(
                    "invoke_slot",
                    {
                        "slot": slot_idx,
                        "text": args.get("input_text", ""),
                        "mode": "forward",
                        "max_tokens": 200,
                    },
                )
                retry_parsed = parse_mcp_result(retry.get("result"))
                if isinstance(retry_parsed, dict) and "output" in retry_parsed:
                    entry["type"] = "generation"
                    entry["output"] = retry_parsed["output"]
                    entry.pop("error", None)
                    entry.pop("status", None)
                    entry["note"] = "retried via forward mode (no system role)"
                    patched = True

        for round_entry in transcript:
            for entry in round_entry.get("entries", []):
                if entry.get("error") == "System role not supported":
                    entry["response"] = "[Skipped: model does not support system role in chat template]"
                    entry["type"] = "skipped"
                    entry.pop("error", None)
                    patched = True

        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # orchestra consensus metrics can fail if outputs are non-numeric structured objects.
    if tool_name == "orchestra" and isinstance(parsed, dict):
        outputs = parsed.get("outputs", [])
        has_consensus_error = any(
            output.get("status") == "error" and "unsupported operand" in str(output.get("error", ""))
            for output in outputs
            if isinstance(output, dict)
        )
        if has_consensus_error:
            parsed["consensus_mean"] = None
            parsed["divergence"] = None
            parsed["note"] = (
                "Consensus averaging failed — clone outputs are structured dicts, not numeric. "
                "Individual clone outputs preserved above."
            )
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # Vast tool wrappers can surface opaque JSON decode errors when upstream CLI
    # emits empty/non-JSON output (commonly auth/config/instance issues).
    if tool_name.startswith("vast_") and isinstance(parsed, dict):
        err = str(parsed.get("error") or "").strip()
        if err == "Expecting value: line 1 column 1 (char 0)":
            normalized = {
                "error": (
                    f"{tool_name} received empty/non-JSON output from Vast backend. "
                    "This usually means authentication is missing/invalid or the requested "
                    "instance is unavailable."
                ),
                "error_code": "vast_non_json_response",
                "hints": [
                    "Set VAST_API_KEY in the runtime environment.",
                    "Run vast_search to verify API connectivity.",
                    "For instance-scoped tools, pass a valid instance_id from vast_instances.",
                ],
                "original_error": err,
            }
            return _return_parsed(normalized)

    return result
