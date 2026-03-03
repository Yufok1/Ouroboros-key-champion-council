from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit, unquote


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


def _normalize_remote_provider_model_id(model_id: str) -> tuple[str, bool]:
    if not isinstance(model_id, str):
        return model_id, False

    raw = model_id.strip()
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return model_id, False

    try:
        parts = urlsplit(raw)
    except Exception:
        return model_id, False

    changed = False
    path = parts.path or ""
    path_no_slash = path.rstrip("/")
    if path_no_slash.endswith("/v1"):
        path = path_no_slash[:-3]
        changed = True
    elif path_no_slash != path:
        path = path_no_slash
        changed = True

    query = parts.query or ""
    if query:
        tokens: list[str] = []
        for token in query.split("&"):
            if not token:
                continue
            if "=" in token:
                key, value = token.split("=", 1)
            else:
                key, value = token, ""

            if key in ("model", "key"):
                decoded = unquote(value)
                if decoded != value:
                    changed = True
                decoded = decoded.replace("&", "%26").replace("=", "%3D")
                token = f"{key}={decoded}"

            tokens.append(token)

        new_query = "&".join(tokens)
        if new_query != query:
            changed = True
    else:
        new_query = query

    rebuilt = urlunsplit((parts.scheme, parts.netloc, path, new_query, parts.fragment))
    if rebuilt != raw:
        changed = True

    return rebuilt, changed


_DOC_KEY_PREFIX = "__docv2__"
_DOC_KEY_SUFFIX = "__k"


def _doc_escape_key(value: str) -> str:
    return str(value).replace("~", "~~").replace("/", "~s")


def _doc_unescape_key(value: str) -> str:
    s = str(value)
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "~" and i + 1 < n:
            nxt = s[i + 1]
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


def _doc_is_encoded_key(key: str) -> bool:
    return isinstance(key, str) and key.startswith(_DOC_KEY_PREFIX)


def _doc_should_virtualize_key(key: str) -> bool:
    if not isinstance(key, str) or not key:
        return False
    if key.startswith("bag_checkpoint:"):
        return False
    if _doc_is_encoded_key(key):
        return True
    return "/" in key


def _doc_encode_exact_key(key: str) -> str:
    if _doc_is_encoded_key(key):
        return key
    return f"{_DOC_KEY_PREFIX}{_doc_escape_key(key)}{_DOC_KEY_SUFFIX}"


def _doc_encode_prefix(prefix: str) -> str:
    if _doc_is_encoded_key(prefix):
        return prefix
    return f"{_DOC_KEY_PREFIX}{_doc_escape_key(prefix)}"


def _doc_decode_key(key: str) -> str:
    if not _doc_is_encoded_key(key):
        return key
    body = key[len(_DOC_KEY_PREFIX):]
    if body.endswith(_DOC_KEY_SUFFIX):
        body = body[:-len(_DOC_KEY_SUFFIX)]
    return _doc_unescape_key(body)


def _doc_encode_checkpoint_key(checkpoint_key: str) -> str:
    if not isinstance(checkpoint_key, str) or not checkpoint_key.startswith("bag_checkpoint:"):
        return checkpoint_key
    try:
        left, ts = checkpoint_key.rsplit(":", 1)
        src = left[len("bag_checkpoint:"):]
        if _doc_should_virtualize_key(src):
            src = _doc_encode_exact_key(_doc_decode_key(src) if _doc_is_encoded_key(src) else src)
        return f"bag_checkpoint:{src}:{ts}"
    except Exception:
        return checkpoint_key


