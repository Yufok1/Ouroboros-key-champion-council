# Master TODO - Frontend-Only Execution Plan (2026-03-05)

## Canonical Guides (Read First)
- `self_deploy/docs/MASTER_GUIDES_INDEX.md`
- `self_deploy/docs/MASTER_OPERATIONS_PLAYBOOK.md`
- `self_deploy/docs/MASTER_EVAL_CONTRACTS.md`

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

#### 5) `ISS-TOOLS-INVENTORY-PARITY` (High)
- Problem:
  - `Tools` tab inventory count/category rollup does not match the live runtime tool count (`179` in runtime header vs lower UI count/category grouping).
  - Operators cannot trust the tab as an authoritative inventory view.
- Frontend-only solution:
  1. Audit tool-list source versus runtime truth (`/api/tools`, MCP capabilities, granted/blocked overlays).
  2. Reconcile category bucketing so uncategorized/hidden tools are still counted in the total.
  3. Show authoritative total separately from filtered/rendered totals.
  4. Add a mismatch warning banner when rendered inventory diverges from runtime-reported tool count.

#### 6) `ISS-WF-FLOWCHART-NAVIGATION` (Medium)
- Problem:
  - Workflow flow chart supports node drag only.
  - Missing viewport pan, background drag, wheel/pinch zoom, and reset-fit style navigation.
- Frontend-only solution:
  1. Add background drag-to-pan behavior.
  2. Add wheel zoom with sensible min/max bounds.
  3. Add touchpad/pinch gesture support where available.
  4. Add viewport reset/fit control in the Workflow tab.
  5. Preserve node drag behavior without conflicting with canvas navigation.

#### 7) `ISS-GF-OPERATOR-SURFACE` (High)
- Problem:
  - GPU Fleet still feels disconnected even when the underlying Vast state is real.
  - Card actions and search/rental controls are operationally thin and visually underpowered for active GPU management.
  - Operators need clearer at-a-glance state, guidance, and frictionless navigation to the active rental.
- Frontend-only solution:
  1. Add stronger state treatment for `running`, `installing`, `ready`, `stopped`, and `error` phases.
  2. Add clearer action grouping for `CONNECT`, `READY`, `STOP`, and search/rent flows.
  3. Surface active-instance guidance inline:
     - stop vs destroy cost semantics
     - boot/install wait guidance
     - console-link prominence
  4. Improve card layout so telemetry, readiness, and actions read as one control surface instead of separate fragments.

#### 8) `ISS-GF-LIVE-TELEMETRY-FEED` (Medium)
- Problem:
  - GPU Fleet shows recent Vast activity, but not a focused operator feed for the current instance lifecycle.
  - There is no direct in-tab visibility into the most relevant GPU-side events/logs while booting, loading, or generating.
- Frontend-only solution:
  1. Add a per-instance live activity pane sourced from current Vast MCP activity/results.
  2. Group rows by instance id and action family (`rent`, `ready`, `run`, `load_model`, `generate`, `embed`, `stop`).
  3. Show condensed status lines with expandable detail payloads.
  4. Keep this UI scoped to existing MCP/tool outputs; do not invent a second backend log source.

#### 9) `ISS-MEM-LENS-SYSTEM` (Medium)
- Problem:
  - FelixBag/Memory is searchable, but still weak for fast human triage and visual reasoning.
  - Operators need filters/lenses across the current catalog, not only raw semantic search.
- Frontend-only solution:
  1. Expand the first-pass catalog filters into a proper lens system.
  2. Add visible state badges and filter chips for:
     - type
     - subsystem
     - recency
     - trust/state when metadata exists
  3. Add saved views/lenses for common working sets:
     - Debug
     - GPU/Vast
     - Eval docs
     - Compiler/docs
     - Historical/reference
  4. Keep semantic search as retrieval substrate, but make the primary operator surface visual and filter-driven.

