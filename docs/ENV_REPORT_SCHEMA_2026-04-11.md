# Env Report Schema 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- pin the `env_report` contract before any broker recipe code
- give the report broker a stable, stateless materializer target
- keep reports composable as data, not as rendered output

Related docs:

- [OPUS_REACCLIMATION_SITREP_2026-04-11.md](/F:/End-Game/champion_councl/docs/OPUS_REACCLIMATION_SITREP_2026-04-11.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)

## Bottom Line

`env_report` is a **stateless materializer over existing truth**. It joins blackboard rows, text-theater snapshot context, workbench state, and corroboration into a small, auditable report. It is never a second truth plane. It never runs on the camera hot path. It never writes. It is a read-side companion to `env_read`, not a replacement.

The only persistent state the broker owns is:

- a recipe dispatch table (recipe_id → recipe function)
- a saved-report archive for semantic recall (later slice, not covered here)

Everything else is recomposed per-call from live shared_state.

## Scope

This doc pins:

- the wire-level shape of an `env_report` response
- the provenance / freshness contract
- the session-threading contract
- the error contract
- size discipline

This doc does **not** pin:

- recipe logic (that is code, one recipe at a time)
- how reports render inside text theater (text theater is a consumer, not authority)
- tape/decision-moment capture (separate `tape:{command_sync_token}:{ts}` contract)
- semantic recall over saved reports (later slice after 10+ recipes exist)

## Relation To Existing Architecture

Reads from, in priority order:

1. `shared_state.blackboard` — row pool + `working_set`
2. `shared_state.text_theater.snapshot` and `shared_state.text_theater.embodiment` — for anchors, freshness, and embodied interpretation
3. `shared_state.workbench.route_report` when present, plus `shared_state.workbench.active_controller` when present
4. `shared_state.corroboration`
5. `shared_state.focus`

Never reads from the browser/web theater directly. Never consumes camera pulses. Never bypasses the theater-first gate — every `env_report` call that touches shared_state must pass through the existing `_env_shared_state_prereq_payload` contract or forward the gate's error payload unchanged.

## Top-Level Response Shape

```
{
  "tool": "env_report",
  "status": "ok" | "error",
  "operation": "env_report",
  "operation_status": "ok" | "error" | "stale" | "unavailable" | "gate_blocked",
  "normalized_args": { "report_id": "...", "target": {...}, "raw_slice": false },
  "summary": "<one-liner rendered from the report>",
  "delta": { "found": bool, "report_id": "...", "live_revision": int },
  "report": { ... },
  "error": "<error_code>"          // only when status=error
}
```

## `report` Object — Required Fields

| Field | Type | Contract |
|---|---|---|
| `report_id` | str | Stable recipe id, e.g. `route_stability_diagnosis`. Must exist in the recipe dispatch table. |
| `intent` | str | One-line agent-readable purpose. ≤ 120 chars. |
| `target` | `{kind: str, id: str}` | Focus object (e.g. `character_runtime::mounted_primary`, `bone::lower_leg_l`). |
| `summary` | str | Terminator-view one-liner. Must be legible at a glance. ≤ 140 chars. |
| `lead_rows` | `[row_id, ...]` | Stable blackboard row ids this report leads with. Every id MUST resolve in `shared_state.blackboard.rows`. ≤ 6. |
| `supporting_rows` | `[row_id, ...]` | Second-tier rows. Ordered. Deduped against `lead_rows`. ≤ 12. |
| `why_this_matters` | str | One paragraph, operator-readable. Must explain, not dump. ≤ 400 chars. |
| `recommended_next_reads` | `[{tool, args, reason}, ...]` | Agent's next read steps. ≤ 5. |
| `recommended_captures` | `[{tool, args, reason}, ...]` | Capture calls the agent should consider. ≤ 3. |
| `evidence_paths` | `[str, ...]` | Dotted shared_state paths the broker consulted. For auditability. ≤ 12. |
| `capture_ids` | `[str, ...]` | Ids of already-resolved capture artifacts referenced. |

