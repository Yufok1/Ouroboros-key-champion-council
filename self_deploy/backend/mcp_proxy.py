from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class PendingCall:
    tool: str
    args: dict[str, Any]
    start: float
    client_id: str | None = None


class PendingCallRegistry:
    """Track pending external MCP tools/call requests.

    Keyed by (session_id, rpc_id) to avoid collisions when multiple external
    clients reuse small JSON-RPC IDs (e.g. each client starts at id=1).
    """

    def __init__(self):
        self._pending: dict[str, dict[str | int, PendingCall]] = {}

    @staticmethod
    def _session_key(session_id: str | None) -> str:
        return session_id or "__default__"

    @staticmethod
    def _id_candidates(rpc_id: str | int) -> list[str | int]:
        candidates: list[str | int] = [rpc_id]

        sid = str(rpc_id)
        if sid not in candidates:
            candidates.append(sid)

        if isinstance(rpc_id, str) and rpc_id.isdigit():
            iid = int(rpc_id)
            if iid not in candidates:
                candidates.append(iid)

        if isinstance(rpc_id, int):
            sid2 = str(rpc_id)
            if sid2 not in candidates:
                candidates.append(sid2)

        return candidates

    def _pop_from_bucket(
        self,
        bucket: dict[str | int, PendingCall] | None,
        rpc_id: str | int | None,
    ) -> PendingCall | None:
        if bucket is None or rpc_id is None:
            return None

        for candidate in self._id_candidates(rpc_id):
            if candidate in bucket:
                return bucket.pop(candidate)

        return None

    def store(
        self,
        session_id: str | None,
        rpc_id: str | int,
        tool: str,
        args: dict[str, Any],
        start: float,
        client_id: str | None = None,
    ) -> None:
        skey = self._session_key(session_id)
        bucket = self._pending.setdefault(skey, {})
        bucket[rpc_id] = PendingCall(tool=tool, args=args or {}, start=start, client_id=client_id)

    def pop(self, session_id: str | None, rpc_id: str | int | None) -> PendingCall | None:
        if rpc_id is None:
            return None

        skey = self._session_key(session_id)
        bucket = self._pending.get(skey)
        pending = self._pop_from_bucket(bucket, rpc_id)
        if pending:
            if bucket is not None and not bucket:
                self._pending.pop(skey, None)
            return pending

        # Fallback: if session is unknown/missing, try all buckets.
        for other_skey, other_bucket in list(self._pending.items()):
            pending = self._pop_from_bucket(other_bucket, rpc_id)
            if pending:
                if not other_bucket:
                    self._pending.pop(other_skey, None)
                return pending

        return None

    def cleanup(self, stale_after_seconds: int = 300) -> None:
        now = time.time()
        stale_sessions: list[str] = []

        for skey, bucket in self._pending.items():
            stale_ids = [k for k, v in bucket.items() if (now - v.start) > stale_after_seconds]
            for k in stale_ids:
                bucket.pop(k, None)
            if not bucket:
                stale_sessions.append(skey)

        for skey in stale_sessions:
            self._pending.pop(skey, None)

    def has_pending(self, session_id: str | None = None) -> bool:
        if session_id is None:
            return any(bool(bucket) for bucket in self._pending.values())

        skey = self._session_key(session_id)
        return bool(self._pending.get(skey))

    def keys(self) -> list[tuple[str, str | int]]:
        out: list[tuple[str, str | int]] = []
        for skey, bucket in self._pending.items():
            for rpc_id in bucket.keys():
                out.append((skey, rpc_id))
        return out


def _coerce_tool_arguments(args: Any) -> dict[str, Any]:
    """Coerce tool arguments into a JSON object."""
    if isinstance(args, dict):
        return args
    if args is None:
        return {}
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    if isinstance(args, list):
        out: dict[str, Any] = {}
        for item in args:
            if (
                isinstance(item, (list, tuple))
                and len(item) == 2
                and isinstance(item[0], str)
            ):
                out[item[0]] = item[1]
            else:
                return {}
        return out
    return {}


def _normalize_tool_call_obj(obj: dict[str, Any]) -> bool:
    """Normalize one JSON-RPC tools/call object in-place."""
    if not isinstance(obj, dict) or obj.get("method") != "tools/call":
        return False

    changed = False

    params = obj.get("params", {})
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            params = parsed if isinstance(parsed, dict) else {}
        except Exception:
            params = {}
        changed = True
    elif not isinstance(params, dict):
        params = {}
        changed = True

    if not params.get("name"):
        alias = params.get("tool") or params.get("tool_name")
        if isinstance(alias, str) and alias:
            params["name"] = alias
            changed = True

    if "arguments" not in params:
        if isinstance(params.get("input"), dict):
            params["arguments"] = params.pop("input")
            changed = True
        elif isinstance(params.get("args"), dict):
            params["arguments"] = params.pop("args")
            changed = True
        else:
            params["arguments"] = {}
            changed = True
    else:
        coerced = _coerce_tool_arguments(params.get("arguments"))
        if coerced != params.get("arguments"):
            params["arguments"] = coerced
            changed = True

    obj["params"] = params
    return changed


