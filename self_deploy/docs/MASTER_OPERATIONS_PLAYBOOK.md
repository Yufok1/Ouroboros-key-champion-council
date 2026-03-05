# Master Operations Playbook

Date: 2026-03-05
Mode: MCP-only
Purpose: One operational guide for plugged-model evaluation and debug-system execution.

## 1) Mission

Run deterministic, evidence-backed evaluations of plugged provider models while using the debug system to classify real failures vs expected constraints. Persist every run to FelixBag with strict schemas.

## 2) Stable Operator Pool

Current stable pool for debug/operator loops:

- `slot 0`: `llama4-maverick-provider`
  - Route: `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8`
- `slot 2`: `qwen3-next80b-provider`
  - Route: `Qwen/Qwen3-Next-80B-A3B-Instruct`
- `slot 3`: `qwen3-coder-480b-provider`
  - Route: `Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8`

Pool source key:

- `eval/providers/provider_pool_curated_2026-03-05T22-27-00`
- Operational note:
  - That key records `slot 6` as `conditional`; default master runs use only `slot 0,2,3` unless explicitly testing conditional models.

Rule:

- Do not run master debug loops on quarantined providers.
- Quarantined models can be used only in explicit provider discovery tests.

## 3) Required Execution Order

Always run stages in this order:

1. Provider preflight
2. Variable matrix
3. Full-batch MCP eval
4. Live debug-system gate
5. Optional dreamer route-assist pass

Execution order source:

- `eval/schemas/plugged_model_debug_schema_pack_2026-03-05`

## 4) Stage Runbooks

### Stage 1: Provider Preflight

Objective:

- Confirm route health before any deep eval.

Required checks per active slot:

- `invoke_slot` strict JSON probe
- `agent_chat` strict JSON probe
- Retry once when failure could be transient

Classification outcomes:

- `stable`
- `pass_with_transient`
- `conditional`
- `fail`

Persist:

- `eval/providers/provider_availability_sweep_<timestamp>`

### Stage 2: Variable Matrix

Objective:

- Validate debug-system behavior on known edge conditions.

Core variables:

- `self_invocation_guard`
- `provider_http_400` or provider route failures
- `iteration_fragility`
- `provider_instability_500`
- `platform limitations` (for example nested workflow restrictions)

Pass condition:

- Debug system classifies each variable to the correct category with explicit evidence.

Reference:

- `eval/debug_mode/variable_matrix_2026-03-05`

### Stage 3: Full-Batch MCP Eval

Objective:

- Run complete toolchain-oriented eval and produce issue list with severity.

Minimum components:

- Provider health checks
- Agent debug-chain checks
- Session retrieval checks
- Feed/telemetry alignment checks

Output must include:

- Test IDs
- Exact calls
- Result (`pass`, `partial_fail`, `fail`, `mismatch_confirmed`, etc.)
- Concrete evidence

Reference:

- `eval/debug_mode/full_batch_mcp_2026-03-05`

### Stage 4: Live Debug-System Gate

Objective:

- Confirm end-to-end debug stack operation on live runtime.

Must validate:

- Nested telemetry in `feed` (`external`, `agent-inner`, and nested tool rows)
- `cascade_*` diagnostics functions
- `symbiotic_interpret`
- `forensics_analyze`
- `trace_root_causes`
- `hold_yield` and `hold_resolve`

Reference:

- `eval/debug_system/mcp_only_live_validation_2026-03-05T22-19-00`

### Stage 5: Dreamer Assist (Optional)

Objective:

- Use dreamer route projection to prioritize branches, then confirm with deterministic probes.

Policy:

- Dreamer is advisory.
- Deterministic probe evidence is final.

Pattern:

- Stage 1: `imagine()` route proposal
- Stage 2: deterministic probes (`slot_info`, `invoke_slot`, etc.)
- Stage 3: normalized diagnosis
- Stage 4: persist report

Reference:

- `eval/debug_mode/dreamer_assist_2026-03-05`

## 5) MCP Tool Families and Facilities

Use these families intentionally:

- Core probe and state:
  - `get_status`, `list_slots`, `slot_info`, `invoke_slot`, `agent_chat`
- Debug telemetry:
  - `observe`, `feed`, `get_cached`
- Debug interpretation and diagnostics:
  - `symbiotic_interpret`, `forensics_analyze`, `trace_root_causes`
- Cascade lattice diagnostics:
  - `cascade_system`, `cascade_data`, `cascade_graph`, `cascade_record`
- Escalation and decision instrumentation:
  - `hold_yield`, `hold_resolve`
- Evidence persistence:
  - `bag_put`, `bag_read_doc`, `bag_search_docs`, `bag_checkpoint`

## 6) Failure Taxonomy

Classify every issue under one class:

- `provider_route_error`
  - HTTP 4xx/5xx from provider route
- `provider_output_contract_failure`
  - Empty response, placeholder text, or non-JSON when strict JSON required
- `expected_constraint`
  - Self-invocation block, slot-not-plugged guard, or other designed guardrail
- `budget_fragility`
  - Incomplete chain due to low iterations/tokens
- `platform_limitation`
  - Known unsupported behavior (for example nested tool limitations)
- `telemetry_semantics_mismatch`
  - Channel semantics differ (for example `feed` vs UI activity stream)

## 7) Regression Gates

Do not pass a run if any of these fail:

- Any stable operator slot fails strict JSON `agent_chat` twice in a row
- Debug gate cannot produce nested telemetry evidence
- Variable matrix misclassifies expected constraints as regressions
- Final report omits required schema keys

## 8) Artifact Naming and Storage

Use predictable key patterns:

- Provider runs:
  - `eval/providers/provider_availability_sweep_<timestamp>`
- Debug runs:
  - `eval/debug_system/<run_id>`
- Full batch:
  - `eval/debug_mode/full_batch_mcp_<date>`
- Consolidated schema packs:
  - `eval/schemas/<schema_pack_id>`

Always checkpoint each final artifact:

- `bag_checkpoint:<key>:<timestamp>`

## 9) Exit Criteria for “Ready to Debug Live Systems”

System is ready only when all conditions are true:

- Stable provider pool verified in current runtime
- Variable matrix all pass
- Full-batch eval complete with no unclassified failures
- Live gate pass proves nested telemetry and diagnostics stack
- Artifact + checkpoint persisted for this run