## `report` Object — Provenance / Freshness

| Field | Type | Contract |
|---|---|---|
| `live_revision` | int | Server live cache `updated_ms` at materialization time. |
| `snapshot_timestamp` | int | `shared_state.text_theater.snapshot.snapshot_timestamp` at materialization time. |
| `text_theater_anchor` | str \| null | Section id / line-range anchor in the text-theater embodiment the broker quoted. Null if no theater text was quoted. |
| `gate_state` | dict | Snapshot of `_env_text_theater_read_gate` at materialization time. Lets the caller verify the gate was satisfied when this report was composed. |

## `report` Object — Session Thread (Required)

The broker **always** returns a `session_thread` block derived from `shared_state.blackboard.working_set`. This is non-negotiable: it is what makes reports feel continuous across camera/focus changes and what prevents the broker from behaving like a stateless meter-wall.

```
"session_thread": {
  "selected_bone_ids":     [str, ...],
  "supporting_joint_ids":  [str, ...],
  "intended_support_set":  [str, ...],
  "missing_support_set":   [str, ...],
  "active_controller_id":  str,
  "active_route_id":       str,
  "pinned_row_ids":        [str, ...],
  "lead_row_ids":          [str, ...]   // echo of blackboard working_set.lead_row_ids at read time
}
```

All fields pulled verbatim from `shared_state.blackboard.working_set` (see `_envBuildBlackboardState` at `static/main.js:31564`). Session threading is integral to the first recipe, not a retrofit.

## `report` Object — Optional Fields

| Field | Type | Contract |
|---|---|---|
| `raw_slice` | dict \| null | **Default OFF.** Only populated if the recipe explicitly opts in AND the caller passed `raw_slice=true`. Never primary evidence. |
| `traces` | `[{row_id, points: [...]}, ...]` | Blackboard row trace excerpts. ≤ 3 rows. Points are the existing `trace` shape `{t, value, label}` already on rows. |
| `notes` | `[str, ...]` | Recipe-specific caveats. ≤ 4. |
| `severity` | `ok \| watch \| degraded \| critical` | Intuitive diagnosis severity. Derived from the same live truth as the rest of the report. |
| `designation` | str | Short canonical diagnosis label such as `single_brace_collapse` or `route_realized`. |
| `visual_read` | str | Short fused embodied read grounded in text theater plus route/support truth. ≤ 240 chars. |
| `expected_vs_observed` | dict | Structured support-topology comparison with `expected_support`, `observed_support`, `missing_support`, and `topology_read`. |
| `failure_character` | str | One-line characterization of the pose failure or success mode. ≤ 180 chars. |
| `embodied_evidence_lines` | `[str, ...]` | Small set of stripped text-theater embodiment lines the report used as its visual evidence. ≤ 6. |

## Size Discipline

Hard limits enforced at materialization:

- `summary`: ≤ 140 chars
- `intent`: ≤ 120 chars
- `why_this_matters`: ≤ 400 chars
- `visual_read`: ≤ 240 chars
- `failure_character`: ≤ 180 chars
- `lead_rows`: ≤ 6
- `supporting_rows`: ≤ 12
- `recommended_next_reads`: ≤ 5
- `recommended_captures`: ≤ 3
- `evidence_paths`: ≤ 12
- `embodied_evidence_lines`: ≤ 6
- total serialized report (JSON bytes): ≤ 8 KB default, hard cap 24 KB

If a recipe needs more, it MUST split into multiple linked reports (via `recommended_next_reads` pointing at sibling `env_report` calls). It must not balloon one report. This is the same anti-dump doctrine as the blackboard redo audit.

## Error Contract

All errors return `status="error"` and set `operation_status` to one of:

