# Fractal Query Continuity Surface Spec 2026-04-21

Repo: `D:\End-Game\champion_councl`

Purpose:

- make context compression summaries and associative chat transcript recall operational without treating memory as authority
- dock archive continuity beside the docs planning packet and live blackboard query spine
- give agents a small packet they can use as a resume face before they return to live theater/source corroboration

## Bottom Line

The fractal query surface is not a new memory plane.

It is a bounded packet stack:

1. `docs_packet` is the planning/material face over repo docs and FelixBag docs
2. `continuity_packet` is the archive/transcript face over `continuity_restore`
3. blackboard/query thread is the visible live query-work face
4. `output_state` is the orienting crane that carries the faces together
5. live theater, source code, and scoped reports remain the authority path

The Rubik-style sequencer metaphor fits as a rotation model: each packet face can be inspected and advanced, but no face becomes the cube.

## Continuity Packet Contract

`continuity_packet` should carry:

- `active`
- `band`
- `posture`
- `summary`
- `packet_kind`
- `query_key`
- `objective_id`
- `objective_label`
- `subject_key`
- `current_pivot_id`
- `archive_resume_only`
- `task_complete_message`
- `open_loops`
- `recent_pressures`
- `recent_user_messages`
- `recent_assistant_messages`
- `hot_tools`
- `hot_terms`
- `resume_hints`
- `recommended_docs`
- `best_session_id`
- `best_session_path`
- `matched_session_count`
- `refreshed_ts`
- `pending`
- `help_lane`
- `next_reads`
- `corroboration_surfaces`
- `paired_state_status`
- `update_lane`

## Authority Guard

Continuity restore is archive-side reacclimation only.

The packet can seed:

- what docs to read next
- what pivot was active
- what file/source seam was hot
- what user pressure remains open
- what live corroboration should happen next

The packet cannot decide live truth by itself.

Fresh order remains:

1. text theater render or embodiment
2. browser-visible capture when needed
3. consult/blackboard query-work
4. text theater snapshot
5. scoped report or contracts
6. raw shared_state only as last resort

## Naming Alignment

Do not resurrect old abstract labels as independent systems.

Use the current mapped terms:

- "adrenaline" maps to `resume_focus` / `surface_prime` pressure
- "shutter" maps to capture boundary / reset boundary
- "Tinkerbell" points attention and interrupt candidates
- "Pan" measures/supports/routes against physical or procedural posture
- "Rubik sequencer" means bounded packet rotation over one query spine

## Update Lane

The live lane is:

1. `continuity_restore(summary=<objective + subject + pivot>)`
2. `output_state.continuity_packet`
3. text-theater blackboard render
4. `env_report(report_id='paired_state_alignment')`
5. `bag_search_docs(prefix='docs/')`
6. repo docs and FelixBag docs are updated with checkpoints when the planning surface changes

## Current Slice

The 2026-04-21 implementation slice wires:

- browser-side continuity packet state
- `output_state.continuity_packet`
- text-theater blackboard continuity lines
- server-side report normalization
- this planning spec as the doctrine anchor

Next work is to make the FelixBag mirror carry this spec and the docs planning spec as checkpointed planning resources.

## Corroboration 2026-04-21

This is now corroborated by the live continuity restore shape, not only by doctrine text.

On the current restore lane:

- `continuity_restore(...)` surfaced `recommended_docs`
- the recommended docs set includes the docs planning spec, the instantiation prompt, and the environment memory index
- the recovered packet carried `priority_pivots`, `recommended_docs`, `help_lane`, `next_reads`, and `corroboration_surfaces`
- the docs face remained distinct from the archive face, which confirms the intended split:
  - `docs_packet` = planning/material face
  - `continuity_packet` = archive/transcript face
  - live theater/source/report = authority path

So the current honest read is:

- docs are operationalized as a queryable planning substrate
- continuity can recommend and carry that substrate during reacclimation
- the docs surface still must be re-corroborated against live theater/query work before it is treated as current truth
