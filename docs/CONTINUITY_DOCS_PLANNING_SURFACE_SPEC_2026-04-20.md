# Continuity Docs Planning Surface Spec 2026-04-20

Repo: `D:\End-Game\champion_councl`

Purpose:

- turn the `docs/` corpus into an updateable planning surface instead of a loose evidence shelf
- keep repo docs, FelixBag docs, continuity restore, and blackboard/query-work on one operator path
- give the state machines one exact docs/plans packet they can read without inventing a second authority plane

## Bottom Line

The docs lane should work like this:

1. repo docs remain the local authored source surface
2. FelixBag carries the queryable and checkpointable planning mirror
3. continuity restore recommends the current docs landscape index first
4. `output_state` carries a bounded `docs_packet`
5. text-theater blackboard renders that packet as part of the live planning surface

This is not a replacement for query-thread or blackboard.

It is the planning/material-reference packet that docks to them.

## Current Audit

Audit taken on `2026-04-20`.

- repo markdown docs in `docs/`: `140`
- repo files total in `docs/`: `163`
- FelixBag docs currently surfaced under `docs/`: `77`

Current truth:

- the FelixBag seam is real
- the docs panel already searches `bag_search_docs`
- the docs lane is still partial and still too lazy-loaded
- docs alignment currently shows up mostly as:
  - `docs_context_kind`
  - `result_count`
  - `active_doc`
  - a coarse `aligned/mismatch/empty` band

That is not enough for planning.

## Corroboration 2026-04-21

Continuity and runtime help now corroborate the docs lane as a real query substrate instead of only a planning idea.

Confirmed on this pass:

- `continuity_restore(...)` returned `recommended_docs` anchored on this planning spec, the instantiation prompt, the environment memory index, and the active trajectory lane
- `output_state.docs_packet` is normalized server-side as a bounded planning/material packet with `band`, `summary`, `active_doc`, `continuity_index`, `top_results`, and `update_lane`
- `env_help(topic='docs_packet')` is registered as the operator-facing explanation for that surface
- the environment help registry already points the live update lane at:
  - `bag_search_docs(prefix='docs/')`
  - `bag_read_doc`
  - `file_checkpoint`
  - `file_write` / `file_edit`
- browser/runtime continuity also treats docs as a carried face beside `continuity_packet`, not as a disconnected side shelf
- operator-facing naming posture can also be carried here when it affects continuity recovery, provided it stays explicitly subordinate to canon runtime names

That means the current honest state is:

- repo docs are the authored source surface
- FelixBag is the queryable/checkpointable mirror
- continuity can recommend the relevant docs lane during reacclimation
- `docs_packet` is the bounded operator packet for the live planning face

What remains incomplete is coverage, not the existence of the surface. Partial FelixBag mirror coverage is still operational debt.

## Required Planning Packet

The live docs packet should carry:

- `band`
- `posture`
- `summary`
- `expected_context_kind`
- `context_kind`
- `context_id`
- `query`
- `result_count`
- `active_doc`
- `continuity_index`
- `search_prefix`
- `search_limit`
- `top_results`
- `update_lane`

## Update Lane

The planning surface must be updateable through FelixBag doc/file operations, not only readable through search.

Use this lane:

1. `bag_search_docs` to surface candidate planning docs
2. `bag_read_doc` or `file_read` to inspect the current planning document
3. `file_checkpoint` before changes
4. `file_write` or `file_edit` to update the FelixBag mirror
5. `bag_read_doc` / `file_read` again to verify the written state

If a repo doc is changed, the matching FelixBag planning doc should be refreshed on the same pass whenever that doc is part of the active continuity lane.

## Canonical Current Index

This document is the continuity/docs planning index for the current sprint.

Read it together with:

- `docs/CODEX_CHAMPION_COUNCIL_INSTANTIATION_PROMPT_2026-04-13.md`
- `docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md`
- `docs/ASSOCIATIVE_SYSTEMS_CONVERGENCE_BRIEF_2026-04-20.md`
- `docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md`
- `docs/ARCHIVED_LIVE_PAIRED_STATE_RESOURCE_SPEC_2026-04-15.md`
- `docs/QUERY_MIRROR_UNIFICATION_SITREP_2026-04-15.md`
- `docs/BLACKBOARD_QUERY_PROCUREMENT_DEEP_DIVE_2026-04-13.md`
- `docs/ENVIRONMENT_MEMORY_INDEX.md`
- `docs/COQUINA_SKIN_SERVICE_CONTINUITY_NOTE_2026-04-22.md`
- `docs/COORDINATED_ACCELERATION_SOLUBLE_SURFACES_REVELATION_2026-04-22.md`
- `docs/ASSOCIATIVE_SURFACES_CONTINUITY_INDEX_2026-04-22.md`
- `docs/STRATIFIED_ROTATIONAL_CONTAINMENT_CONTINUITY_MODEL_2026-04-23.md`
- `docs/brotology/BROTOLOGY_FIELD_OPERATIONS_MANUAL_2026-04-22.md`
- `docs/brotology/BROTOLOGISTS_LOG_2026-04-23.md`
- `docs/brotology/HIGH_YIELD_BROSPECULATION_CANYON_SPAN_SIMULATION_PRIMITIVES_REPORT_2026-04-23.md`
- `docs/brotology/CARRIER_FORTRESS_CANYON_SPAN_PLANNING_DOSSIER_2026-04-23.md`
- `docs/brotology/CANYON_SPAN_PRIMITIVE_REGISTRY_SPEC_2026-04-23.md`
- `docs/brotology/EA_DEVELOPERS_BROTOLOGY_FIELD_REPORT_SPEC_2026-04-22.md`
- `docs/brotology/EA_DEVELOPERS_REPORT_WEEK_01_2026-04-22.md`
- `docs/CONTINUOUS_OBSERVATION_DREAMER_GOVERNANCE_NOTE_2026-04-22.md`

## Guard Rails

1. docs do not outrank live theater, blackboard, snapshot, or corroboration
2. docs should not be a side panel only
3. planning docs must be queryable and updateable from the same operator path
4. continuity restore should recommend the current planning index before widening into older archive prose
5. FelixBag coverage gaps must be treated as operational debt, not ignored
6. invocation-only operator aliases may be documented for recovery, but they must never replace neutral default address or mutate runtime/help/API names

## Next Practical Slice

1. recommend this doc from continuity restore
2. expose `docs_packet` in `output_state`
3. render `docs_packet` in text-theater blackboard
4. checkpoint and mirror this planning doc into FelixBag
5. add a later sync pass that lifts the remaining repo docs into FelixBag so search quality stops depending on partial corpus coverage