| `operation_status` | When | Required extra fields |
|---|---|---|
| `stale` | `snapshot_timestamp` older than `_env_text_theater_read_gate.last_text_theater_read` → caller must reread theater | `required_sequence: [str, ...]`, `gate_state: dict` |
| `gate_blocked` | Theater-first gate rejected the underlying shared_state read | Forward the existing `_env_shared_state_prereq_payload` error payload unchanged |
| `missing` | Required shared_state path not present | `missing_paths: [str, ...]` |
| `unavailable` | Live cache not available or not yet bootstrapped | `reason: str`, `cache_age_ms: int` |
| `recipe_error` | Recipe code raised | `recipe: str`, `exception_class: str`, `message: str` |
| `unknown_report` | `report_id` not registered in dispatch table | `available_reports: [str, ...]` |

Every error shape MUST include the attempted `report_id` and the `live_revision` that was attempted, so a caller can diagnose without a second call.

Errors never partially populate `report`. Either a full report, or a clean error envelope.

## Recipe Dispatch Contract (Sketch For Implementation, Not Schema)

Recipes are registered by id. Each recipe is a pure function:

```
(shared_state, target, args) -> report_dict_or_error
```

- pure: no writes
- deterministic given identical shared_state + target + args
- must honor size discipline and session-thread inclusion
- must set all required fields
- must cite at least one `evidence_path`

The dispatch table is the only persistent state the broker owns beyond the saved-report archive (future slice).

## First Recipe To Implement Against This Schema

`report_id: route_stability_diagnosis`

- **intent:** "Explain current route/support stability state and next adjustment"
- **reads from:**
  - `shared_state.blackboard.working_set.lead_row_ids`
  - `shared_state.blackboard.working_set.intended_support_set`
  - `shared_state.blackboard.working_set.missing_support_set`
  - `shared_state.workbench.route_report`
  - `shared_state.workbench.active_controller` when present
  - `shared_state.text_theater.snapshot`
  - `shared_state.text_theater.embodiment`
- **lead_rows candidates:** `route.status`, `route.phase`, `route.blocker`, `route.next_adjustment`, `balance.stability_risk`, `balance.stability_margin`
- **fused fields:** should emit `severity`, `designation`, `visual_read`, `expected_vs_observed`, `failure_character`, and `embodied_evidence_lines`
- **session-threaded from day one.** Not retrofitted.
- **recommended_next_reads** typically includes:
  - `env_read(query='text_theater_embodiment')` — for narrative corroboration
  - `env_report(report_id='controller_role_audit', target={...})` — once that recipe exists

One recipe. Then clean live eval of it against this schema. Then, and only then, broader broker work.

## Open Questions Deferred

1. Tool surface — dedicated `env_report` tool vs. `env_read(query='report::...')` — defer to implementation; this schema works either way.
2. Capture feedback loop (linking capture_ids back to reports automatically) — later.
3. Saved-report archive + semantic recall — later, after 10+ recipes.
4. Tape / decision-moment narrow snapshots — separate contract, not bundled with env_report.

## Relation To Theater-First Gate

The gate contract at `server.py:3817` is upstream of `env_report`. `env_report` is a broker over reads, not a replacement for them. If the underlying `env_read(query='shared_state')` would be blocked, the broker returns `operation_status='gate_blocked'` with the gate's `required_sequence` forwarded verbatim. This preserves the enforcement doctrine rather than bypassing it.

Forward-compat note: once `env_report` exists, the gate's error payload should be updated to list `env_report` as a preferred next step over raw `shared_state`, because reports pre-bundle the theater-first anchor and supporting rows the operator actually needs.

## Non-Goals Of This Schema

- does not pin render styling
- does not pin profile-family selection logic
- does not pin capture orchestration
- does not pin memory or recall behavior
- does not pin any UI
- does not redefine blackboard row contract (that is already live in `_envBuildBlackboardState` at `static/main.js:31197`)

## Summary

`env_report` is a stateless join over live truth, returning small, auditable, session-threaded reports that prefer reasoning over data dumps. The schema pins shape, provenance, session thread, errors, and size — nothing else. The first recipe `route_stability_diagnosis` implements against this exact contract. Then clean eval. Then the next recipe. Then broker expansion.

No broker plumbing, no saved-report archive, no capture feedback, no semantic recall in this slice. Just the contract.
