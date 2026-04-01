# Builder Theater Session Handoff

Status: Active handoff
Date: 2026-03-31
Scope: Current repo/runtime truth for the builder theater lane through committed Slice 3d

## Purpose

This file is the short operational handoff for new sessions landing on the builder theater lane.

Use it to reacclimate quickly after context compression.

Use `docs/SCAFFOLD_MODEL_THEATER_SITREP_2026-03-31.md` for doctrine and architecture.
Use this file for actual committed repo/runtime state.

## Current Git Truth

- repo: `F:\End-Game\champion_councl`
- branch: `main`
- committed HEAD: `ea12443` `Add structure-mode gizmo bridge, local_offset, part work-cell staging, and focus rig (Slice 3d)`

Checks green at handoff time:

- `node --check static/main.js`
- `python -m py_compile server.py`

## Committed Builder Arc

- `802e038` Slice 1
  - blank model theater builder subject
- `0bde3e7` Slice 2
  - structure editing: set bone, isolate chain, save/load blueprint
- `4018a4c` Slice 3a
  - selection substrate
- `98ed875` Slice 3b
  - derived part surface contract
- `86ce784` Slice 3c
  - part camera recipes
  - `workbench_frame_part`
  - part-target `capture_focus` / `capture_probe`
- `acd5003` Slice 3c.1/3c.2
  - visual selection grammar
  - display scopes
- `ea12443` Slice 3d
  - structure-mode gizmo bridge
  - `local_offset` persistence
  - `workbench_set_gizmo_mode`
  - `workbench_set_gizmo_space`
  - part work-cell staging
  - part-aware focus rig

## Current Builder Capabilities

The builder structure-authoring loop is now complete enough to treat as a real milestone:

- create a blank or preset builder subject
- edit canonical bones through `workbench_set_bone`
- rotate, scale, and translate selected bones through shared TransformControls
- persist `orientation`, `roll`, `length`, `radius_profile`, `local_offset`, and `enabled`
- isolate chains and apply display scopes:
  - `body`
  - `part_chain`
  - `part_adjacent`
  - `part_only`
- derive part surfaces and camera recipes for any selected bone
- frame selected parts through `workbench_frame_part`
- save and load structure blueprints
- mirror selection, part surface, camera recipes, and gizmo state through `workbench_surface`
- drive the same structure lane through either direct browser interaction or `env_control`

## Current Live Runtime Truth

Live shell and mirror were revalidated after Slice 3d.

Confirmed live:

- mounted focus is `character_runtime::mounted_primary`
- command surface includes:
  - `workbench_new_builder`
  - `workbench_get_blueprint`
  - `workbench_get_part_surface`
  - `workbench_frame_part`
  - `workbench_select_bone`
  - `workbench_set_editing_mode`
  - `workbench_set_display_scope`
  - `workbench_set_gizmo_mode`
  - `workbench_set_gizmo_space`
  - `workbench_set_bone`
- shared `workbench_surface` includes:
  - `selected_bone_id`
  - `selected_part_surface`
  - `part_camera_recipes`
  - `selection_visual_state`
  - `part_display_scope`
  - `part_view`
  - `gizmo_attached`

Part-subtarget observer lane remains real:

- `capture_probe("character_runtime::mounted_primary#bone:upper_arm_l")`
  - returns `part_key`
  - returns `bone_id`
  - returns derived `part_surface`
  - returns derived `camera_recipes`

## What Slice 3d Solved

The important post-3c gap was no longer selection itself.

The missing behavior was:

- isolated limbs stayed staged like a full body
- camera focus drifted back to mounted-mesh framing
- translate-mode gizmo edits had no persisted target

Slice 3d closed that gap by landing:

- persisted `local_offset`
- structure-mode rotate / scale / translate through one gizmo bridge
- agent-parity gizmo mode and space verbs
- part-work-cell recenter / rescale staging
- persistent part-aware focus rig inside the same theater

## What Does Not Exist Yet

These are still the real missing layers:

- `pose_state`
- explicit reset verbs for pose and structure cleanup
- `joint_limits`
- pose-mode gizmo
- timeline / key-pose substrate
- clip compiler into the existing playback contract

The downstream playback lane already exists.
What does not exist yet is the authored motion substrate that feeds it.

## Next Target

The next clean move is the pose/motion layer:

1. `pose_state`
2. reset verbs
3. `joint_limits`
4. pose-mode gizmo
5. timeline / key-pose data model
6. clip compiler into the existing playback lane

Keep the doctrine invariant:

- structure and pose are separate mutation paths

## Read Order For Fresh Session

1. this file
2. `C:\Users\Jeff Towers\.codex\memories\champion-council-session-handoff-2026-03-31-builder-theater.md`
3. `C:\Users\Jeff Towers\.codex\memories\champion-council-core-hierarchy.md`
4. `C:\Users\Jeff Towers\.codex\memories\champion-council-working-rules.md`
5. `docs/SCAFFOLD_MODEL_THEATER_SITREP_2026-03-31.md`
6. `git status --short`
7. `git log --oneline -5`
8. `git diff --stat`
9. `env_read(shared_state)`

## Bottom Line

Where the repo stands now:

- one theater
- one builder structure truth
- one shared human/agent control surface
- real structure authoring through Slice 3d
- real downstream playback runtime already waiting

The next layer is not another structure stack.

The next layer is `pose_state -> timeline -> clip compiler`.
