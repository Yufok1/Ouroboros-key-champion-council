# Master TODO - Frontend-Only Execution Plan (2026-03-05)

## Operating Precept
- Do not edit backend files.
- Do not edit `champion_gen8` or capsule internals.
- Backend defects are tracked as deferred blockers, with frontend mitigations only.

## Evidence Artifacts
- `self_deploy/data/high_intensity_eval_20260305_030422.json`
- `self_deploy/data/master_ops_eval_20260305_031154.json`
- `self_deploy/data/felixbag_ci_eval_20260305_031407.json`
- `self_deploy/data/resume_eval_20260304_225842.json`

## Proven Operational Status
- Resumed run verified 3 plugged provider slots operational (`0..2`).
- Deterministic `invoke_slot` checks stable.
- Workflow stress and timeout reconciliation operate for compact/medium definitions.
- Activity trace rows are emitted backend-side with workflow trace metadata.
- FelixBag substrate faculties are operational:
  - `bag_*` lifecycle, `file_*` lifecycle, and utility paths (`pocket/summon/materialize/save/load/export`).
- Collective-memory pattern is operationalized via compact entropy flow:
  - `ci_entropy_compact_20260305_031622` -> `proxy_exec_c0651517883a`.
  - Shards persisted to `eval/ci/20260305_031622/compact/*`.

## Resume Addendum (2026-03-04 22:58 ET)
- Frontend mitigations deployed and pushed:
  - `89cca63` activity feed pagination + full session history retention in UI.
  - `df48395` compare slot coercion + workflow preflight guards.
- Revalidated:
  - `workflow_create`/`workflow_update` invalid definitions now reject at call time (`-32602`).
  - Heavy 3-slot fanout (`~5.7s`) completed without timeout.
- Newly proven backend limitations:
  - Node-output template refs are not resolved in workflow params (`$s0`, `$s0.output` remain literal).
  - In-workflow `bag_put` keys are readable via `bag_read_doc`/`bag_catalog` but fail via `bag_get`.

## Reorganized Issue Register

### Frontend Fix Now

#### 1) `ISS-FEED-DOM-TRIM` (Medium)
- Problem:
  - Activity DOM is trimmed to 50 visible rows (`static/main.js`, `addActivityEntry`), hiding nested traces during load.
- Frontend-only solution:
  1. Replace hard trim with paginated/virtualized list.
  2. Keep trace-group expansion state while paging.
  3. Show visible/total counters and “load older” controls.
- Status:
  - Done (frontend deployed in `89cca63`).

#### 2) `ISS-CMP-SLOT-TYPE` (High, frontend mitigation)
- Problem:
  - `compare` with string slot ids returns empty results silently.
- Frontend-only solution:
  1. Enforce numeric slot arrays in all compare UIs.
  2. Coerce string numerics to integers client-side before submit.
  3. Block submit when non-numeric slot values remain.
  4. Add explicit warning banner for empty `comparisons` with non-empty slot input.
- Status:
  - Frontend mitigation done (deployed in `df48395`).
  - Backend behavior still reproducible when callers bypass UI.

#### 3) `ISS-WF-HISTORY-LIMIT-SCHEMA` (Low, frontend mitigation)
- Problem:
  - `workflow_history.limit` is schema-typed as string.
- Frontend-only solution:
  1. Always serialize `limit` as string from UI/API wrapper.
  2. Normalize display and internal controls as numeric while emitting string on request.

#### 4) `ISS-WF-CREATE-VALIDATION-GAP` (High, frontend mitigation)
- Problem:
  - Invalid workflows can be created and only fail at execute time.
- Frontend-only solution:
  1. Add client-side workflow preflight validator:
     - Required node fields.
     - Required tool args from `/api/tools` schemas.
  2. Block publish/execute buttons on preflight failure.
  3. Show field-level diagnostics in workflow editor.
- Status:
  - Frontend preflight done (deployed in `df48395`).
  - Backend now also rejects invalid create/update in resumed live tests.

