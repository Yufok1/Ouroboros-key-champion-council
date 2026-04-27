# Opus Reacclimation Sitrep 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- update Opus on the text-theater / blackboard / glyph-surface work since the 2026-04-10 sitrep
- separate what is now live in source/runtime from what is still doctrine
- define what should be checkpointed later without creating the checkpoint yet

Late-day supersession note:

- this file remains valid for runtime-contract corroboration
- the late 2026-04-11 doctrine correction on alphanumeric embodiment is captured in [OPUS_DATA_FIRST_TEXT_THEATER_SITREP_2026-04-11.md](/F:/End-Game/champion_councl/docs/OPUS_DATA_FIRST_TEXT_THEATER_SITREP_2026-04-11.md)
- when the two conflict on glyph/body direction, trust the newer data-first sitrep

Related docs:

- [OPUS_SITREP_2026-04-10.md](/F:/End-Game/champion_councl/docs/OPUS_SITREP_2026-04-10.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)
- [TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md)

## Bottom Line

Since the 2026-04-10 baseline, the repo has moved in three real directions:

1. `shared_state.blackboard` is now a live structured row pool, not only a plan
2. `shared_state.text_theater_profiles` and `shared_state.text_theater_control` now exist as first-class contracts
3. the text-theater/glyph work has been clarified into a stronger doctrine:
   - one glyph-box model
   - default character cell as the buoyant reference surface
   - punctuation/line/corner glyphs as orientation scaffold
   - glyph/state-space consumers must consume existing workbench/gizmo/batch-pose truth, not invent a second articulation plane

The text renderer itself is **not finished**. The programmable path remains the active lane, but the exact readable granular implementation is still under active repair.

## What Is Now Corroborated In Source

### 1. Blackboard contract is live

Current source/runtime now carry:

- `shared_state.blackboard`
- `text_theater_snapshot.blackboard`
- stable row ids
- row families
- row anchors
- tolerance states
- priorities
- sticky timing
- session weighting
- optional traces

Current live families observed through `env_read(query='shared_state')`:

- `balance`
- `contact`
- `controller`
- `corroboration`
- `load`
- `route`
- `session`
- `support`

Live row count observed at handoff time: `15`

### 2. Text-theater profile registry is live

Current source/runtime now carry:

- `shared_state.text_theater_profiles`
- 7-family registry
- first-wave ids
- deferred ids
- row-admission policies
- surface defaults
- designation contract stating that tolerance/color semantics stay on blackboard rows, not profiles

First-wave families currently live:

- `operator_default`
- `mechanics_telemetry`
- `route_telestrator`
- `spectacle_showcase`

Deferred families currently live in registry:

- `drafting_authoring`
- `archive_inspection`
- `alert_high_contrast`

Deferred note also exists for:

- `agent_narration`

### 3. Text-theater control surface is live

Current source/runtime now carry:

- `shared_state.text_theater_control`
- browser-side control setter: `text_theater_set_view`
- standalone text theater remote-control ingestion

Current control fields:

- `view_mode`
- `section_key`
- `diagnostics_visible`
- `revision`
- `updated_ts`
- `source`

This is the actual bridge for agent/runtime-driven text-theater view changes.

### 4. Camera parity path is partially formalized

Source now confirms:

- camera sync reasons explicitly attach text-theater bundles for:
  - `camera:manual:end`
  - `camera:manual:change`
  - `camera:manual:wheel`
  - `camera:workbench-shot:*`
  - `camera:turntable*`
  - `camera:preset:*`
- `_env3DCommitManualCamera(...)` increments `cameraPulseSeq`
- workbench shot presets commit through `_env3DCommitManualCamera(...)`

This means the browser/server parity lane is no longer limited to drag rotation only. Shot presets and wheel zoom are now threaded into the same freshness lane.

### 5. Workbench remains the articulation authority

The repo still already has the real articulation surface:

