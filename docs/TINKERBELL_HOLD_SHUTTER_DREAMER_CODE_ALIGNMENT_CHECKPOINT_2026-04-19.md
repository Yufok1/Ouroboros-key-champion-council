# Tinkerbell HOLD Shutter Dreamer Code Alignment Checkpoint 2026-04-19

Purpose: leave one code-backed restart note so the next session can resume from the real repo state instead of from drifted memory.

## Verified live seam

- Current continuity pivot: `operative_memory_alignment`
- Current live sequence: `query_seq/live/character_runtime::mounted_primary/selection_orientation/bone:character_runtime::mounted_primary:hips`
- Live corroboration was re-run on 2026-04-19 through:
  - `env_read(query='text_theater_embodiment')`
  - `env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)`
  - `env_read(query='text_theater_snapshot')`
  - `capture_supercam`
  - `env_read(query='supercam')`

## What is real in code now

### 1. `output_state` is real and already carries the orienting field

Verified in [static/main.js](/D:/End-Game/champion_councl/static/main.js:34312).

Current emitted child blocks include:

- `placement`
- `trajectory_correlator`
- `continuity_cue`
- `tinkerbell_attention`
- `field_disposition`
- `watch_board`
- `equilibrium`
- `drift`
- `next_reads`
- `receipts`
- `freshness`
- `confidence`
- `sources`
- `pan_probe`

Important current behavior:

- `equilibrium` is scored from sequence/pivot/objective/subject presence, mirror lag, bundle mismatch, parity contamination, docs alignment, subject/focus mismatch, and next-read availability.
- `trajectory_correlator` and `continuity_cue` are already present, not merely speculative doctrine.
- `continuity_cue` currently surfaces `Run Continuity Drill` rather than mutating the system.

### 2. `tinkerbell_attention` is now live as a first-pass pointer layer

Verified in:

- [static/main.js](/D:/End-Game/champion_councl/static/main.js:34322) `_envBuildTinkerbellAttention(...)`
- [static/main.js](/D:/End-Game/champion_councl/static/main.js:35075) `tinkerbell_attention: tinkerbellAttention`
- [server.py](/D:/End-Game/champion_councl/server.py:4728) `_env_report_normalize_output_state(...)`
- [server.py](/D:/End-Game/champion_councl/server.py:12128) `_dreamer_snapshot_oracle_context(...)`
- [scripts/text_theater.py](/D:/End-Game/champion_councl/scripts/text_theater.py:1207) `_output_state_tinkerbell_attention(...)`

Current live contract:

- `band`
- `summary`
- `attention_kind`
- `attention_target`
- `attention_confidence`
- `hold_candidate`
- `active_pointer`
- `prospect_candidates`

Current scope:

- this is a derived pointer layer over the existing orienting field
- it is visible in facility mirror, text-theater consult, blackboard text, env-report normalization, and Dreamer oracle context
- it is still pointer-only; it does not mutate embodiment truth or create a new authority plane

### 3. Dreamer already reads a meaningful subset of the orienting field

Verified in:

- [server.py](/D:/End-Game/champion_councl/server.py:12041) `_dreamer_snapshot_query_thread(...)`
- [server.py](/D:/End-Game/champion_councl/server.py:12086) `_dreamer_snapshot_oracle_context(...)`
- [server.py](/D:/End-Game/champion_councl/server.py:12941) `_dreamer_rank_proposals(...)`

Current Dreamer intake already includes:

- query-thread sequence, segment, pivot, objective, visible read, anchor rows, next reads, help lane
- oracle/output-state summary, equilibrium band/signals, drift band, watch alerts, field disposition, pan band, contact bias, support role, placement subject/objective/seam/evidence/next

Current ranker already uses:

- `watch_alerts`
- `pan_band`
- `contact_bias`
- `support_role`
- `current_pivot_id`

Important correction:

- Dreamer now ingests the Tinkerbell pointer fields in oracle context, but the current proposal ranker does not yet score directly from them

### 4. HOLD is real, but still mostly a tool and UI seam

Verified in:

- [static/main.js](/D:/End-Game/champion_councl/static/main.js:60303)
- [static/main.js](/D:/End-Game/champion_councl/static/main.js:60320)
- [static/main.js](/D:/End-Game/champion_councl/static/main.js:68571)

Current real pieces:

