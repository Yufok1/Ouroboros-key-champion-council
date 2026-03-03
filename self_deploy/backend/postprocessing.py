from __future__ import annotations

import asyncio
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


def _is_default_slot_name(name: str) -> bool:
    v = str(name or "").strip().lower()
    if v in ("empty", "vacant"):
        return True
    if v.startswith("slot_") and v[5:].isdigit():
        return True
    if v.startswith("slot-") and v[5:].isdigit():
        return True
    if v.startswith("slot ") and v[5:].isdigit():
        return True
    return False


async def postprocess_tool_result(
    tool_name: str,
    args: dict,
    result: dict,
    call_tool_fn: Callable[[str, dict], Awaitable[dict]],
    activity_hub=None,
) -> dict:
    """Apply compatibility patches for known capsule/tool edge cases."""
    parsed = parse_mcp_result(result.get("result"))

    # Normalize compact list_slots/council_status summaries to explicit per-slot state.
    if tool_name in ("list_slots", "council_status") and isinstance(parsed, dict):
        slots = parsed.get("slots")
        all_ids = parsed.get("all_ids")
        total = parsed.get("total")
        if (not isinstance(slots, list) or len(slots) == 0) and isinstance(all_ids, list) and isinstance(total, int) and total > 0:
            enriched_slots = []
            for i in range(total):
                name = all_ids[i] if i < len(all_ids) else f"slot_{i}"
                enriched_slots.append(
                    {
                        "index": i,
                        "name": name,
                        "plugged": False,
                        "model_source": None,
                    }
                )

            plugged_sum = None
            try:
                plugged_sum = int((((parsed.get("stats") or {}).get("plugged") or {}).get("sum")))
            except Exception:
                plugged_sum = None

            candidate_indices = [i for i, s in enumerate(enriched_slots) if not _is_default_slot_name(s.get("name", ""))]
            if plugged_sum is not None:
                if plugged_sum <= 0:
                    parsed["slots"] = enriched_slots
                    return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
                if plugged_sum > len(candidate_indices):
                    candidate_indices = list(range(total))
            elif len(candidate_indices) == 0:
                candidate_indices = list(range(total))

            if candidate_indices:
                async def _fetch_slot_info(idx: int):
                    info_raw = await call_tool_fn("slot_info", {"slot": idx})
                    info = parse_mcp_result(info_raw.get("result")) if isinstance(info_raw, dict) else None
                    return idx, info

                seen = set()
                calls = []
                for idx in candidate_indices:
                    if idx in seen or idx < 0 or idx >= total:
                        continue
                    seen.add(idx)
                    calls.append(_fetch_slot_info(idx))

                infos = await asyncio.gather(*calls, return_exceptions=True) if calls else []
                for item in infos:
                    if isinstance(item, Exception):
                        continue
                    idx, info = item
                    if not isinstance(info, dict):
                        continue

                    slot = enriched_slots[idx]
                    if info.get("name"):
                        slot["name"] = info["name"]
                    is_plugged = bool(info.get("plugged"))
                    slot["plugged"] = is_plugged
                    src = info.get("source") or info.get("model_source")
                    if not src and is_plugged and not _is_default_slot_name(slot.get("name", "")):
                        src = slot.get("name")
                    slot["model_source"] = src if is_plugged else None
                    if info.get("model_type"):
                        slot["model_type"] = info["model_type"]

            parsed["slots"] = enriched_slots
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

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

    # --- Helper: detect retryable slot errors ---
    def _is_retryable_slot_error(err_str: str) -> bool:
        if not err_str:
            return False
        markers = ("Remote embedding failed", "HTTP Error 404", "System role not supported",
                    "not callable", "is not callable", "embedding failed")
        return any(m.lower() in err_str.lower() for m in markers)

    async def _retry_slot_generate(slot_idx: int, text: str, max_tokens: int = 300):
        try:
            retry = await call_tool_fn("invoke_slot", {
                "slot": int(slot_idx), "text": text, "mode": "generate", "max_tokens": max_tokens,
            })
            retry_parsed = parse_mcp_result(retry.get("result"))
            if isinstance(retry_parsed, dict):
                out = retry_parsed.get("output", "")
                if out:
                    return str(out)
        except Exception:
            pass
        return None

    # --- Fix compare: retry slots that fail ---
    if tool_name == "compare" and isinstance(parsed, dict):
        comparisons = parsed.get("comparisons", [])
        patched = False
        for entry in comparisons:
            err = str(entry.get("error", ""))
            if entry.get("status") == "error" and _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    out = await _retry_slot_generate(slot_idx, args.get("input_text", ""))
                    if out:
                        entry["type"] = "generation"
                        entry["output"] = out
                        entry.pop("error", None)
                        entry["status"] = "ok"
                        entry["note"] = "retried via generate mode"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix debate: retry slots that fail ---
    if tool_name == "debate" and isinstance(parsed, dict):
        transcript = parsed.get("transcript", [])
        patched = False
        for rnd in transcript:
            for entry in rnd.get("entries", []):
                err = str(entry.get("error", ""))
                if _is_retryable_slot_error(err):
                    slot_idx = None
                    councilor = entry.get("councilor", "")
                    try:
                        slots_result = await call_tool_fn("list_slots", {})
                        slots_parsed = parse_mcp_result(slots_result.get("result"))
                        if isinstance(slots_parsed, dict):
                            for s in slots_parsed.get("slots", []):
                                if s.get("name") == councilor and s.get("plugged"):
                                    slot_idx = s.get("index")
                                    break
                    except Exception:
                        pass
                    if slot_idx is not None:
                        topic = args.get("text", "")
                        prompt = f"Debate topic: {topic}\nProvide your position in a clear paragraph."
                        out = await _retry_slot_generate(slot_idx, prompt, 400)
                        if out:
                            entry["response"] = out
                            entry.pop("error", None)
                            entry["note"] = "retried via generate mode"
                            patched = True
                    else:
                        entry["response"] = f"[Skipped: {err}]"
                        entry.pop("error", None)
                        entry["type"] = "skipped"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix broadcast/all_slots: retry slots that fail ---
    if tool_name in ("broadcast", "all_slots") and isinstance(parsed, dict):
        responses = parsed.get("responses", [])
        patched = False
        for entry in responses:
            err = str(entry.get("error", ""))
            if _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    text = args.get("message", "") or args.get("text", "")
                    out = await _retry_slot_generate(slot_idx, text)
                    if out:
                        entry["response"] = out
                        entry.pop("error", None)
                        entry.pop("status", None)
                        entry["note"] = "retried via generate mode"
                        patched = True
        if patched:
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # --- Fix pipe/chain: retry slots that fail ---
    if tool_name in ("pipe", "chain") and isinstance(parsed, dict):
        trace = parsed.get("trace", [])
        patched = False
        prev_output = args.get("input_text", "") or args.get("text", "")
        for entry in trace:
            if entry.get("slot") == "input":
                prev_output = entry.get("output", "") or entry.get("value", "") or prev_output
                continue
            err = str(entry.get("error", ""))
            if _is_retryable_slot_error(err):
                slot_idx = entry.get("slot")
                if slot_idx is not None:
                    out = await _retry_slot_generate(slot_idx, prev_output)
                    if out:
                        entry["output"] = out
                        entry.pop("error", None)
                        entry.pop("status", None)
                        entry["note"] = "retried via generate mode"
                        prev_output = out
                        patched = True
            elif entry.get("output"):
                prev_output = entry["output"]
        if patched:
            if "final_output" in parsed and trace:
                last_ok = [e for e in trace if e.get("output") and e.get("slot") != "input"]
                if last_ok:
                    parsed["final_output"] = last_ok[-1]["output"]
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # agent_chat: resolve cached responses for inner tool call broadcasting.
    if tool_name == "agent_chat" and isinstance(parsed, dict):
        _cache_id = parsed.get("_cached")
        _full_parsed = parsed
        if _cache_id and call_tool_fn:
            try:
                _cache_resp = await call_tool_fn("get_cached", {"cache_id": str(_cache_id)})
                _cache_data = parse_mcp_result((_cache_resp or {}).get("result"))
                if isinstance(_cache_data, dict) and ("result" in _cache_data or "tool_calls" in _cache_data):
                    _full_parsed = _cache_data
                    print(f"[AGENT-INNER] Resolved cache {_cache_id}")
            except Exception as _ce:
                print(f"[AGENT-INNER] Cache resolve failed for {_cache_id}: {_ce}")

        _inner = _full_parsed.get("result") if isinstance(_full_parsed.get("result"), dict) else _full_parsed
        _inner_tc = _inner.get("tool_calls", []) if isinstance(_inner, dict) else []
        if isinstance(_inner_tc, list) and len(_inner_tc) > 0 and activity_hub:
            for _i, _tc_entry in enumerate(_inner_tc):
                if not isinstance(_tc_entry, dict):
                    continue
                activity_hub.add_entry(
                    tool=_tc_entry.get("tool", "unknown"),
                    args=_tc_entry.get("args", {}),
                    result={"content": [{"type": "text", "text": str(_tc_entry.get("result", ""))}]},
                    duration_ms=0,
                    error=str(_tc_entry.get("error")) if _tc_entry.get("error") else None,
                    source="agent-inner",
                    client_id=None,
                )
                print(f"[AGENT-INNER] Broadcast {_i+1}/{len(_inner_tc)}: {_tc_entry.get('tool')}")

        _result = _full_parsed.get("result") if isinstance(_full_parsed.get("result"), dict) else _full_parsed
        _fa = str(_result.get("final_answer", "")).strip() if isinstance(_result, dict) else ""
        _tc = _result.get("tool_calls", []) if isinstance(_result, dict) else []

        # --- Strip <think>...</think> reasoning blocks from final_answer ---
        import re as _re
        if _fa and "<think>" in _fa:
            _stripped = _re.sub(r"<think>[\s\S]*?</think>\s*", "", _fa).strip()
            if not _stripped and "<think>" in _fa:
                _after_think = _re.split(r"</think>\s*", _fa, maxsplit=1)
                if len(_after_think) > 1:
                    _stripped = _after_think[-1].strip()
            if _stripped:
                _fa = _stripped
                _result["final_answer"] = _fa
                _result["_think_stripped"] = True
            else:
                _fa = ""
                _result["final_answer"] = ""
                _result["_think_stripped"] = True

        # --- Unwrap double-nested JSON in final_answer ---
        if _fa and _fa.startswith("{"):
            try:
                _inner = json.loads(_fa)
                if isinstance(_inner, dict) and "final_answer" in _inner:
                    _fa = str(_inner["final_answer"]).strip()
                    _result["final_answer"] = _fa
                    _result["_unwrapped"] = True
            except (json.JSONDecodeError, ValueError):
                pass

        _empty_markers = (
            "", "model returned an empty response.", "model returned an empty response",
            "no response received", "no response received.",
        )
        if _fa.lower() in _empty_markers and isinstance(_tc, list) and len(_tc) > 0:
            summary_parts = []
            for tc in _tc:
                if not isinstance(tc, dict):
                    continue
                t_name = tc.get("tool", "unknown")
                t_result = tc.get("result", "")
                t_error = tc.get("error")
                if t_error:
                    summary_parts.append(f"[{t_name}] ERROR: {t_error}")
                elif t_result:
                    preview = str(t_result)[:600]
                    if len(str(t_result)) > 600:
                        preview += "..."
                    summary_parts.append(f"[{t_name}] {preview}")
            if summary_parts:
                synthesized = "Tool results (model failed to synthesize):\n\n" + "\n\n".join(summary_parts)
                _result["final_answer"] = synthesized
                _result["_synthesized"] = True
                if "result" in parsed and isinstance(parsed["result"], dict):
                    parsed["result"] = _result
                else:
                    parsed = _result
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # chat: retry via invoke_slot when chat returns empty response.
    if tool_name == "chat" and isinstance(parsed, dict):
        _response = str(parsed.get("response", "")).strip()
        if not _response and args.get("message"):
            _slot = args.get("slot", 0)
            try:
                retry = await call_tool_fn(
                    "invoke_slot",
                    {
                        "slot": int(_slot),
                        "text": str(args["message"]),
                        "mode": "generate",
                        "max_tokens": 512,
                    },
                )
                retry_parsed = parse_mcp_result(retry.get("result"))
                if isinstance(retry_parsed, dict):
                    _output = retry_parsed.get("output", "")
                    if _output:
                        parsed["response"] = _output
                        parsed["_fallback"] = "invoke_slot_generate"
                        return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

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

    # --- Fix invoke_slot/generate: strip <think> blocks ---
    if tool_name in ("invoke_slot", "generate") and isinstance(parsed, dict):
        import re as _re_gen
        _out = str(parsed.get("output", "")).strip()
        if _out and "<think>" in _out:
            _clean = _re_gen.sub(r"<think>[\s\S]*?</think>\s*", "", _out).strip()
            if not _clean:
                _after = _re_gen.split(r"</think>\s*", _out, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean:
                parsed["output"] = _clean
                parsed["_think_stripped"] = True
                return _return_parsed(parsed)

    # --- Fix chat: strip <think> blocks, retry empty ---
    if tool_name == "chat" and isinstance(parsed, dict):
        _response = str(parsed.get("response", "")).strip()
        if _response and "<think>" in _response:
            import re as _re_chat
            _clean = _re_chat.sub(r"<think>[\s\S]*?</think>\s*", "", _response).strip()
            if not _clean:
                _after = _re_chat.split(r"</think>\s*", _response, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean:
                parsed["response"] = _clean
                return _return_parsed(parsed)
            else:
                _response = ""
        if not _response and args.get("message"):
            _slot = args.get("slot", 0)
            try:
                retry = await call_tool_fn("invoke_slot", {
                    "slot": int(_slot), "text": str(args["message"]),
                    "mode": "generate", "max_tokens": 512,
                })
                retry_parsed = parse_mcp_result(retry.get("result"))
                if isinstance(retry_parsed, dict):
                    _out = retry_parsed.get("output", "")
                    if _out:
                        parsed["response"] = _out
                        parsed["_fallback"] = "invoke_slot_generate"
                        return _return_parsed(parsed)
            except Exception:
                pass

    return result
