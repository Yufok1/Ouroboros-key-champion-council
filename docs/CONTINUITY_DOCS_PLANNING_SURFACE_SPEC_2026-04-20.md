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

## Guard Rails

1. docs do not outrank live theater, blackboard, snapshot, or corroboration
2. docs should not be a side panel only
3. planning docs must be queryable and updateable from the same operator path
4. continuity restore should recommend the current planning index before widening into older archive prose
5. FelixBag coverage gaps must be treated as operational debt, not ignored

## Next Practical Slice

1. recommend this doc from continuity restore
2. expose `docs_packet` in `output_state`
3. render `docs_packet` in text-theater blackboard
4. checkpoint and mirror this planning doc into FelixBag
5. add a later sync pass that lifts the remaining repo docs into FelixBag so search quality stops depending on partial corpus coverage