def normalize_rpc_payload(payload_bytes: bytes) -> bytes:
    """Normalize incoming JSON-RPC tools/call payload(s)."""
    try:
        body = json.loads(payload_bytes)
    except Exception:
        return payload_bytes

    changed = False
    if isinstance(body, dict):
        changed = _normalize_tool_call_obj(body)
    elif isinstance(body, list):
        for item in body:
            if isinstance(item, dict) and _normalize_tool_call_obj(item):
                changed = True
    else:
        return payload_bytes

    if changed:
        return json.dumps(body).encode("utf-8")
    return payload_bytes


def _extract_tool_call(obj: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any], str | int | None]:
    method = obj.get("method", "")
    rpc_id = obj.get("id")

    if method != "tools/call":
        return method, None, {}, rpc_id

    params = obj.get("params", {})
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            params = parsed if isinstance(parsed, dict) else {}
        except Exception:
            params = {}
    if not isinstance(params, dict):
        params = {}

    if not params.get("name"):
        alias = params.get("tool") or params.get("tool_name")
        if isinstance(alias, str) and alias:
            params["name"] = alias

    args = _coerce_tool_arguments(params.get("arguments"))
    if not args:
        if isinstance(params.get("input"), dict):
            args = params["input"]
        elif isinstance(params.get("args"), dict):
            args = params["args"]

    tool_name = params.get("name", "unknown")
    return method, tool_name, args, rpc_id


def parse_rpc_tool_call(payload_bytes: bytes) -> tuple[str | None, str | None, dict[str, Any], str | int | None]:
    """Return first tools/call tuple for compatibility with legacy callers."""

    method, calls = parse_rpc_tool_calls(payload_bytes)
    if calls:
        tool, args, rpc_id = calls[0]
        return method, tool, args, rpc_id
    return method, None, {}, None


def parse_rpc_tool_calls(
    payload_bytes: bytes,
) -> tuple[str | None, list[tuple[str, dict[str, Any], str | int | None]]]:
    """Return (method, [(tool_name, tool_args, rpc_id), ...]) from JSON-RPC payload.

    Supports both single JSON-RPC objects and batch arrays.
    """

    try:
        body = json.loads(payload_bytes)

        if isinstance(body, list):
            first_method: str | None = None
            calls: list[tuple[str, dict[str, Any], str | int | None]] = []
            for item in body:
                if not isinstance(item, dict):
                    continue
                method, tool, args, rpc_id = _extract_tool_call(item)
                if first_method is None:
                    first_method = method
                if tool:
                    calls.append((tool, args, rpc_id))
            return first_method, calls

        if isinstance(body, dict):
            method, tool, args, rpc_id = _extract_tool_call(body)
            if tool:
                return method, [(tool, args, rpc_id)]
            return method, []

        return None, []
    except Exception:
        return None, []


def _normalize_workflow_call(obj: dict[str, Any], normalizer) -> bool:
    if not isinstance(obj, dict):
        return False

    if obj.get("method") != "tools/call":
        return False

    params = obj.get("params", {})
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            params = parsed if isinstance(parsed, dict) else {}
        except Exception:
            return False
    if not isinstance(params, dict):
        return False

    tool = params.get("name")
    if tool not in ("workflow_create", "workflow_update"):
        return False

    args = _coerce_tool_arguments(params.get("arguments"))
    if not isinstance(args, dict) or "definition" not in args:
        return False

    args = dict(args)
    args["definition"] = normalizer(args["definition"])

    params = dict(params)
    params["arguments"] = args

    obj["params"] = params
    return True


def normalize_rpc_workflow(payload_bytes: bytes, normalizer) -> bytes:
    """Normalize workflow definition in JSON-RPC tools/call payload(s)."""
    try:
        body = json.loads(payload_bytes)

        changed = False

        if isinstance(body, dict):
            changed = _normalize_workflow_call(body, normalizer)
        elif isinstance(body, list):
            for item in body:
                if _normalize_workflow_call(item, normalizer):
                    changed = True
        else:
            return payload_bytes

        if changed:
            return json.dumps(body).encode("utf-8")

        return payload_bytes
    except Exception:
        return payload_bytes