- `hold_yield`
- `hold_resolve`
- HOLD result formatting in UI/debug paths
- warnings around missing or ambiguous `hold_id`

Current missing piece:

- HOLD is not yet a first-class blackboard/query/output-state row family

### 5. Snapshot and shutter surfaces exist, but the generic freeze packet does not

Verified in:

- [static/main.js](/D:/End-Game/champion_councl/static/main.js:34191)
- [static/main.js](/D:/End-Game/champion_councl/static/main.js:34212)
- [static/main.js](/D:/End-Game/champion_councl/static/main.js:35270)

Current real capture/shutter-adjacent surfaces:

- `text_theater_snapshot`
- `text_theater_embodiment`
- `text_theater_view`
- `supercam`
- `pan_probe.capture_surfaces`
- camera snapshot patching for text-theater bundle state

Important correction:

- local generic packet fields such as `shutter_close`, `shutter_open`, `latched_hold_id`, and `resume_mode` are not implemented in code yet
- the only literal `freeze_auth_enabled` found in `static/main.js` is part of the Technolit reactor/trust surface, not the general HOLD partner runtime

## What is not in code yet

The following terms are present in docs and design work, but not yet implemented as live runtime fields:

- `shutter_close`
- `shutter_open`
- `latched_hold_id`
- `resume_mode`

Main remaining gaps now:

- HOLD is still not a carried row family
- shutter/freeze packet fields are still absent
- the Bell/Tink naming split is still doctrinal, not reflected in runtime naming
- Dreamer proposal ranking does not yet use the new pointer directly

## Clean role split to preserve

This split is still the most code-honest reading of the repo:

- `output_state` = orienting crane
- `equilibrium` = settling gauge inside `output_state`
- `watch_board` = urgency/intercept board inside `output_state`
- `trajectory_correlator` = intended vs actual sequence grading
- `continuity_cue` = visible reorientation bell
- `Tinkerbell` = first-pass pointer/attention layer over `output_state`
- `HOLD` = intervention latch
- `freeze/shutter` = writer-segment capture contract to be added, not a whole-runtime freeze
- `Dreamer` = bounded proposer/scorer over truthful observations
- `Pan` = router/dispatch layer over support and actuation truth

## No-surprise implementation order

When work resumes, keep the slices in this order:

1. Pressure-test the live `tinkerbell_attention` field against real theater sessions
2. Keep Dreamer proposal-only; do not let it mutate embodiment truth directly
3. Promote HOLD into a visible row family
4. Add shutter packet fields only after HOLD and Tinkerbell are visible
5. Decide whether Bell/Tink should stay doctrinal names or become runtime aliases

Reason:

- `output_state` already exists and is the correct carrier
- Dreamer already reads the carrier and now ingests the pointer
- HOLD already exists as a tool seam
- shutter/freeze should attach to those existing seams rather than become a second hidden runtime

## Current cautions

From the last live corroboration pass:

- continuity is restored and live again
- the current sequence is valid
- `output_state` moved from `aligned` to `watch` after `supercam`
- the active causes were `mirror lag` and `subject/focus mismatch`

This is not a conceptual blocker. It is just the current live caution state.

## Resume recipe

When work resumes, do not start from broad theory. Start here:

1. Re-run continuity if needed
2. Re-read this checkpoint doc
3. Re-open:
   - [static/main.js](/D:/End-Game/champion_councl/static/main.js:34312)
   - [static/main.js](/D:/End-Game/champion_councl/static/main.js:34322)
   - [server.py](/D:/End-Game/champion_councl/server.py:12041)
   - [server.py](/D:/End-Game/champion_councl/server.py:12086)
   - [server.py](/D:/End-Game/champion_councl/server.py:4720)
   - [server.py](/D:/End-Game/champion_councl/server.py:12941)
   - [scripts/text_theater.py](/D:/End-Game/champion_councl/scripts/text_theater.py:1207)
   - [docs/PHYSICAL_DIAGNOSTIC_FACILITY_OF_FACILITIES_BLUEPRINT_2026-04-18.md](/D:/End-Game/champion_councl/docs/PHYSICAL_DIAGNOSTIC_FACILITY_OF_FACILITIES_BLUEPRINT_2026-04-18.md)
4. Verify what the live pointer chooses in a real posture session
5. Then thread HOLD and shutter packeting

That should keep the next session in the code-backed lane instead of reopening old ambiguity.