#### 10) `ISS-COUNCIL-REMOTE-SLOT-VISIBILITY` (Medium)
- Problem:
  - The Council tab currently reflects raw slot truth correctly, but it does not yet communicate the remote-GPU attach lifecycle clearly.
  - Once a remote GPU is attached as a normal slot, operators need to see that provenance inline instead of inferring it from GPU Fleet or Activity.
- Frontend-only solution:
  1. Add remote-slot provenance badges in Council cards:
     - `REMOTE GPU`
     - provider/endpoint origin
     - attachment health state
  2. Add drill-through links between Council slots and the matching GPU Fleet instance when attachment metadata exists.
  3. Surface attachment failure state on the slot card if the remote endpoint is unreachable after attach.

#### 11) `ISS-ENVIRONMENT-TAB-FOUNDATION` (High)
- Problem:
  - There is no dedicated runtime shell for workflow-backed systems, environments, or produced programs.
  - The current Workflows tab is an editor/inspector, not an operator-facing environment surface.
- Frontend-only solution:
  1. Add a first-class `Environment` tab as a browser-native habitat for workflow-backed systems.
  2. Reuse existing workflow list/get/execute/history/status surfaces instead of inventing a second workflow engine.
  3. Provide one system picker plus run/step controls, state/output panes, trace visibility, and a habitat stage in a single shell.
  4. Keep the first pass centered on existing runtime truth:
     - workflow definition
     - workflow execution state
     - activity/debug traces
     - FelixBag artifacts

#### 12) `ISS-ENVIRONMENT-RENDER-CONTRACT` (High)
- Problem:
  - The frontend has no normalized projection layer that turns workflow/runtime state into a visible “system” or environment.
  - Without a stable render contract, any environment tab would become another one-off panel.
- Frontend-only solution:
  1. Define a minimal frontend render contract over existing outputs:
     - selected workflow
     - active execution state
     - node statuses
     - produced outputs/artifacts
     - related activity/debug rows
  2. Build adapters in the frontend only; do not change champion/runtime semantics in the first pass.
  3. Keep the renderer shell generic enough to support:
     - browser-native habitat scenes
     - control-room panels
     - system dashboards
     - artifact previews
     - future Godot/export targets

#### 13) `ISS-ENVIRONMENT-EXPORT-SURFACE` (Medium)
- Problem:
  - Produced workflow-backed systems have no dedicated operator surface for export, promotion, or packaging.
  - Existing export/runtime tools are present, but not presented as part of a coherent environment-production flow.
- Frontend-only solution:
  1. Add an export/promote surface inside the Environment tab.
  2. Use existing tools and artifacts only in the first pass:
     - `export_interface`
     - FelixBag artifacts/docs
     - workflow definitions/history
     - `materialize` where appropriate
  3. Distinguish clearly between:
     - runnable environment
     - exported interface bundle
     - saved workflow/artifact
  4. Treat full standalone program packaging as a later compiler/runtime contract.

#### 14) `ISS-ENVIRONMENT-DEEP-CONTROL-SURFACE` (High)
- Problem:
  - The first Environment shell can load, run, and observe workflow-backed systems, but it is not yet a true operator kernel / total-control surface.
  - Operators need to navigate node-level state, attached models, produced artifacts, and system structure from one place without bouncing between multiple tabs.
- Frontend-only solution:
  1. Add environment-side drill routing for:
     - workflow nodes
     - node outputs and node state payloads
     - attached model/provider metadata where present
     - linked debug/activity traces
  2. Add “focus” actions that jump the Environment shell to:
     - selected node
     - selected artifact
     - selected runtime trace
     - selected habitat object
     - selected branch/sample
  3. Keep the first implementation as a control shell over existing runtime truth; do not invent secondary state.

#### 15) `ISS-ENVIRONMENT-DOC-ARTIFACT-ARBITRATION` (High)
- Problem:
  - Workflow-backed systems need direct access to the documents, FelixBag records, and surfaced artifacts they produce or depend on.
  - The current shell shows outputs, but does not yet provide a proper arbitration surface for reading, tracing, and promoting those materials.
