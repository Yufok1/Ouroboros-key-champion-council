# Master Guides Index

Date: 2026-03-05
Scope: Plugged-model operations, MCP-only evaluation, debug-system operation

## Single Source of Truth

- Canonical FelixBag schema key:
  - `eval/schemas/plugged_model_debug_schema_pack_2026-03-05`
- Canonical checkpoint:
  - `bag_checkpoint:eval/schemas/plugged_model_debug_schema_pack_2026-03-05:1772747778399`

Use this index first, then run from the playbook and contracts below.

## Guide Set

1. `self_deploy/docs/MASTER_OPERATIONS_PLAYBOOK.md`
   - End-to-end operating runbook.
   - Stable provider pool.
   - MCP tool families and when to use each.
   - Required eval order and stop/go gates.

2. `self_deploy/docs/MASTER_EVAL_CONTRACTS.md`
   - Strict JSON report schemas.
   - Pass/fail rules.
   - Constraint normalization rules (what is expected vs what is a failure).

## Primary Evidence Keys

- Debug system live validation:
  - `eval/debug_system/mcp_only_live_validation_2026-03-05T22-19-00`
- Provider availability sweep:
  - `eval/providers/provider_availability_sweep_2026-03-05T22-24-00`
- Curated provider pool:
  - `eval/providers/provider_pool_curated_2026-03-05T22-27-00`
- Full batch debug eval:
  - `eval/debug_mode/full_batch_mcp_2026-03-05`
- Variable matrix:
  - `eval/debug_mode/variable_matrix_2026-03-05`
- Dreamer assist pattern:
  - `eval/debug_mode/dreamer_assist_2026-03-05`
- Plugged-model stress baseline:
  - `eval/orchestration/stress_audit_plugged_models_2026-03-04`

## Operating Invariants

- MCP tools only for live eval/debug runs.
- Provider plugs only (no local hub download/plug for this track).
- Stable operator pool only unless running explicit provider discovery.
- Treat self-invocation guard as expected constraint, not regression.
- Treat provider HTTP errors as provider-route failures unless reproduced across stable pool.

## Recommended Reading Order

1. `MASTER_OPERATIONS_PLAYBOOK.md`
2. `MASTER_EVAL_CONTRACTS.md`
3. Historical evidence keys listed above