### Backend-Deferred Blockers (Report-Only)

#### 5) `ISS-WF-CACHED-DEF-EXEC` (High blocker)
- Problem:
  - Workflows large enough to trigger `_cached` on `workflow_get` can fail on `workflow_execute` (409), even with valid definitions.
- Counter-proof:
  - `wf_small_031552` (no `_cached`) executes.
  - `wf_big_031552` (`_cached: r701`) fails execute.
  - Large entropy workflow failed execute with validation error despite valid cached definition payload.
- Frontend containment strategy:
  1. Add workflow size budget indicator (warn above threshold).
  2. Prefer compact workflows + post-run memory writes (external orchestration).
  3. Auto-suggest “compact CI pattern” when definition crosses risk threshold.

#### 6) `ISS-WF-NODE-TEMPLATE-RESOLUTION` (High blocker)
- Problem:
  - Workflow params do not resolve references to prior node outputs (e.g. `$s0`, `$s0.output`), so downstream tools receive literal placeholders.
- Counter-proof:
  - `eval_resume_node_ref_invoke_f8a2` output from node `s1` became literal `$s0.output`.
  - `eval_resume_bag_node_template_e4f6` persisted literal `$s0`.
  - `$input.*` substitutions still resolve correctly.
- Frontend containment strategy:
  1. Mark node-ref placeholders as unsupported in workflow builder UX.
  2. Route cross-node value plumbing through orchestrator post-processing instead of inline templates.
  3. Add lint warning whenever non-`$input.*` placeholders appear in tool params.

#### 7) `ISS-BAG-GET-KEYSPACE-MISMATCH` (Medium blocker)
- Problem:
  - Some keys written in-workflow by `bag_put` are discoverable via `bag_catalog`/`bag_read_doc` but fail `bag_get`.
- Counter-proof:
  - `eval/resume/20260305/entropy/s0` and `/s1` readable via `bag_read_doc`, not found by `bag_get`.
  - Direct external `bag_put` key `eval/resume/20260305/smoke/value` remains retrievable via `bag_get`.
- Frontend containment strategy:
  1. Prefer `bag_read_doc` for workflow-produced memory keys.
  2. In UI retrieval path, fallback from `bag_get` to `bag_read_doc` on not-found.
  3. Surface keyspace/source metadata on write confirmation.

## Frontend Implementation Backlog (No Backend Edits)
1. [done] Activity feed virtualization + trace pagination.
2. [done] Compare slot type hardening (numeric-only).
3. [done] Workflow editor preflight validator against tool schemas.
4. [todo] Workflow size-risk scoring and compact-mode suggestions.
5. [todo] `workflow_history.limit` request normalization wrapper.
6. [todo] Operator UX:
   - “Backend-deferred blocker” badges in Workflow tab.
   - Auto-linked evidence entries from activity rows.
7. [done] Workflow placeholder lint for unsupported non-`$input.*` refs.
8. [done] Memory read fallback chain (`bag_get` -> `bag_read_doc`) for workflow-produced keys.

## Collective Memory Substrate Plan (Frontend-Orchestrated)
- Keep entropy memory pipelines compact:
  - fanout generation workflow only.
  - follow with explicit `bag_put` calls from orchestrator/UI layer.
- Record CI shard metadata in FelixBag:
  - key naming: `eval/ci/<run>/compact/<slot>`.
  - summary doc key: `eval/ci/<run>/summary`.
- Compute and display diversity heuristics in UI:
  - unique shard count
  - pairwise lexical overlap score
  - trace completeness score

## Frontend Regression Pack
- Heavy activity run must preserve access to all trace rows (not only latest 50).
- Compare requests with text slot inputs must coerce/reject deterministically.
- Invalid workflow definitions must be blocked before create/execute.
- Compact entropy pipeline must:
  - execute
  - persist 4 shards in FelixBag
  - surface trace rows and diversity metrics in UI.