- `workbench_set_bone`
- `workbench_set_pose`
- `workbench_set_pose_batch`
- `workbench_set_gizmo_mode`
- `workbench_set_gizmo_space`
- `workbench_select_bone`
- `workbench_select_chain`
- `workbench_select_controller`
- `workbench_frame_part`

Text theater already mirrors that state through diagnostics/snapshot export.

What does **not** exist yet is:

- glyph rig
- glyph articulation registry
- workbench-to-glyph adapter
- glyph field continuity solver

So the articulation authority exists; the glyph/state-space consumer does not.

## New Doctrine Added Since The Last Opus Sitrep

### 1. Blackboard redo doctrine

Captured in [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md):

- previous blackboard attempt failed both architecturally and product-wise
- blackboard must stay off the live camera/motion hot path
- correct shape is:
  - stable row pool
  - procedural collation/layout
  - separate consumers for text theater and web theater

### 2. Spatial bridge doctrine

Captured in [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md):

- text theater is a bridge/interchange layer, not mere terminal fluff
- diagnostic cube, text-rendered 3D objects, hybrid text skins, and telestrator overlays are downstream consumers
- composite/faceted consumers are the reusable abstraction, not just “cube”

### 3. Profile doctrine

Captured in [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md):

- 7 base profile families
- 4 first-wave implementations
- row-admission is part of the contract
- composite/faceted consumer support is reserved in the design
- spectacle/showcase is constrained so it cannot drift into empty chrome

### 4. CASCADE/HOLD blackboard integration doctrine

Captured in [TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md):

- CASCADE and HOLD should attach as row families, not bespoke renderers
- proposed additional row families:
  - `signal`
  - `causation`
  - `tape`
  - `hold`
  - `data_hygiene`
- discoverability seam still exists: environment help is present, but `env_help` naming is not exposed cleanly

### 5. Glyph orientation / buoyant surface doctrine

Captured in [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md):

- one canonical character box
- default fixed-width character cell is the common buoyant reference surface
- multiple focus levels over the same glyph occupancy:
  - `reference`
  - `fused`
  - `granular`
  - `field`
- direct keyboard characters are preferred when they already fit honestly
- punctuation/line/corner glyphs are first-class geometry/orientation primitives

### 6. Glyph articulation doctrine

Captured in [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md):

- treat glyphs as rigged micro-subjects
- treat glyph fields as batch-poseable surface subjects
- map workbench/gizmo/batch pose onto glyph articulation instead of building a second control plane

## What Is Live In Runtime Right Now

Corroborated via:

- `get_help('environment')`
- `get_help('symbiotic_interpret')`
- `get_help('hold_yield')`
- `env_read(query='shared_state')`

### 1. Environment/help surfaces

Environment help is seeded and exposes:

- `env_spawn`
- `env_mutate`
- `env_remove`
- `env_read`
- `env_control`
- `env_persist`
- workstation tools

### 2. CASCADE/HOLD tools are real and auditable

Confirmed:

- `symbiotic_interpret` is live as a signal-normalization/interpretation lane
- `hold_yield` is live as a structured oversight/audit lane with non-blocking MCP behavior by default

### 3. Live shared state corroborates the new contracts

Observed live:

- `text_theater_control`
- `text_theater_profiles`
- `blackboard`
- mounted runtime command surface already exposing workbench/builder commands

The mounted runtime command surface still includes the articulation verbs the glyph consumer will eventually need.

## Dirty Worktree Scope

### Modified code files

- [persistence.py](/F:/End-Game/champion_councl/persistence.py)
- [scripts/text_theater.py](/F:/End-Game/champion_councl/scripts/text_theater.py)
- [server.py](/F:/End-Game/champion_councl/server.py)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js)
- [static/panel.html](/F:/End-Game/champion_councl/static/panel.html)
- [static/sw.js](/F:/End-Game/champion_councl/static/sw.js)

### Untracked docs

- [COMMERCIALIZATION_MAP_2026-04-11.md](/F:/End-Game/champion_councl/docs/COMMERCIALIZATION_MAP_2026-04-11.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)

