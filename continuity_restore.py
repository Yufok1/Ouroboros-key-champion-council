"""
Continuity restoration helpers for local Codex session archives.

Phase 0 scope:
  - discover local `.codex` homes and rollout session logs
  - parse operational continuity from session JSONL archives
  - score sessions against a compaction summary and cwd hint
  - emit a continuity packet plus a lightweight resume-focus bundle
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent
_WINDOWS_PATH_RE = re.compile(r"(?i)\b[a-z]:\\[^\s\"'<>|]+")
_RELATIVE_PATH_RE = re.compile(r"(?:(?:[\w.-]+[\\/])+[\w.-]+\.[A-Za-z0-9]{1,8})")
_FILE_NAME_RE = re.compile(
    r"\b[\w.-]+\.(?:py|js|mjs|cjs|ts|tsx|jsx|json|md|txt|ps1|bat|sh|yml|yaml|toml|ini|cfg|html|css|jpg|jpeg|png|gif|svg|wav|mp3|m4a|sqlite|db|csv)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9_./:-]{3,}")
_JSON_STRING_FIELD_RE = re.compile(r'"(?P<key>[^"]+)":"(?P<value>(?:\\.|[^"])*)"')
_STOPWORDS = {
    "about", "after", "again", "among", "around", "because", "before", "being", "between",
    "build", "built", "could", "dance", "doing", "every", "exactly", "feels", "first",
    "from", "have", "here", "into", "just", "keep", "last", "like", "make", "more",
    "most", "much", "need", "none", "only", "other", "over", "please", "said", "same",
    "should", "some", "state", "still", "surface", "surfaces", "that", "their", "them",
    "then", "there", "these", "thing", "this", "those", "through", "what", "when", "where",
    "which", "while", "with", "would", "your",
}
_SESSION_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}
_SKIP_LINE_BYTES = 20000
_RAW_STATE_GUARDRAIL = (
    "Only open raw shared_state after text theater render, browser-visible corroboration, "
    "consult/blackboard, snapshot, env_help, and any needed scoped report."
)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tokenize(text: Any) -> list[str]:
    raw = str(text or "").strip().lower()
    if not raw:
        return []
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(raw):
        cleaned = token.strip("._/-:")
        if len(cleaned) < 3 or cleaned in _STOPWORDS:
            continue
        tokens.append(cleaned)
    return tokens


def _collect_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(_collect_strings(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(_collect_strings(item))
    return out


def _safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _fast_extract_json_string(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}":"((?:\\.|[^"])*)"', text)
    if not match:
        return ""
    raw = match.group(1)
    return raw.replace("\\\\", "\\").replace('\\"', '"')


def _normalize_line(text: Any, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _dedupe_recent(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in reversed(values):
        clean = _normalize_line(value, limit=400)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return list(reversed(out))


def _extract_file_mentions(value: Any) -> list[str]:
    found: list[str] = []
    for text in _collect_strings(value):
        for match in _WINDOWS_PATH_RE.findall(text):
            found.append(match.rstrip(".,)"))
        for match in _RELATIVE_PATH_RE.findall(text):
            if match.lower().startswith(("http://", "https://")):
                continue
            found.append(match.rstrip(".,)"))
        for match in _FILE_NAME_RE.findall(text):
            found.append(match.rstrip(".,)"))
    ordered: list[str] = []
    seen: set[str] = set()
    for item in found:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _append_tail(session: dict[str, Any], kind: str, text: str = "", meta: dict[str, Any] | None = None, timestamp: str = "") -> None:
    tail = session.setdefault("tail_events", [])
    entry = {"kind": kind}
    if timestamp:
        entry["timestamp"] = timestamp
    if text:
        entry["text"] = _normalize_line(text, limit=220)
    if meta:
        entry["meta"] = meta
    tail.append(entry)
    if len(tail) > 40:
        del tail[:-40]


def _append_tool(session: dict[str, Any], name: str) -> None:
    clean = str(name or "").strip()
    if not clean:
        return
    session.setdefault("tool_names", []).append(clean)


def _append_text(session: dict[str, Any], text: str) -> None:
    clean = _normalize_line(text, limit=1200)
    if clean:
        session.setdefault("search_parts", []).append(clean)


def _append_file_mentions(session: dict[str, Any], file_seen: set[str], value: Any) -> None:
    for mention in _extract_file_mentions(value):
        key = mention.lower()
        if key in file_seen:
            continue
        file_seen.add(key)
        session["file_mentions"].append(mention)


def _home_recent_rollouts(home: Path, limit: int = 6) -> list[Path]:
    sessions_root = home / "sessions"
    if not sessions_root.exists():
        return []
    files = list(sessions_root.rglob("rollout-*.jsonl"))
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return files[:limit]


def _probe_session_cwd(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _ in range(8):
                raw = handle.readline()
                if not raw:
                    break
                try:
                    entry = json.loads(raw)
                except Exception:
                    continue
                payload = entry.get("payload")
                if not isinstance(payload, dict):
                    continue
                cwd = str(payload.get("cwd", "") or "").strip()
                if cwd:
                    return cwd
    except Exception:
        return ""
    return ""


def _rank_codex_home(home: Path, cwd_hint: str = "") -> float:
    score = 0.0
    recent_files = _home_recent_rollouts(home, limit=6)
    if recent_files:
        newest = recent_files[0]
        try:
            newest_mtime = newest.stat().st_mtime
        except Exception:
            newest_mtime = 0.0
        score += newest_mtime / 1000000.0
    cwd_hint_clean = str(cwd_hint or "").strip().lower()
    if cwd_hint_clean:
        cwd_name = Path(cwd_hint_clean).name
        for index, path in enumerate(recent_files):
            session_cwd = _probe_session_cwd(path).lower()
            if not session_cwd:
                continue
            weight = max(1.0, 6.0 - float(index))
            if session_cwd == cwd_hint_clean:
                score += 1000.0 * weight
            elif session_cwd.startswith(cwd_hint_clean) or cwd_hint_clean.startswith(session_cwd):
                score += 300.0 * weight
            elif cwd_name and Path(session_cwd).name == cwd_name:
                score += 80.0 * weight
    return score


def _discover_codex_homes(codex_home: str | None = None, cwd_hint: str = "") -> list[Path]:
    candidates: list[Path] = []
    explicit = str(codex_home or "").strip()
    if explicit:
        candidates.append(Path(explicit))
    else:
        env_home = str(os.environ.get("CODEX_HOME", "") or "").strip()
        if env_home:
            candidates.append(Path(env_home))
        candidates.append(Path.home() / ".codex")
        users_root = Path("C:/Users")
        if users_root.exists():
            try:
                candidates.extend(users_root.glob("*/.codex"))
            except Exception:
                pass
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            resolved = candidate.expanduser()
        key = str(resolved).lower()
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        deduped.append(resolved)
    if explicit:
        return deduped[:1]
    if len(deduped) <= 1:
        return deduped
    ranked = sorted(deduped, key=lambda path: _rank_codex_home(path, cwd_hint=cwd_hint), reverse=True)
    return ranked[:1]


def _discover_session_files(codex_home: str | None = None, cwd_hint: str = "", since_days: int = 30, max_files: int = 200) -> tuple[list[Path], list[Path]]:
    homes = _discover_codex_homes(codex_home=codex_home, cwd_hint=cwd_hint)
    if not homes:
        return [], []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(since_days or 30)))
    files: list[Path] = []
    for home in homes:
        sessions_root = home / "sessions"
        if not sessions_root.exists():
            continue
        try:
            for path in sessions_root.rglob("rollout-*.jsonl"):
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                except Exception:
                    continue
                if mtime >= cutoff:
                    files.append(path)
        except Exception:
            continue
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    cwd_hint_clean = str(cwd_hint or "").strip().lower()
    if cwd_hint_clean and files:
        cwd_name = Path(cwd_hint_clean).name
        exact: list[Path] = []
        related: list[Path] = []
        other: list[Path] = []
        for path in files:
            session_cwd = _probe_session_cwd(path).lower()
            if session_cwd == cwd_hint_clean:
                exact.append(path)
            elif session_cwd and cwd_name and Path(session_cwd).name == cwd_name:
                related.append(path)
            else:
                other.append(path)
        files = exact + related + other
    if max_files > 0:
        files = files[:max_files]
    return homes, files


def _parse_session_file(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except Exception:
        return None
    cache_key = str(path.resolve())
    cached = _SESSION_CACHE.get(cache_key)
    if cached and cached[0] == stat.st_mtime_ns:
        return cached[1]

    session: dict[str, Any] = {
        "session_path": str(path),
        "session_id": "",
        "cwd": "",
        "started_at": None,
        "last_timestamp": None,
        "user_messages": [],
        "assistant_messages": [],
        "tool_names": [],
        "file_mentions": [],
        "tail_events": [],
        "task_complete_message": "",
        "search_parts": [],
        "reasoning_item_count": 0,
    }
    file_seen: set[str] = set()

    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                if len(line) > _SKIP_LINE_BYTES:
                    if '"type":"session_meta"' in line:
                        session["session_id"] = _fast_extract_json_string(line, "id") or session["session_id"]
                        session["cwd"] = _fast_extract_json_string(line, "cwd") or session["cwd"]
                        meta_timestamp = _parse_timestamp(_fast_extract_json_string(line, "timestamp"))
                        if meta_timestamp is not None:
                            session["started_at"] = meta_timestamp
                        _append_text(session, session.get("cwd", ""))
                    elif '"type":"turn_context"' in line:
                        session["cwd"] = _fast_extract_json_string(line, "cwd") or session["cwd"]
                        _append_text(session, session.get("cwd", ""))
                    elif '"type":"reasoning"' in line:
                        session["reasoning_item_count"] += 1
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                timestamp_text = str(entry.get("timestamp") or "")
                timestamp = _parse_timestamp(timestamp_text)
                if timestamp is not None:
                    if session["started_at"] is None:
                        session["started_at"] = timestamp
                    session["last_timestamp"] = timestamp

                entry_type = str(entry.get("type") or "")
                payload = entry.get("payload")

                if entry_type == "session_meta" and isinstance(payload, dict):
                    session["session_id"] = str(payload.get("id", "") or session["session_id"])
                    session["cwd"] = str(payload.get("cwd", "") or session["cwd"])
                    meta_timestamp = _parse_timestamp(payload.get("timestamp"))
                    if meta_timestamp is not None:
                        session["started_at"] = meta_timestamp
                    _append_text(session, payload.get("cwd", ""))
                    continue

                if entry_type == "turn_context" and isinstance(payload, dict):
                    session["cwd"] = str(payload.get("cwd", "") or session["cwd"])
                    _append_text(session, payload.get("cwd", ""))
                    continue

                if entry_type == "event_msg" and isinstance(payload, dict):
                    event_type = str(payload.get("type") or "").strip()
                    if event_type == "user_message":
                        message = str(payload.get("message", "") or "").strip()
                        if message:
                            session["user_messages"].append(message)
                            _append_text(session, message)
                            _append_file_mentions(session, file_seen, message)
                            _append_tail(session, "user_message", message, timestamp=timestamp_text)
                    elif event_type == "agent_message":
                        message = str(payload.get("message", "") or "").strip()
                        if message:
                            session["assistant_messages"].append(message)
                            _append_text(session, message)
                            _append_file_mentions(session, file_seen, message)
                            _append_tail(session, "agent_message", message, meta={"phase": str(payload.get("phase", "") or "")}, timestamp=timestamp_text)
                    elif event_type == "task_complete":
                        message = str(payload.get("last_agent_message", "") or "").strip()
                        if message:
                            session["task_complete_message"] = message
                            _append_text(session, message)
                            _append_file_mentions(session, file_seen, message)
                            _append_tail(session, "task_complete", message, timestamp=timestamp_text)
                    elif event_type in {"exec_command_end", "mcp_tool_call_end", "web_search_end"}:
                        tool_name = str(payload.get("tool_name") or payload.get("tool") or event_type).strip()
                        _append_tool(session, tool_name)
                        _append_tail(session, event_type, meta={"tool": tool_name}, timestamp=timestamp_text)
                        _append_text(session, tool_name)
                    else:
                        tool_name = str(payload.get("tool_name") or payload.get("tool") or payload.get("name") or "").strip()
                        if tool_name:
                            _append_tool(session, tool_name)
                            _append_text(session, tool_name)

                if entry_type == "response_item" and isinstance(payload, dict):
                    item_type = str(payload.get("type") or "").strip()
                    if item_type == "message":
                        role = str(payload.get("role") or "").strip().lower()
                        text_bits = []
                        for item in payload.get("content") or []:
                            if isinstance(item, dict):
                                text_bits.extend(_collect_strings(item))
                        joined = "\n".join(bit for bit in text_bits if bit).strip()
                        if joined and role == "assistant":
                            session["assistant_messages"].append(joined)
                            _append_text(session, joined)
                            _append_file_mentions(session, file_seen, joined)
                            _append_tail(session, "assistant_message", joined, timestamp=timestamp_text)
                    elif item_type == "function_call":
                        tool_name = str(payload.get("name") or "").strip()
                        if tool_name:
                            _append_tool(session, tool_name)
                            _append_text(session, tool_name)
                            _append_tail(session, "function_call", meta={"tool": tool_name}, timestamp=timestamp_text)
                        args = payload.get("arguments")
                        if isinstance(args, str):
                            parsed_args = _safe_json_loads(args)
                            scan_value = parsed_args if parsed_args is not None else args
                        else:
                            scan_value = args
                        _append_file_mentions(session, file_seen, scan_value)
                        _append_text(session, json.dumps(scan_value, ensure_ascii=True) if isinstance(scan_value, (dict, list)) else str(scan_value or ""))
                    elif item_type == "function_call_output":
                        output_value = payload.get("output")
                        _append_file_mentions(session, file_seen, output_value)
                    elif item_type == "reasoning":
                        session["reasoning_item_count"] += 1
                    elif item_type == "web_search_call":
                        _append_tool(session, "web_search")
                        _append_text(session, "web_search")
    except Exception:
        return None

    session["search_text"] = "\n".join(session.get("search_parts") or []).lower()
    _SESSION_CACHE[cache_key] = (stat.st_mtime_ns, session)
    return session


def _session_brief(session: dict[str, Any], score: float | None = None) -> dict[str, Any]:
    started_at = session.get("started_at")
    last_timestamp = session.get("last_timestamp")
    return {
        "session_id": session.get("session_id") or "",
        "session_path": session.get("session_path") or "",
        "cwd": session.get("cwd") or "",
        "started_at": started_at.isoformat() if isinstance(started_at, datetime) else None,
        "last_timestamp": last_timestamp.isoformat() if isinstance(last_timestamp, datetime) else None,
        "score": round(float(score), 3) if score is not None else None,
        "tool_count": len(session.get("tool_names") or []),
        "file_count": len(session.get("file_mentions") or []),
    }


def _score_session(session: dict[str, Any], query_tokens: list[str], cwd_hint: str = "") -> float:
    score = 0.0
    search_text = str(session.get("search_text") or "")
    if query_tokens:
        counts = Counter(_tokenize(search_text))
        for token in query_tokens:
            freq = counts.get(token, 0)
            if freq:
                score += 3.0 + min(freq, 4) * 0.75
            elif token in search_text:
                score += 1.5
    session_cwd = str(session.get("cwd") or "").strip().lower()
    cwd_hint_clean = str(cwd_hint or "").strip().lower()
    if cwd_hint_clean and session_cwd:
        if session_cwd == cwd_hint_clean:
            score += 25.0
        elif session_cwd.startswith(cwd_hint_clean) or cwd_hint_clean.startswith(session_cwd):
            score += 12.0
        elif Path(session_cwd).name == Path(cwd_hint_clean).name:
            score += 6.0
    last_timestamp = session.get("last_timestamp")
    if isinstance(last_timestamp, datetime):
        age_hours = max(0.0, (datetime.now(timezone.utc) - last_timestamp).total_seconds() / 3600.0)
        score += max(0.0, 12.0 - min(age_hours / 24.0, 12.0))
    if session.get("task_complete_message"):
        score += 1.0
    return score


def _extract_hot_terms(session: dict[str, Any], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for text in (session.get("user_messages") or [])[-6:]:
        counter.update(_tokenize(text))
    for text in (session.get("assistant_messages") or [])[-4:]:
        counter.update(_tokenize(text))
    return [token for token, _ in counter.most_common(limit)]


def _dt_to_ms(value: Any) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return 0


def _repo_doc_candidates(candidates: list[str]) -> list[str]:
    docs: list[str] = []
    seen: set[str] = set()
    for rel in candidates:
        token = str(rel or "").replace("\\", "/").strip()
        if not token or token.lower() in seen:
            continue
        if (_REPO_ROOT / token).exists():
            seen.add(token.lower())
            docs.append(token)
    return docs


def _session_resume_tokens(session: dict[str, Any], summary: str = "") -> set[str]:
    tokens: set[str] = set()
    parts: list[str] = []
    if summary:
        parts.append(summary)
    parts.extend((session.get("user_messages") or [])[-5:])
    parts.extend((session.get("assistant_messages") or [])[-3:])
    parts.extend((session.get("tool_names") or [])[-8:])
    parts.extend((session.get("file_mentions") or [])[-8:])
    for part in parts:
        tokens.update(_tokenize(part))
    return tokens


def _classify_resume_seam(session: dict[str, Any], summary: str = "") -> tuple[str, str]:
    tokens = _session_resume_tokens(session, summary=summary)
    continuity_terms = {
        "continuity", "compaction", "compression", "reacclimation", "reacclimation_packet",
        "restore", "archive", "archives", "sequence", "sequencer",
        "context", "groundhog", "aspectation", "resume", "packet",
    }
    field_terms = {
        "surface", "alignment", "weather", "rain", "field", "blackboard", "corroboration",
        "contracts", "query", "mirror", "glyph", "snapshot", "parity",
    }
    route_terms = {
        "route", "support", "kneel", "balance", "dreamer", "calibration", "controller",
        "blocker", "contact", "topology",
    }
    if tokens & continuity_terms:
        return "continuity_reacclimation", "Continuity Reacclimation"
    if tokens & route_terms:
        return "route_calibration_resume", "Route Calibration Resume"
    if tokens & field_terms:
        return "surface_alignment_review", "Surface Alignment Review"
    return "resume_reacclimation", "Resume Reacclimation"


def _build_resume_help_lane(seam_id: str) -> list[dict[str, Any]]:
    help_lane: list[dict[str, Any]] = [
        {
            "tool": "env_help",
            "args": {"topic": "continuity_reacclimation"},
            "reason": "Use the existing environment help lane to recover the resume doctrine instead of inventing a new restore surface.",
        },
        {
            "tool": "env_help",
            "args": {"topic": "output_state"},
            "reason": "Use the derived orienting surface contract to normalize placement, drift, freshness, and next reads across the resumed seam.",
        },
        {
            "tool": "env_help",
            "args": {"topic": "env_report"},
            "reason": "Keep scoped brokered diagnosis available after the fresh theater and snapshot reads land.",
        },
    ]
    if seam_id == "route_calibration_resume":
        help_lane.append(
            {
                "tool": "env_help",
                "args": {"topic": "dreamer_transform_relay"},
                "reason": "Use the calibration relay only after the fresh theater intake when the resumed seam is route/support mechanics.",
            }
        )
    else:
        help_lane.append(
            {
                "tool": "env_help",
                "args": {"topic": "text_theater_embodiment"},
                "reason": "Keep the embodied read as the first live surface after archive restore.",
            }
        )
    return help_lane


def _build_resume_next_reads(seam_id: str) -> list[dict[str, Any]]:
    next_reads: list[dict[str, Any]] = [
        {
            "tool": "env_read",
            "args": {"query": "text_theater_embodiment"},
            "reason": "Re-open a fresh embodied frame before trusting archive continuity as live truth.",
        },
        {
            "tool": "env_control",
            "args": {"command": "capture_supercam", "actor": "assistant"},
            "reason": "Acquire browser-visible corroboration so the resumed chain does not rely on transcript memory alone.",
        },
        {
            "tool": "env_read",
            "args": {"query": "text_theater_view", "view": "consult", "section": "blackboard", "diagnostics": True},
            "reason": "Recover the visible query-work lane and anchor the live objective before widening.",
        },
        {
            "tool": "env_read",
            "args": {"query": "text_theater_snapshot"},
            "reason": "Check structured snapshot freshness and the rows backing the resumed seam.",
        },
    ]
    if seam_id == "route_calibration_resume":
        next_reads.append(
            {
                "tool": "env_report",
                "args": {"report_id": "route_stability_diagnosis"},
                "reason": "Use the existing scoped broker after the live theater and snapshot intake is fresh.",
            }
        )
    else:
        next_reads.append(
            {
                "tool": "env_read",
                "args": {"query": "contracts"},
                "reason": "Open the scoped contract surface only after the fresh theater and snapshot reads are in hand.",
            }
        )
    return next_reads


def _pick_objective_seed(session: dict[str, Any], summary: str = "") -> str:
    candidates = [
        str(summary or "").strip(),
        *((session.get("user_messages") or [])[-2:]),
        str(session.get("task_complete_message") or "").strip(),
    ]
    for candidate in candidates:
        clean = _normalize_line(candidate, limit=180)
        if clean:
            return clean
    return "resume from archived operational continuity"


def _derive_resume_subject(session: dict[str, Any]) -> dict[str, str]:
    files = _dedupe_recent(session.get("file_mentions") or [], 12)
    if files:
        ident = str(files[-1] or "").strip()
        if ident:
            return {
                "subject_kind": "file",
                "subject_id": ident,
                "subject_key": f"file:{ident}",
            }
    cwd = str(session.get("cwd") or "").strip()
    if cwd:
        return {
            "subject_kind": "cwd",
            "subject_id": cwd,
            "subject_key": f"cwd:{cwd}",
        }
    session_path = str(session.get("session_path") or "").strip()
    return {
        "subject_kind": "session",
        "subject_id": session_path,
        "subject_key": f"session:{session_path}",
    }


def _recommended_repo_docs(seam_id: str, cwd: str = "") -> list[str]:
    cwd_name = Path(str(cwd or "").strip()).name.lower()
    if cwd_name != "champion_councl":
        return []
    candidates = [
        "docs/CODEX_CHAMPION_COUNCIL_INSTANTIATION_PROMPT_2026-04-13.md",
        "docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md",
        "docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md",
        "docs/STATIC_SURFACE_CORRELATION_SPEC_2026-04-15.md",
        "docs/ARCHIVED_LIVE_PAIRED_STATE_RESOURCE_SPEC_2026-04-15.md",
        "docs/PIVOT_DECLARATIONS_REGISTRY_2026-04-15.md",
        "docs/ASSOCIATIVE_CONTINUITY_ADRENALINE_SITREP_2026-04-15.md",
        "docs/PAN_SUPPORT_FIELD_PROCGEN_SPEC_2026-04-15.md",
        "docs/QUERY_ROOT_SEQUENCE_PROTOCOL_2026-04-13.md",
        "docs/BLACKBOARD_QUERY_PROCUREMENT_DEEP_DIVE_2026-04-13.md",
        "docs/ENVIRONMENT_MEMORY_INDEX.md",
    ]
    if seam_id in {"continuity_reacclimation", "surface_alignment_review", "resume_reacclimation"}:
        candidates.append("docs/BLACKBOARD_FIELD_UNIFICATION_SITREP_2026-04-14.md")
    if seam_id == "route_calibration_resume":
        candidates.extend(
            [
                "docs/CODEX_SITREP_2026-04-13_DREAMER_TEXT_THEATER_CALIBRATION.md",
                "docs/CALIBRATION_TRAJECTORY_REPORT_2026-04-13.md",
            ]
        )
    return _repo_doc_candidates(candidates)


def _active_pivot_declarations(cwd: str = "") -> list[dict[str, Any]]:
    cwd_name = Path(str(cwd or "").strip()).name.lower()
    if cwd_name != "champion_councl":
        return []
    pivots = [
        {
            "pivot_id": "operative_memory_alignment",
            "label": "Operative Memory Alignment",
            "status": "active",
            "retract_to_after_completion": "static_surface_correlation",
            "reason": "Carry the agent's current operational stance through continuity, blackboard, theater, reports, and docs so compression no longer forces transcript archaeology.",
            "docs": _repo_doc_candidates(
                [
                    "docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md",
                    "docs/ASSOCIATIVE_CONTINUITY_ADRENALINE_SITREP_2026-04-15.md",
                    "docs/QUERY_MIRROR_UNIFICATION_SITREP_2026-04-15.md",
                ]
            ),
        },
        {
            "pivot_id": "static_surface_correlation",
            "label": "Static Surface Correlation",
            "status": "declared",
            "retract_to_after_completion": "pan_support_field_procgen",
            "reason": "Correlate completed model grounding against total relevant surface, not only sparse point contacts.",
            "docs": _repo_doc_candidates(
                [
                    "docs/STATIC_SURFACE_CORRELATION_SPEC_2026-04-15.md",
                    "docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md",
                    "docs/BUILDER_THEATER_SESSION_HANDOFF_2026-03-31.md",
                ]
            ),
        },
        {
            "pivot_id": "pan_support_field_procgen",
            "label": "Pan Support-Field Procgen",
            "status": "declared",
            "retract_to_after_completion": "archived_live_paired_state_resource",
            "reason": "Allow support topology to compensate under intended contacts instead of forcing the body to accommodate a fixed floor every time.",
            "docs": _repo_doc_candidates(
                [
                    "docs/PAN_SUPPORT_FIELD_PROCGEN_SPEC_2026-04-15.md",
                    "docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md",
                    "docs/PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md",
                ]
            ),
        },
        {
            "pivot_id": "archived_live_paired_state_resource",
            "label": "Archived / Live Paired-State Resource",
            "status": "active",
            "retract_to_after_completion": "query_mirror_sequence_unification",
            "reason": "Pair archived query posture and live query posture on one authoring surface with drift, freshness, reset-boundary, and next-read logic.",
            "docs": _repo_doc_candidates(
                [
                    "docs/ARCHIVED_LIVE_PAIRED_STATE_RESOURCE_SPEC_2026-04-15.md",
                    "docs/ASSOCIATIVE_CONTINUITY_ADRENALINE_SITREP_2026-04-15.md",
                    "docs/QUERY_MIRROR_UNIFICATION_SITREP_2026-04-15.md",
                ]
            ),
        },
        {
            "pivot_id": "query_mirror_sequence_unification",
            "label": "Query / Mirror Sequence Unification",
            "status": "active",
            "retract_to_after_completion": "context_compression_countermeasure",
            "reason": "Carry mirrored freshness and query objective on one finite sequence instead of separate inference lanes.",
            "docs": _repo_doc_candidates(
                [
                    "docs/QUERY_MIRROR_UNIFICATION_SITREP_2026-04-15.md",
                    "docs/QUERY_ROOT_SEQUENCE_PROTOCOL_2026-04-13.md",
                ]
            ),
        },
        {
            "pivot_id": "context_compression_countermeasure",
            "label": "Context Compression Countermeasure",
            "status": "active",
            "retract_to_after_completion": "baseline_runtime_alignment",
            "reason": "Restore posture, query stance, and reset boundaries instead of a recap-only continuity summary.",
            "docs": _repo_doc_candidates(
                [
                    "docs/ASSOCIATIVE_CONTINUITY_ADRENALINE_SITREP_2026-04-15.md",
                    "docs/BLACKBOARD_FIELD_UNIFICATION_SITREP_2026-04-14.md",
                ]
            ),
        },
    ]
    return pivots


def _build_reset_boundary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "boundary_kind": "context_compression_resume",
        "archive_only": True,
        "requires_fresh_live_read": True,
        "first_authoritative_surfaces": [
            "env_read(query='text_theater_embodiment')",
            "env_control(command='capture_supercam')",
            "env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)",
            "env_read(query='text_theater_snapshot')",
        ],
        "raw_state_guardrail": _RAW_STATE_GUARDRAIL,
        "last_archived_event_ms": _dt_to_ms(session.get("last_timestamp")),
    }


def _build_query_state(session: dict[str, Any], summary: str = "") -> dict[str, Any]:
    seam_id, seam_label = _classify_resume_seam(session, summary=summary)
    subject = _derive_resume_subject(session)
    session_id = str(session.get("session_id") or "").strip()
    fallback_session = Path(str(session.get("session_path") or "session")).stem
    sequence_tail = session_id or fallback_session or "session"
    priority_pivots = _active_pivot_declarations(cwd=str(session.get("cwd") or ""))
    return {
        "sequence_id": f"query_seq/session/{sequence_tail}",
        "segment_id": "resume_candidate",
        "session_id": session_id,
        "objective_id": seam_id,
        "objective_label": seam_label,
        "objective_seed": _pick_objective_seed(session, summary=summary),
        "subject_kind": str(subject.get("subject_kind") or ""),
        "subject_id": str(subject.get("subject_id") or ""),
        "subject_key": str(subject.get("subject_key") or ""),
        "status": "suspended",
        "archive_resume_only": True,
        "opened_at_ms": _dt_to_ms(session.get("started_at")),
        "last_seen_at_ms": _dt_to_ms(session.get("last_timestamp")),
        "anchor_row_ids": [],
        "current_pivot_id": str((priority_pivots[0] or {}).get("pivot_id") or "") if priority_pivots else "",
        "priority_pivots": priority_pivots,
        "help_lane": _build_resume_help_lane(seam_id),
        "next_reads": _build_resume_next_reads(seam_id),
        "raw_state_guardrail": _RAW_STATE_GUARDRAIL,
    }


def _build_surface_prime(session: dict[str, Any], summary: str = "") -> dict[str, Any]:
    seam_id, seam_label = _classify_resume_seam(session, summary=summary)
    priority_pivots = _active_pivot_declarations(cwd=str(session.get("cwd") or ""))
    return {
        "prime_mode": "archive_reacclimation",
        "seam_id": seam_id,
        "seam_label": seam_label,
        "recovered_from_archive": True,
        "corroboration_required": True,
        "current_pivot_id": str((priority_pivots[0] or {}).get("pivot_id") or "") if priority_pivots else "",
        "priority_pivots": priority_pivots,
        "recommended_docs": _recommended_repo_docs(seam_id, cwd=str(session.get("cwd") or "")),
        "help_lane": _build_resume_help_lane(seam_id),
        "next_reads": _build_resume_next_reads(seam_id),
        "reset_boundary": _build_reset_boundary(session),
        "corroboration_surfaces": [
            "text_theater_embodiment",
            "capture_supercam",
            "consult_blackboard",
            "text_theater_snapshot",
            "env_help",
            "env_report_or_contracts",
        ],
    }


def _build_paired_state_resource(session: dict[str, Any], summary: str = "") -> dict[str, Any]:
    query_state = _build_query_state(session, summary=summary)
    surface_prime = _build_surface_prime(session, summary=summary)
    recommended_next_reads: list[dict[str, Any]] = []
    for entry in list(query_state.get("help_lane") or []) + list(query_state.get("next_reads") or []):
        if isinstance(entry, dict):
            recommended_next_reads.append(entry)
    return {
        "resource_kind": "archived_live_paired_state",
        "shared_query_identity": {
            "objective_id": str(query_state.get("objective_id") or ""),
            "objective_label": str(query_state.get("objective_label") or ""),
            "subject_key": str(query_state.get("subject_key") or ""),
            "current_pivot_id": str(query_state.get("current_pivot_id") or ""),
        },
        "archive_query_state": query_state,
        "live_query_state": None,
        "archive_surface_prime": surface_prime,
        "live_mirror_context": {
            "status": "pending_fresh_live_read",
            "recovered_from_archive": True,
            "authoritative": False,
            "note": "Archive posture recovered; fresh live theater/query corroboration is still required.",
        },
        "drift": {
            "status": "unpaired_pending_live",
            "agreement_points": [],
            "discrepancies": [
                {
                    "field": "live_query_state",
                    "classification": "stale_state",
                    "archive_value": "available",
                    "live_value": "missing",
                    "status": "open",
                    "note": "The archive side is restored, but no live query state has been paired yet.",
                }
            ],
            "decision": "Recover the live query thread before trusting any merge between archive posture and current runtime posture.",
        },
        "freshness": {
            "archive_only": True,
            "requires_fresh_live_read": True,
            "archive_started_at_ms": _dt_to_ms(session.get("started_at")),
            "archive_last_seen_at_ms": _dt_to_ms(session.get("last_timestamp")),
        },
        "required_recorroboration": list(surface_prime.get("corroboration_surfaces") or []),
        "recommended_next_reads": recommended_next_reads[:6],
        "reset_boundary": _build_reset_boundary(session),
    }


def _build_resume_hints(session: dict[str, Any], summary: str = "") -> list[str]:
    hints: list[str] = []
    cwd = str(session.get("cwd") or "").strip()
    if cwd:
        hints.append(f"resume in cwd {cwd}")
    recent_tools = _dedupe_recent(session.get("tool_names") or [], 4)
    if recent_tools:
        hints.append("replay the hot tool lane: " + ", ".join(recent_tools))
    recent_files = _dedupe_recent(session.get("file_mentions") or [], 4)
    if recent_files:
        hints.append("re-open the touched file surface: " + ", ".join(recent_files))
    if summary:
        hints.append("use the compaction summary as the semantic lookup key for this session")
    task_complete = str(session.get("task_complete_message") or "").strip()
    if task_complete:
        hints.append("start from the last stable answer instead of re-deriving the entire thread")
    return hints[:5]


def _build_continuity_packet(session: dict[str, Any], summary: str = "") -> dict[str, Any]:
    recent_user_messages = _dedupe_recent(session.get("user_messages") or [], 5)
    recent_assistant_messages = _dedupe_recent(session.get("assistant_messages") or [], 5)
    recent_tool_names = _dedupe_recent(session.get("tool_names") or [], 10)
    file_mentions = _dedupe_recent(session.get("file_mentions") or [], 12)
    task_complete_message = _normalize_line(session.get("task_complete_message") or "", limit=400)
    open_loops: list[str] = []
    if recent_user_messages:
        last_user = recent_user_messages[-1]
        if not task_complete_message or last_user not in task_complete_message:
            open_loops.append(last_user)
    query_state = _build_query_state(session, summary=summary)
    priority_pivots = _active_pivot_declarations(cwd=str(session.get("cwd") or ""))
    resume_focus = {
        "focus_cwd": str(session.get("cwd") or ""),
        "hot_tools": recent_tool_names[:6],
        "hot_files": file_mentions[:6],
        "hot_terms": _extract_hot_terms(session),
        "recent_pressures": recent_user_messages[-3:],
        "last_stable_answer": task_complete_message,
    }
    return {
        "packet_kind": "reacclimation",
        "recent_user_messages": recent_user_messages,
        "recent_assistant_messages": recent_assistant_messages,
        "recent_tool_names": recent_tool_names,
        "file_mentions": file_mentions,
        "task_complete_message": task_complete_message,
        "open_loops": open_loops,
        "tail": (session.get("tail_events") or [])[-12:],
        "resume_hints": _build_resume_hints(session, summary=summary),
        "current_pivot_id": str((priority_pivots[0] or {}).get("pivot_id") or "") if priority_pivots else "",
        "priority_pivots": priority_pivots,
        "query_state": query_state,
        "resume_focus": resume_focus,
        "surface_prime": _build_surface_prime(session, summary=summary),
        "paired_state_resource": _build_paired_state_resource(session, summary=summary),
    }


def continuity_status_payload(limit: int = 10, codex_home: str | None = None) -> dict[str, Any]:
    homes, files = _discover_session_files(codex_home=codex_home, since_days=3650, max_files=max(limit * 2, 6))
    sessions = [_parse_session_file(path) for path in files]
    sessions = [session for session in sessions if session]
    sessions.sort(
        key=lambda session: session.get("last_timestamp") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return {
        "status": "ok",
        "archive": {
            "codex_homes": [str(path) for path in homes],
            "history_paths": [str(path / "history.jsonl") for path in homes if (path / "history.jsonl").exists()],
            "scanned_sessions": len(files),
        },
        "recent_sessions": [_session_brief(session) for session in sessions[: max(1, int(limit or 10))]],
    }


def continuity_restore_payload(
    summary: str | None = None,
    cwd: str | None = None,
    limit: int = 3,
    since_days: int = 30,
    session_path: str | None = None,
    codex_home: str | None = None,
) -> dict[str, Any]:
    summary_text = str(summary or "").strip()
    cwd_hint = str(cwd or "").strip()
    resolved_limit = max(1, min(int(limit or 3), 10))

    target_session_path = str(session_path or "").strip()
    if target_session_path:
        session = _parse_session_file(Path(target_session_path))
        if not session:
            return {"status": "error", "error": f"Session not found or unreadable: {target_session_path}"}
        matched = [(session, 100.0)]
        homes = _discover_codex_homes(codex_home=codex_home, cwd_hint=cwd_hint)
    else:
        homes, files = _discover_session_files(
            codex_home=codex_home,
            cwd_hint=cwd_hint,
            since_days=max(1, int(since_days or 30)),
            max_files=8 if cwd_hint else 12,
        )
        query_tokens = _tokenize(summary_text)
        sessions = [_parse_session_file(path) for path in files]
        scored: list[tuple[dict[str, Any], float]] = []
        for session in sessions:
            if not session:
                continue
            score = _score_session(session, query_tokens=query_tokens, cwd_hint=cwd_hint)
            scored.append((session, score))
        scored.sort(
            key=lambda item: (
                item[1],
                item[0].get("last_timestamp") or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        matched = scored[:resolved_limit]

    if not matched:
        return {
            "status": "error",
            "error": "No matching session archive found",
            "query": {"summary": summary_text, "cwd": cwd_hint, "since_days": since_days},
            "archive": {"codex_homes": [str(path) for path in homes]},
        }

    best_session, best_score = matched[0]
    return {
        "status": "ok",
        "query": {
            "summary": summary_text,
            "cwd": cwd_hint,
            "since_days": int(since_days or 30),
            "session_path": target_session_path or None,
        },
        "archive": {
            "codex_homes": [str(path) for path in homes],
            "history_paths": [str(path / "history.jsonl") for path in homes if (path / "history.jsonl").exists()],
        },
        "best_session": _session_brief(best_session, score=best_score),
        "matched_sessions": [_session_brief(session, score=score) for session, score in matched],
        "continuity_packet": _build_continuity_packet(best_session, summary=summary_text),
    }