- Frontend-only solution:
  1. Add an Environment-side document/artifact browser tied to the active system.
  2. Surface related:
     - FelixBag docs
     - workflow-produced artifacts
     - exported interface results
     - linked memory keys when available
  3. Add open/read/focus actions that hand off into existing Memory and workflow drill surfaces while preserving environment context.

#### 16) `ISS-ENVIRONMENT-SHARED-OPERATOR-CONTROL` (High)
- Problem:
  - The Environment tab must support dynamic tandem use: human operator and assistant-driven workflow over the same system surface.
  - Without an explicit shared-control model, the shell risks becoming passive for one party and fragmented for the other.
- Frontend-only solution:
  1. Make all Environment actions explicit and externally callable through the existing runtime/UI state transitions.
  2. Preserve enough state in the shell so manual operator actions and assistant-directed actions converge on the same selected system, execution, trace, artifact, habitat object, and branch focus.
  3. Treat the Environment tab as the shared operational shell, not a read-only summary view.

#### 17) `ISS-ENVIRONMENT-OPERATOR-KERNEL` (High)
- Problem:
  - The shell lacks explicit god-mode controls for focus, sample, act, branch, trace, and promote.
  - Without an operator kernel, the habitat remains a staged viewer with partial controls.
- Frontend-only solution:
  1. Add a first-class operator kernel panel for:
     - focus state
     - sample-now
     - continuous sampling
     - branch creation
     - trace follow
     - export/promote hooks
  2. Keep all actions attributable by actor:
     - user
     - assistant
     - workflow
     - system
  3. Surface the action stream as a visible god-mode ledger inside the Environment tab.

### Backend-Deferred Blockers (Report-Only)

#### 18) `ISS-WF-CACHED-DEF-EXEC` (High blocker)
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

#### 19) `ISS-WF-NODE-TEMPLATE-RESOLUTION` (High blocker)
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

#### 20) `ISS-BAG-GET-KEYSPACE-MISMATCH` (Medium blocker)
- Problem:
  - Some keys written in-workflow by `bag_put` are discoverable via `bag_catalog`/`bag_read_doc` but fail `bag_get`.
- Counter-proof:
  - `eval/resume/20260305/entropy/s0` and `/s1` readable via `bag_read_doc`, not found by `bag_get`.
  - Direct external `bag_put` key `eval/resume/20260305/smoke/value` remains retrievable via `bag_get`.
- Frontend containment strategy:
  1. Prefer `bag_read_doc` for workflow-produced memory keys.
  2. In UI retrieval path, fallback from `bag_get` to `bag_read_doc` on not-found.
  3. Surface keyspace/source metadata on write confirmation.

#### 21) `ISS-WF-TOOL-ARGS-DROPPED` (High blocker)
- Problem:
  - Workflow `tool` nodes are reaching runtime tools without their declared args.
  - Live repros showed both literal args and `$input.*` args arriving as missing positional parameters.
- Counter-proof:
  - `tmp_audit_literal_slotinfo_20260306` failed with:
    - `slot_info() missing 1 required positional argument: 'slot'`
  - `tmp_audit_bagput_20260306` failed with:
    - `bag_put() missing 2 required positional arguments: 'key' and 'value'`
- Implication:
  - This is broader than template substitution. Tool-node arg plumbing itself is broken in the live workflow executor.

#### 22) `ISS-WF-EXEC-STATUS-HISTORY-GAP` (Medium blocker)
- Problem:
  - Failed workflow executions return an `execution_id`, but `workflow_status` and `workflow_history` do not surface the failed run afterward.
- Counter-proof:
  - `workflow_execute` returned `exec_01910d7dd19b` and `exec_bbbc73fa648b`
  - `workflow_status(exec_01910d7dd19b)` returned `Execution not found`
  - `workflow_history(..., limit=2)` returned `count: 0` for both audit workflows
- Implication:
  - Workflow failure auditability is incomplete even when execution failure is reported synchronously.

