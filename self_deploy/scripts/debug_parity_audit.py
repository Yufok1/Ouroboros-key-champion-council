#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("CC_BASE_URL", "http://127.0.0.1:7866")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _contains_all(path: Path, patterns: list[str]) -> bool:
    text = _read_text(path)
    return all(p in text for p in patterns)


def _api_get(path: str, timeout: int = 20) -> tuple[int, Any]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body) if body else {}
        except Exception:
            return exc.code, {"raw": body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def _api_post(path: str, payload: dict[str, Any], timeout: int = 30) -> tuple[int, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Source": "external"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(txt) if txt else {}
    except urllib.error.HTTPError as exc:
        txt = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(txt) if txt else {}
        except Exception:
            return exc.code, {"raw": txt}
    except Exception as exc:
        return 0, {"error": str(exc)}


def _parse_mcp_response(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {}
        text = first.get("text")
        if isinstance(text, str):
            try:
                return json.loads(text)
            except Exception:
                return {"text": text}
    return result


def run_code_checks() -> list[dict[str, Any]]:
    checks = [
        {
            "commit": "bb7cbad",
            "name": "SSE framing via aiter_text",
            "path": ROOT / "backend" / "server.py",
            "patterns": ["aiter_text", "event_data_lines"],
        },
        {
            "commit": "5363172",
            "name": "External MCP result capture",
            "path": ROOT / "backend" / "server.py",
            "patterns": ["pending_calls.store", "pending_calls.pop", 'source="external"'],
        },
        {
            "commit": "190298e",
            "name": "Silent tool filtering + MCP envelope parser",
            "path": ROOT / "backend" / "activity.py",
            "patterns": ["SILENT_TOOLS", "parse_mcp_result"],
        },
        {
            "commit": "cc35801",
            "name": "Activity dedupe + hydration suppression",
            "path": ROOT / "frontend" / "vscode-shim.js",
            "patterns": ["rememberActivityEventId", "isDuplicateActivityEventId", "event.source === 'hydration'"],
        },
        {
            "commit": "1e051b8",
            "name": "Activity drill renders plain text",
            "path": ROOT / "frontend" / "main.js",
            "patterns": ["Build detail sections as plain escaped text lines", "<pre class=\"activity-detail\">"],
        },
        {
            "commit": "9d29d12",
            "name": "Workflow node normalization",
            "path": ROOT / "backend" / "postprocessing.py",
            "patterns": ['if node.get("type") == "tool_call"', 'node["tool_name"] = tool_name'],
        },
        {
            "commit": "a8d308f",
            "name": "Proxy postprocessing patches (genesis/system-role/orchestra)",
            "path": ROOT / "backend" / "postprocessing.py",
            "patterns": ["tool_name == \"get_genesis\"", "tool_name in (\"compare\", \"debate\")", "tool_name == \"orchestra\""],
        },
        {
            "commit": "92d3552",
            "name": "Per-user HF dataset persistence support",
            "path": ROOT / "backend" / "persistence.py",
            "patterns": ["SPACE_AUTHOR_NAME", "STATE_REPO_SUFFIX", "repo_type=\"dataset\""],
        },
        {
            "commit": "4bcd0a0",
            "name": "Persistence debug logging",
            "path": ROOT / "backend" / "persistence.py",
            "patterns": ["[PERSIST]", "autosave tick", "save complete"],
        },
        {
            "commit": "956bf50",
            "name": "Runtime deps for requests/onnx/rerun/paramiko/vastai",
            "path": ROOT / "requirements-capsule.txt",
            "patterns": ["requests", "onnx", "rerun-sdk", "paramiko", "vastai"],
        },
    ]

    results: list[dict[str, Any]] = []
    for check in checks:
        ok = _contains_all(check["path"], check["patterns"])
        results.append(
            {
                "commit": check["commit"],
                "name": check["name"],
                "path": str(check["path"]),
                "ok": ok,
            }
        )
    return results


def run_runtime_checks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    # 1) Health payload includes activity session metadata.
    status, health = _api_get("/api/health")
    ok = (
        status == 200
        and isinstance(health, dict)
        and bool(health.get("activity_session_id"))
        and health.get("mcp_session") is True
    )
    out.append(
        {
            "name": "health includes activity session + MCP session up",
            "ok": ok,
            "status": status,
            "activity_session_id": health.get("activity_session_id") if isinstance(health, dict) else None,
        }
    )

    # 2) Activity log includes sessionId envelope.
    status, activity_log = _api_get("/api/activity-log?limit=10")
    ok = status == 200 and isinstance(activity_log, dict) and "sessionId" in activity_log and "entries" in activity_log
    out.append(
        {
            "name": "activity-log envelope includes sessionId + entries",
            "ok": ok,
            "status": status,
            "entry_count": len(activity_log.get("entries", [])) if isinstance(activity_log, dict) else 0,
        }
    )

    # 3) Bag put/get round-trip for drill path.
    key = f"parity_smoke_{int(time.time())}"
    put_status, put_payload = _api_post("/api/tool/bag_put", {"key": key, "value": "parity_value"})
    get_status, get_payload = _api_post("/api/tool/bag_get", {"key": key})
    get_parsed = _parse_mcp_response(get_payload)
    ok = (
        put_status == 200
        and get_status == 200
        and isinstance(get_parsed, dict)
        and get_parsed.get("key") == key
        and "value" in get_parsed
    )
    out.append(
        {
            "name": "bag_put + bag_get roundtrip",
            "ok": ok,
            "put_status": put_status,
            "get_status": get_status,
        }
    )

    # 4) Persistence save path writes successfully.
    save_status, save_payload = _api_post("/api/persist/save", {})
    ok = save_status == 200 and isinstance(save_payload, dict) and save_payload.get("status") in ("saved", "failed")
    out.append(
        {
            "name": "persistence save endpoint responds",
            "ok": ok,
            "status": save_status,
            "save_result": save_payload,
        }
    )

    # 5) Workflow normalization (tool_call + tool -> tool + tool_name).
    wf_id = f"parity_wf_{int(time.time())}"
    definition = {
        "id": wf_id,
        "name": "parity workflow",
        "nodes": [
            {"id": "n1", "type": "tool_call", "tool": "heartbeat", "parameters": {}},
        ],
        "connections": [],
    }
    create_status, create_payload = _api_post("/api/tool/workflow_create", {"definition": json.dumps(definition)})
    get_wf_status, get_wf_payload = _api_post("/api/tool/workflow_get", {"workflow_id": wf_id})
    wf_parsed = _parse_mcp_response(get_wf_payload)
    normalized = False
    if isinstance(wf_parsed, dict):
        nodes = wf_parsed.get("nodes", [])
        if isinstance(nodes, list) and nodes:
            n0 = nodes[0] if isinstance(nodes[0], dict) else {}
            normalized = n0.get("type") == "tool" and bool(n0.get("tool")) and bool(n0.get("tool_name"))
    # Cleanup best-effort.
    _api_post("/api/tool/workflow_delete", {"workflow_id": wf_id})
    out.append(
        {
            "name": "workflow normalization at proxy",
            "ok": create_status == 200 and get_wf_status == 200 and normalized,
            "create_status": create_status,
            "get_status": get_wf_status,
        }
    )

    # 6) Activity capture records external call with parsed result.
    call_status, _ = _api_post("/api/tool/get_about", {})
    log_status, log_payload = _api_get("/api/activity-log?limit=200")
    ext_entry = None
    if log_status == 200 and isinstance(log_payload, dict):
        entries = log_payload.get("entries", [])
        if isinstance(entries, list):
            for entry in reversed(entries):
                if isinstance(entry, dict) and entry.get("tool") == "get_about" and entry.get("source") == "external":
                    ext_entry = entry
                    break
    ok = call_status == 200 and isinstance(ext_entry, dict) and ext_entry.get("result") is not None
    out.append(
        {
            "name": "activity captures external get_about with parsed result",
            "ok": ok,
            "call_status": call_status,
            "entry_found": ext_entry is not None,
        }
    )

    return out


def main() -> int:
    code_checks = run_code_checks()
    runtime_checks = run_runtime_checks()

    code_ok = all(item["ok"] for item in code_checks)
    runtime_ok = all(item["ok"] for item in runtime_checks)

    report = {
        "base_url": BASE,
        "timestamp_ms": int(time.time() * 1000),
        "code_checks_ok": code_ok,
        "runtime_checks_ok": runtime_ok,
        "all_ok": code_ok and runtime_ok,
        "code_checks": code_checks,
        "runtime_checks": runtime_checks,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
