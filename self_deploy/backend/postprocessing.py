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

    # Resolve cached stubs for multi-slot tools before retry patching.
    _CACHE_RESOLVE_TOOLS = ("broadcast", "all_slots", "debate", "compare", "pipe", "chain")
    if tool_name in _CACHE_RESOLVE_TOOLS and isinstance(parsed, dict) and parsed.get("_cached"):
        try:
            _cr = await call_tool_fn("get_cached", {"cache_id": str(parsed["_cached"])})
            _cr_parsed = parse_mcp_result((_cr or {}).get("result"))
            if isinstance(_cr_parsed, dict):
                parsed = _cr_parsed
                result = {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
        except Exception:
            pass

    def _doc_decode_key(key: str) -> str:
        prefix = "__docv2__"
        suffix = "__k"
        if not isinstance(key, str) or not key.startswith(prefix):
            return key
        body = key[len(prefix):]
        if body.endswith(suffix):
            body = body[:-len(suffix)]
        out = []
        i = 0
        n = len(body)
        while i < n:
            ch = body[i]
            if ch == "~" and i + 1 < n:
                nxt = body[i + 1]
                if nxt == "~":
                    out.append("~")
                    i += 2
                    continue
                if nxt == "s":
                    out.append("/")
                    i += 2
                    continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _doc_decode_checkpoint_key(checkpoint_key: str) -> str:
        if not isinstance(checkpoint_key, str) or not checkpoint_key.startswith("bag_checkpoint:"):
            return checkpoint_key
        try:
            left, ts = checkpoint_key.rsplit(":", 1)
            src = left[len("bag_checkpoint:"):]
            return f"bag_checkpoint:{_doc_decode_key(src)}:{ts}"
        except Exception:
            return checkpoint_key

    def _decode_doc_in_text(value: str) -> str:
        import re as _re_doc
        if not isinstance(value, str) or "__docv2__" not in value:
            return value

        def _repl(m):
            token = m.group(0)
            return _doc_decode_key(token)

        return _re_doc.sub(r"__docv2__[^\s\",'}]+(?:__k)?", _repl, value)

    def _decode_doc_fields(obj):
        if isinstance(obj, dict):
            for key_field in ("key", "source_key", "restored_key", "pattern", "removed", "path", "old_path", "new_path", "source_path", "dest_path", "restored_path"):
                if isinstance(obj.get(key_field), str):
                    obj[key_field] = _doc_decode_key(obj[key_field])
            for ck_field in ("checkpoint_key", "from_checkpoint", "to_checkpoint", "to_target", "backup_checkpoint"):
                if isinstance(obj.get(ck_field), str):
                    obj[ck_field] = _doc_decode_checkpoint_key(obj[ck_field])
            if isinstance(obj.get("available"), list):
                obj["available"] = [(_doc_decode_key(v) if isinstance(v, str) else v) for v in obj["available"]]
            if isinstance(obj.get("error"), str):
                obj["error"] = _decode_doc_in_text(obj["error"])
            for v in list(obj.values()):
                _decode_doc_fields(v)
        elif isinstance(obj, list):
            for item in obj:
                _decode_doc_fields(item)

    if (tool_name.startswith("bag_") or tool_name.startswith("file_")) and isinstance(parsed, (dict, list)):
        _decode_doc_fields(parsed)
        result = {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # file_write checkpoint contract normalization:
    # - checkpoint_key returned by write is a pre-write backup snapshot
    # - add backup_checkpoint explicitly
    # - promote checkpoint_key to a post-write snapshot for deterministic diff flows
    if tool_name == "file_write" and isinstance(parsed, dict):
        _path = str(args.get("path") or parsed.get("path") or parsed.get("key") or "").strip()
        _auto_ck = str(parsed.get("checkpoint_key") or "").strip()
        if _path and _auto_ck and bool(parsed.get("replaced")) and call_tool_fn:
            parsed["backup_checkpoint"] = _auto_ck
            parsed["backup_checkpoint_semantics"] = "pre_write_backup"
            try:
                _post_ck_raw = await call_tool_fn("file_checkpoint", {"path": _path, "message": "auto post-write snapshot"})
                _post_ck = parse_mcp_result((_post_ck_raw or {}).get("result"))
                if isinstance(_post_ck, dict) and isinstance(_post_ck.get("checkpoint_key"), str):
                    _post_key_raw = str(_post_ck.get("checkpoint_key") or "").strip()
                    _post_key = _doc_decode_checkpoint_key(_post_key_raw) if _post_key_raw else ""
                    if _post_key:
                        parsed["checkpoint_key"] = _post_key
                        parsed["post_write_checkpoint"] = _post_key
                        parsed["checkpoint_semantics"] = "post_write_snapshot"
                        note = str(parsed.get("note") or "").strip()
                        extra = "checkpoint_key is post-write; backup_checkpoint is pre-write state"
                        parsed["note"] = (note + "; " + extra) if note else extra
                        return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                parsed["checkpoint_semantics"] = "pre_write_backup"
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    # C5 fix: also trigger for non-empty prefix (scoped subtrees), not just root.
    if tool_name in ("bag_tree", "file_tree") and isinstance(parsed, dict):
        tree = parsed.get("tree")
        doc_count = int(parsed.get("document_count", 0) or 0)
        req_prefix = str(args.get("prefix", args.get("path", "")) or "")
        if (not isinstance(tree, dict) or not tree) and doc_count == 0:
            try:
                ls_args = {
                    "prefix": "",
                    "include_checkpoints": bool(args.get("include_checkpoints", False)),
                    "limit": 500,
                }
                ls_raw = await call_tool_fn("bag_list_docs", ls_args)
                ls_parsed = parse_mcp_result((ls_raw or {}).get("result"))
                if isinstance(ls_parsed, dict) and ls_parsed.get("_cached"):
                    _ls_cache = await call_tool_fn("get_cached", {"cache_id": str(ls_parsed.get("_cached"))})
                    _ls_cache_parsed = parse_mcp_result((_ls_cache or {}).get("result"))
                    if isinstance(_ls_cache_parsed, dict):
                        ls_parsed = _ls_cache_parsed
                items = ls_parsed.get("items", []) if isinstance(ls_parsed, dict) else []
                # C5 fix: filter items to prefix BEFORE building tree
                _pfx_norm = req_prefix.strip("/") + "/" if req_prefix.strip("/") else ""
                matching_items = []
                built = {}
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    k = _doc_decode_key(str(it.get("key", "") or ""))
                    if not k:
                        continue
                    if _pfx_norm and not k.startswith(_pfx_norm) and k != req_prefix.strip("/"):
                        continue
                    matching_items.append(k)
                    rel_key = k[len(_pfx_norm):] if _pfx_norm else k
                    parts = [p for p in rel_key.split("/") if p]
                    if not parts:
                        continue
                    cur = built
                    for idx, part in enumerate(parts):
                        if part not in cur:
                            cur[part] = {}
                        node = cur[part]
                        if idx == len(parts) - 1:
                            node.setdefault("_items", [])
                            node["_items"].append(k)
                        cur = node
                parsed["tree"] = built
                parsed["document_count"] = len(matching_items)
                parsed["prefix"] = req_prefix
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

    # Normalize slot payloads and clear stale unloaded metadata.
    def _normalize_unplugged_slot_fields(slot_obj: dict):
        try:
            idx = int(slot_obj.get("index", slot_obj.get("slot", 0)))
        except Exception:
            idx = 0
        slot_obj["plugged"] = False
        slot_obj["name"] = f"slot_{idx}"
        slot_obj["model_source"] = None
        slot_obj["source"] = None
        slot_obj["model"] = None
        slot_obj["status"] = "empty"
        slot_obj["model_type"] = None
        slot_obj["type"] = None

    if tool_name == "slot_info" and isinstance(parsed, dict):
        if not bool(parsed.get("plugged")):
            _normalize_unplugged_slot_fields(parsed)
            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

    if tool_name in ("list_slots", "council_status") and isinstance(parsed, dict):
        slots = parsed.get("slots")
        all_ids = parsed.get("all_ids")
        total = parsed.get("total")

        if isinstance(slots, list) and len(slots) > 0:
            normalized_slots = []
            for i, raw_slot in enumerate(slots):
                slot = dict(raw_slot) if isinstance(raw_slot, dict) else {}
                try:
                    idx = int(slot.get("index", i))
                except Exception:
                    idx = i
                slot["index"] = idx

                is_plugged = bool(slot.get("plugged"))
                if is_plugged:
                    src = slot.get("model_source") or slot.get("source")
                    if not src and not _is_default_slot_name(slot.get("name", "")):
                        src = slot.get("name")
                    slot["model_source"] = src
                    if slot.get("status") in (None, "", "empty"):
                        slot["status"] = "plugged"
                else:
                    _normalize_unplugged_slot_fields(slot)

                normalized_slots.append(slot)

            parsed["slots"] = normalized_slots
            parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(normalized_slots)]
            parsed["total"] = len(normalized_slots)

            try:
                plugged_sum = sum(1 for s in normalized_slots if bool(s.get("plugged")))
                stats = parsed.get("stats") if isinstance(parsed.get("stats"), dict) else {}
                pstats = stats.get("plugged") if isinstance(stats.get("plugged"), dict) else {}
                pstats["sum"] = plugged_sum
                pstats["min"] = False
                pstats["max"] = True if plugged_sum > 0 else False
                pstats["avg"] = round(plugged_sum / max(1, len(normalized_slots)), 2)
                stats["plugged"] = pstats
                parsed["stats"] = stats
            except Exception:
                pass

            return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

        # Compact list_slots shape from some external MCP paths (no explicit slots[])
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
                    for s in enriched_slots:
                        _normalize_unplugged_slot_fields(s)
                    parsed["slots"] = enriched_slots
                    parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(enriched_slots)]
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

            for s in enriched_slots:
                if not bool(s.get("plugged")):
                    _normalize_unplugged_slot_fields(s)

            parsed["slots"] = enriched_slots
            parsed["all_ids"] = [str(s.get("name", f"slot_{i}")) for i, s in enumerate(enriched_slots)]
            parsed["total"] = len(enriched_slots)
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
        """Robust generation retry for flaky providers."""
        prompts = [
            text,
            (text + "\n\nRespond with a concise direct answer."),
            ("Answer briefly and directly:\n" + text),
        ]
        token_budgets = [max_tokens, max(max_tokens, 512), max(max_tokens, 768)]

        for p in prompts:
            for mt in token_budgets:
                try:
                    retry = await call_tool_fn("invoke_slot", {
                        "slot": int(slot_idx), "text": p, "mode": "generate", "max_tokens": int(mt),
                    })
                    retry_parsed = parse_mcp_result(retry.get("result"))
                    if isinstance(retry_parsed, dict):
                        out = str(retry_parsed.get("output", "") or "").strip()
                        if out:
                            if out.lower().startswith("[remote provider error"):
                                continue
                            if "<think>" in out:
                                import re as _re_try
                                cleaned = _re_try.sub(r"<think>[\s\S]*?</think>\s*", "", out).strip()
                                if cleaned:
                                    out = cleaned
                                else:
                                    continue
                            if out:
                                return out
                except Exception:
                    pass

        # Fallback through chat path
        try:
            ch = await call_tool_fn("chat", {"slot": int(slot_idx), "message": text})
            ch_parsed = parse_mcp_result(ch.get("result"))
            if isinstance(ch_parsed, dict):
                out = str(ch_parsed.get("response", "") or "").strip()
                if out:
                    if out.lower().startswith("[remote provider error"):
                        return None
                    return out
        except Exception:
            pass

        return None

    def _is_retryable_provider_output(text: str) -> bool:
        s = str(text or "").strip()
        if not s:
            return True
        low = s.lower()
        if low.startswith("[remote provider error"):
            retry_markers = (
                "http error 500",
                "http error 502",
                "http error 503",
                "http error 504",
                "http error 429",
                "gateway",
                "timeout",
                "temporarily",
            )
            return any(m in low for m in retry_markers)
        return False

    # --- Fix compare: retry failures + reconstruct explicit slot filters when capsule returns [] ---
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

        requested_slots = args.get("slots")
        if isinstance(requested_slots, list) and requested_slots and isinstance(comparisons, list) and len(comparisons) == 0:
            try:
                slots_result = await call_tool_fn("list_slots", {})
                slots_parsed = parse_mcp_result(slots_result.get("result"))
                if isinstance(slots_parsed, dict) and slots_parsed.get("_cached"):
                    _ls_cr = await call_tool_fn("get_cached", {"cache_id": str(slots_parsed["_cached"])})
                    _ls_full = parse_mcp_result((_ls_cr or {}).get("result"))
                    if isinstance(_ls_full, dict):
                        slots_parsed = _ls_full
                slots_list = slots_parsed.get("slots", []) if isinstance(slots_parsed, dict) else []
                slots_by_idx = {}
                slots_by_name = {}
                for s in slots_list:
                    if not isinstance(s, dict):
                        continue
                    try:
                        idx = int(s.get("index", s.get("slot", -1)))
                    except Exception:
                        continue
                    slots_by_idx[idx] = s
                    nm = str(s.get("name") or "").strip().lower()
                    if nm:
                        slots_by_name[nm] = idx

                selected = []
                selected_set = set()
                unresolved = []
                for token in requested_slots:
                    idx = None
                    if isinstance(token, int):
                        idx = token
                    else:
                        raw = str(token).strip()
                        low = raw.lower()
                        if low.lstrip("+-").isdigit():
                            idx = int(low)
                        elif low.startswith("s") and low[1:].isdigit():
                            idx = int(low[1:]) - 1
                        elif low in slots_by_name:
                            idx = slots_by_name[low]
                    if idx is None:
                        unresolved.append(str(token))
                        continue
                    if idx in selected_set:
                        continue
                    selected_set.add(idx)
                    selected.append(idx)

                rebuilt = []
                compare_text = str(args.get("input_text", "") or "")
                for idx in selected:
                    slot_info = slots_by_idx.get(idx, {})
                    slot_name = str(slot_info.get("name") or f"slot_{idx}")
                    if not bool(slot_info.get("plugged")):
                        rebuilt.append({"slot": idx, "name": slot_name, "status": "empty"})
                        continue
                    out = await _retry_slot_generate(idx, compare_text)
                    if out:
                        rebuilt.append({
                            "slot": idx,
                            "name": slot_name,
                            "status": "ok",
                            "type": "generation",
                            "output": out,
                            "note": "rebuilt via proxy slot-filter fallback",
                        })
                    else:
                        rebuilt.append({
                            "slot": idx,
                            "name": slot_name,
                            "status": "error",
                            "error": "No output from slot during proxy slot-filter fallback",
                        })

                for token in unresolved:
                    rebuilt.append({
                        "selector": token,
                        "status": "error",
                        "error": "Slot selector did not match any slot",
                    })

                parsed["comparisons"] = rebuilt
                parsed["note"] = "compare slot-filter fallback applied"
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}
            except Exception:
                pass

    # trace_root_causes can miss existing causal links; bridge from cascade_graph for event ids.
    if tool_name == "trace_root_causes" and isinstance(parsed, dict):
        event_desc = str(args.get("event_description") or parsed.get("event") or "").strip()
        root_causes = parsed.get("root_causes")
        no_prior = isinstance(root_causes, list) and any("no prior events to trace" in str(rc).lower() for rc in root_causes)
        if no_prior and event_desc.startswith("evt_"):
            try:
                cg_raw = await call_tool_fn(
                    "cascade_graph",
                    {"operation": "get_causes", "params": json.dumps({"event_id": event_desc})},
                )
                cg_parsed = parse_mcp_result((cg_raw or {}).get("result"))
                cg_causes = cg_parsed.get("causes", []) if isinstance(cg_parsed, dict) else []
                if isinstance(cg_causes, list) and cg_causes:
                    normalized = []
                    for cause in cg_causes:
                        if not isinstance(cause, dict):
                            normalized.append(str(cause))
                            continue
                        cid = str(cause.get("event_id", "") or "").strip()
                        comp = str(cause.get("component", "") or "").strip()
                        etype = str(cause.get("event_type", "") or "").strip()
                        line = "cascade_graph"
                        if comp:
                            line += f":{comp}"
                        if etype:
                            line += f":{etype}"
                        if cid:
                            line += f":{cid}"
                        normalized.append(line)
                    parsed["root_causes"] = normalized
                    parsed["root_causes_structured"] = cg_causes
                    parsed["trace_depth"] = max(1, len(cg_causes))
                    parsed["_bridge"] = {"source": "cascade_graph.get_causes", "event_id": event_desc, "cause_count": len(cg_causes)}
                    return _return_parsed(parsed)
            except Exception:
                pass

    # cascade_data pii_scan can overmatch decimal metrics as PHONE_NUMBER; filter deterministically.
    if tool_name == "cascade_data" and isinstance(parsed, dict):
        op = str(args.get("operation", "") or "").strip().lower()
        if op == "pii_scan":
            hits = parsed.get("pii_found")
            if isinstance(hits, list) and hits:
                import re as _re_pii

                params_raw = args.get("params")
                params_text = ""
                try:
                    if isinstance(params_raw, str):
                        pj = json.loads(params_raw)
                        if isinstance(pj, dict):
                            params_text = str(pj.get("text") or pj.get("data") or pj.get("input") or params_raw)
                        else:
                            params_text = params_raw
                    elif isinstance(params_raw, dict):
                        params_text = str(params_raw.get("text") or params_raw.get("data") or params_raw.get("input") or "")
                    else:
                        params_text = str(params_raw or "")
                except Exception:
                    params_text = str(params_raw or "")

                metric_context = any(tok in params_text.lower() for tok in ("fitness", "loss", "accuracy", "reward", "score", "rate", "critic"))
                filtered_hits = []
                removed = []
                for hit in hits:
                    if not isinstance(hit, dict):
                        filtered_hits.append(hit)
                        continue
                    htype = str(hit.get("type", "") or "").upper()
                    preview = str(hit.get("value_preview", "") or "").replace(" ", "")
                    if htype == "PHONE_NUMBER":
                        looks_decimal = bool(_re_pii.match(r"^\d+\.\d+\*{0,8}$", preview))
                        lacks_phone_chars = not any(ch in preview for ch in "+()-")
                        if metric_context and looks_decimal and lacks_phone_chars:
                            removed.append({"type": htype, "value_preview": preview, "reason": "decimal_metric_false_positive"})
                            continue
                    filtered_hits.append(hit)

                if removed:
                    parsed["pii_found"] = filtered_hits
                    parsed["count"] = len(filtered_hits)
                    parsed["_false_positive_filtered"] = removed
                    parsed["note"] = "Filtered decimal metric false positives from pii_scan."
                    return _return_parsed(parsed)

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
                        if isinstance(slots_parsed, dict) and slots_parsed.get("_cached"):
                            _ls_cr = await call_tool_fn("get_cached", {"cache_id": str(slots_parsed["_cached"])})
                            slots_parsed = parse_mcp_result((_ls_cr or {}).get("result")) or slots_parsed
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

        # Strict-JSON contract normalization for deterministic debug/eval paths.
        _req_msg = str(args.get("message", "") or "")
        _req_low = _req_msg.lower()
        _strict_json_requested = (
            "strict json" in _req_low
            or "json only" in _req_low
            or "return json" in _req_low
        )
        if _strict_json_requested:
            _fa_obj = _result.get("final_answer") if isinstance(_result.get("final_answer"), (dict, list)) else None
            if _fa_obj is None and isinstance(_fa, str) and _fa:
                _cand = _fa.strip()
                _m = _re.search(r"```(?:json)?\s*([\s\S]*?)```", _cand, flags=_re.IGNORECASE)
                if _m:
                    _cand = _m.group(1).strip()
                try:
                    _parsed_json = json.loads(_cand)
                    if isinstance(_parsed_json, (dict, list)):
                        _fa_obj = _parsed_json
                except Exception:
                    _fa_obj = None

            if _fa_obj is not None:
                if not isinstance(_result.get("final_answer"), (dict, list)):
                    _result["final_answer"] = _fa_obj
                    _result["_strict_json_normalized"] = True
                    _fa = json.dumps(_fa_obj)
            else:
                _result["contract_violation"] = {
                    "type": "strict_json_not_returned",
                    "expected": "json",
                    "received": "text",
                }
                _result["final_answer_raw"] = _fa
                _result["final_answer"] = {
                    "status": "contract_violation",
                    "violation": "strict_json_not_returned",
                    "tool_calls": len(_tc) if isinstance(_tc, list) else 0,
                }
                if "result" in parsed and isinstance(parsed["result"], dict):
                    parsed["result"] = _result
                else:
                    parsed = _result
                return {"result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}

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

    # --- Fix invoke_slot/generate: strip <think> blocks + retry transient provider failures ---
    if tool_name in ("invoke_slot", "generate") and isinstance(parsed, dict):
        import re as _re_gen
        _out = str(parsed.get("output", "")).strip()
        if _out and "<think>" in _out:
            _clean = _re_gen.sub(r"<think>[\s\S]*?</think>\s*", "", _out).strip()
            if not _clean:
                _after = _re_gen.split(r"</think>\s*", _out, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean and not _clean.lower().startswith("[remote provider error"):
                parsed["output"] = _clean
                parsed["_think_stripped"] = True
                _out = _clean
            elif tool_name == "invoke_slot" and args.get("slot") is not None and args.get("text"):
                try:
                    _cf = await call_tool_fn("chat", {"slot": int(args.get("slot", 0)), "message": str(args.get("text", ""))})
                    _cfp = parse_mcp_result(_cf.get("result"))
                    if isinstance(_cfp, dict):
                        _resp = str(_cfp.get("response", "")).strip()
                        if _resp and not _resp.lower().startswith("[remote provider error"):
                            parsed["output"] = _resp
                            parsed["_fallback"] = "chat_after_think_only"
                            _out = _resp
                except Exception:
                    pass

        if tool_name == "invoke_slot" and args.get("slot") is not None and args.get("text") and _is_retryable_provider_output(_out):
            _retry_out = await _retry_slot_generate(int(args.get("slot", 0)), str(args.get("text", "")), max_tokens=max(64, int(args.get("max_tokens", 300) or 300)))
            if _retry_out:
                parsed["output"] = _retry_out
                parsed["_fallback"] = "retry_generate"
                return _return_parsed(parsed)

        if "_think_stripped" in parsed or parsed.get("_fallback"):
            return _return_parsed(parsed)

    # --- Fix chat: strip <think> blocks, retry transient provider/empty ---
    if tool_name == "chat" and isinstance(parsed, dict):
        _chat_changed = False
        _response = str(parsed.get("response", "")).strip()
        if _response and "<think>" in _response:
            import re as _re_chat
            _clean = _re_chat.sub(r"<think>[\s\S]*?</think>\s*", "", _response).strip()
            if not _clean:
                _after = _re_chat.split(r"</think>\s*", _response, maxsplit=1)
                _clean = _after[-1].strip() if len(_after) > 1 else ""
            if _clean:
                parsed["response"] = _clean
                _response = _clean
                _chat_changed = True
            else:
                _response = ""

        if args.get("message") and args.get("slot") is not None and _is_retryable_provider_output(_response):
            _retry_out = await _retry_slot_generate(int(args.get("slot", 0)), str(args.get("message", "")), max_tokens=512)
            if _retry_out:
                parsed["response"] = _retry_out
                parsed["_fallback"] = "invoke_slot_retry"
                _chat_changed = True

        if _chat_changed:
            return _return_parsed(parsed)

    return result