def _normalize_tool_arguments_for_proxy(tool_name: str | None, args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {}

    patched = dict(args)

    if isinstance(tool_name, str) and tool_name.startswith("file_"):
        if "path" not in patched and isinstance(patched.get("key"), str):
            patched["path"] = patched.get("key")
        if "source_path" not in patched and isinstance(patched.get("source"), str):
            patched["source_path"] = patched.get("source")
        if "dest_path" not in patched and isinstance(patched.get("destination"), str):
            patched["dest_path"] = patched.get("destination")
        if tool_name == "file_write" and "content" not in patched and "value" in patched:
            patched["content"] = patched.get("value")

    if tool_name == "plug_model" and isinstance(patched.get("model_id"), str):
        normalized, changed = _normalize_remote_provider_model_id(patched.get("model_id"))
        if changed:
            patched["model_id"] = normalized

    if tool_name in ("bag_get", "bag_put", "bag_read_doc", "bag_checkpoint", "bag_versions", "bag_restore", "bag_diff", "bag_induct"):
        k = patched.get("key")
        if _doc_should_virtualize_key(k):
            patched["key"] = _doc_encode_exact_key(_doc_decode_key(k) if _doc_is_encoded_key(k) else k)

    if tool_name in ("bag_list_docs", "bag_search_docs", "bag_tree"):
        pfx = patched.get("prefix")
        if isinstance(pfx, str) and pfx and _doc_should_virtualize_key(pfx):
            patched["prefix"] = _doc_encode_prefix(_doc_decode_key(pfx) if _doc_is_encoded_key(pfx) else pfx)

    if tool_name in (
        "file_read", "file_write", "file_edit", "file_append", "file_prepend", "file_delete",
        "file_rename", "file_copy", "file_info", "file_checkpoint", "file_versions", "file_diff", "file_restore"
    ):
        for kf in ("key", "path", "old_path", "new_path", "source_path", "dest_path", "source", "destination"):
            kv = patched.get(kf)
            if isinstance(kv, str) and kv and _doc_should_virtualize_key(kv):
                patched[kf] = _doc_encode_exact_key(_doc_decode_key(kv) if _doc_is_encoded_key(kv) else kv)

    if tool_name in ("file_list", "file_tree", "file_search"):
        pfx = patched.get("path")
        if not isinstance(pfx, str) or not pfx:
            pfx = patched.get("prefix")
        if isinstance(pfx, str) and pfx and _doc_should_virtualize_key(pfx):
            patched["path"] = _doc_encode_prefix(_doc_decode_key(pfx) if _doc_is_encoded_key(pfx) else pfx)

    if tool_name == "bag_forget":
        k = patched.get("key")
        pat = patched.get("pattern")
        if isinstance(k, str) and k and not pat and _doc_should_virtualize_key(k):
            patched["key"] = _doc_encode_exact_key(_doc_decode_key(k) if _doc_is_encoded_key(k) else k)
        if isinstance(pat, str) and pat and _doc_should_virtualize_key(pat):
            patched["pattern"] = _doc_encode_prefix(_doc_decode_key(pat) if _doc_is_encoded_key(pat) else pat)

    if tool_name == "bag_restore" and isinstance(patched.get("checkpoint_key"), str):
        patched["checkpoint_key"] = _doc_encode_checkpoint_key(patched["checkpoint_key"])

    if tool_name == "file_restore" and isinstance(patched.get("checkpoint_key"), str):
        patched["checkpoint_key"] = _doc_encode_checkpoint_key(patched["checkpoint_key"])

    if tool_name in ("file_diff",):
        if isinstance(patched.get("from_checkpoint"), str) and patched.get("from_checkpoint"):
            patched["from_checkpoint"] = _doc_encode_checkpoint_key(patched["from_checkpoint"])
        if isinstance(patched.get("to_checkpoint"), str) and patched.get("to_checkpoint") not in ("", "current"):
            patched["to_checkpoint"] = _doc_encode_checkpoint_key(patched["to_checkpoint"])

    return patched


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
        raw_args = params.get("arguments")
        coerced = _coerce_tool_arguments(raw_args)
        if coerced != raw_args:
            params["arguments"] = coerced
            changed = True

    tool_name = params.get("name")
    if isinstance(params.get("arguments"), dict):
        normalized_args = _normalize_tool_arguments_for_proxy(tool_name, params.get("arguments"))
        if normalized_args != params.get("arguments"):
            params["arguments"] = normalized_args
            changed = True

    # For strict no-arg tools, omit empty arguments object.
    if "arguments" in params and isinstance(params.get("arguments"), dict) and not params.get("arguments"):
        params.pop("arguments", None)
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
    if isinstance(tool_name, str) and isinstance(args, dict):
        args = _normalize_tool_arguments_for_proxy(tool_name, args)
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