#### 23) `ISS-VAST-SEARCH-FILTER-PARSE` (Medium blocker)
- Problem:
  - Filtered `vast_search` queries can still fail at parse time instead of returning filtered offers.
- Counter-proof:
  - Query:
    - `rentable=true dph_total<=2 gpu_ram>=40 secure_cloud=true`
  - Returned:
    - `Expecting value: line 1 column 1 (char 0)`
- Implication:
  - The search helper is brittle for structured filtering and cannot currently be trusted as the only selection surface.

#### 24) `ISS-TRACE-ROOTCAUSE-NOISY-CONTEXT` (Medium blocker)
- Problem:
  - `trace_root_causes` can still return irrelevant historical causes when given a fresh observed runtime error.
- Counter-proof:
  - Observed workflow error `workflow_input_ref_slot_missing`
  - `trace_root_causes(2bfd52aa4a9baa2d)` returned an older debug-runtime trace repro event instead of a workflow-local cause
- Implication:
  - Root-cause tracing is operational, but not yet trustworthy as a precise local failure explainer without additional context filtering.

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
9. [todo] Tools tab inventory parity:
   - authoritative total count versus rendered total
   - category reconciliation for hidden/uncategorized tools
   - mismatch warning when UI count diverges from runtime
10. [todo] Workflow flow chart navigation:
   - drag background to pan
   - wheel/pinch zoom
   - fit/reset viewport controls
11. [todo] GPU Fleet operator surface:
   - stronger phase/readiness presentation
   - clearer active-instance controls and guidance
   - cost semantics for stop/destroy
12. [todo] GPU Fleet live telemetry feed:
   - instance-scoped activity grouping
   - expandable detail rows from existing Vast MCP outputs
13. [todo] FelixBag visual lens system:
   - filter chips / saved views
   - human-facing catalog triage over semantic substrate
14. [todo] Council remote-slot visibility:
   - show when a slot is backed by a remote GPU attachment
   - link attached slots back to GPU Fleet state
   - surface attachment health inline on the card
15. [todo] Environment tab foundation:
   - workflow-backed browser-native habitat shell
   - state/output/artifact panes
   - integrated trace/debug visibility
16. [todo] Environment render contract:
   - normalize workflow/runtime projection for environment views and habitat objects
   - keep first pass frontend-only over existing runtime truth
17. [todo] Environment export surface:
   - export/promote actions in the Environment tab
   - distinguish runtime, artifact, and interface outputs
18. [todo] Environment deep control surface:
   - node-level drill routing
   - model/provider focus where present
   - trace/artifact/habitat-object focus actions inside the shell
19. [todo] Environment doc/artifact arbitration:
   - linked FelixBag docs and produced artifact browser
   - open/read/focus flows that preserve environment context
20. [todo] Environment shared operator control:
   - shell state usable by both manual operator actions and assistant-directed actions
   - no split between “assistant path” and “human path”
21. [todo] Environment operator kernel:
   - focus/sample/act/branch/trace/promote controls
   - visible god-mode ledger with actor attribution

## Pending Live Validation
- Deployed runtime commit `1fed2ba` contains the remote-slot Vast pivot.
- Current live proof:
  1. `vast_rent` returns `api_port`, `console_url`, and attach-oriented guidance.
  2. `vast_ready` reports `api_server_url`, `port_exposed`, `support_matrix`, and `usable_families`.
  3. The remaining runtime validation target is end-to-end remote-slot attachment after the remote API server is fully reachable from the Space.
  4. Recent live audit also surfaced non-Vast runtime regressions in workflow tool-node arg plumbing and workflow execution auditability.
- Next narrow validation target, before more frontend work:
  1. remote champion API server reaches healthy/listening state on the rented GPU
  2. local attach via `vast_load_model` produces a real Council slot
  3. attached slot succeeds through normal slot paths:
     - `invoke_slot`
     - `agent_chat`
     - `compare`
     - workflow usage

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