### Untracked asset payloads

- `capture_probe`
- `static/assets/packs/kenney-graveyard-kit/Textures/`
- `static/assets/packs/kenney-mini-characters-1/Textures/`
- `static/assets/packs/kenney-mini-dungeon/Textures/`

These assets should not be casually mixed into the same checkpoint as the text-theater/blackboard doctrine unless they are intentionally part of the same slice.

## What The Modified Code Is Doing

### 1. `static/main.js`

Primary new responsibilities:

- builds and clones `text_theater_control`
- builds and exports `text_theater_profiles`
- builds and exports `blackboard`
- exposes `text_theater_set_view`
- threads camera-sync reasons into text-theater parity
- increments camera freshness on manual/preset camera commits

### 2. `scripts/text_theater.py`

Primary new responsibilities:

- expanded programmable text rendering infrastructure
- `blackboard` diagnostics section
- `profiles` diagnostics section
- remote-control ingestion from `text_theater_control`
- richer split/snapshot/theater/embodiment frame handling
- programmable text path on operator surfaces

Important caution:

- the programmable render path is still being tuned
- the doctrine is stronger than the current visual result
- renderer quality should not be treated as solved just because the contracts are in place

### 3. `server.py`

Primary new responsibilities:

- proxy support for `text_theater_set_view`
- environment-control payload classification for that command
- live-cache stale-camera merge guard still exists and still keys off `camera_pulse_seq`

### 4. `persistence.py`

Primary new responsibilities:

- local/HF snapshot copy/upload helpers refactored into thread-offloaded helpers
- tmpdir cleanup moved off the main async path

This is not directly text-theater doctrine, but it is part of the dirty checkpoint scope.

### 5. `static/panel.html` / `static/sw.js`

Primary new responsibilities:

- browser cache-bust for the current JS bundle (`131j`)

## Open Seams

1. The programmable text renderer is still unresolved
   - the user wants programmable larger text surfaces, not regression to tiny default terminal text
   - current doctrine is correct
   - current visual implementation is still under repair

2. The glyph articulation system is still doctrine, not implementation
   - articulation authority exists
   - glyph consumer/adapter does not

3. CASCADE/HOLD row families are specified but not yet threaded into the blackboard row pool

4. `env_help` discoverability is still weaker than it should be even though environment help exists

## Suggested Checkpoint Grouping Later

### Checkpoint A: blackboard/profile/control substrate

Include:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js)
- [server.py](/F:/End-Game/champion_councl/server.py)
- [scripts/text_theater.py](/F:/End-Game/champion_councl/scripts/text_theater.py)
- [static/panel.html](/F:/End-Game/champion_councl/static/panel.html)
- [static/sw.js](/F:/End-Game/champion_councl/static/sw.js)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)

### Checkpoint B: glyph/cascade doctrine

Include:

- [TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md)

### Checkpoint C: commercialization / strategy

Include separately if desired:

- [COMMERCIALIZATION_MAP_2026-04-11.md](/F:/End-Game/champion_councl/docs/COMMERCIALIZATION_MAP_2026-04-11.md)

### Checkpoint D: persistence/runtime cleanup

Consider separately:

- [persistence.py](/F:/End-Game/champion_councl/persistence.py)

### Asset payloads

Keep separate unless intentionally part of the same release:

- `capture_probe`
- `static/assets/packs/.../Textures/`

## What Opus Most Needs To Know

1. The blackboard contract is no longer hypothetical. It is live in `shared_state`.
2. The profile registry and text-theater control bridge are also live in `shared_state`.
3. The glyph-surface doctrine has been clarified substantially:
   - buoyant reference surface
   - glyph orientation primitives
   - articulation-authority reuse
4. The correct next build step is not another blind renderer tweak. It is:
   - glyph articulation registry
   - workbench-to-glyph adapter
   - fit scorer / continuity solver
5. The text renderer itself still needs repair and should not be presented as finished.
