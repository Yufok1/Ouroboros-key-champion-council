# Env Help Sitrep 2026-04-04

Repo: `F:\End-Game\champion_councl`

Scope:

- repo-local environment help subsystem only
- no edits to `champion_gen8`
- no edits to capsule internals
- no edits to legacy `get_help`

## Current State

The new `env_help` system is live over local `self_deploy` and is now richer than the first scaffold pass.

Current live counts:

- `137` total indexed entries
- `116` env/runtime commands
- `21` browser-local environment UI actions
- `9` families
- `4` playbooks

The key files are:

- [scripts/generate-env-help-registry.js](/F:/End-Game/champion_councl/scripts/generate-env-help-registry.js)
- [static/data/help/environment_command_overrides.json](/F:/End-Game/champion_councl/static/data/help/environment_command_overrides.json)
- [static/data/help/environment_command_registry.json](/F:/End-Game/champion_councl/static/data/help/environment_command_registry.json)
- [server.py](/F:/End-Game/champion_councl/server.py)
- [ENVIRONMENT_HELP_SYSTEM_SPEC_2026-04-04.md](/F:/End-Game/champion_councl/docs/ENVIRONMENT_HELP_SYSTEM_SPEC_2026-04-04.md)

## What Changed

The system is no longer just a thin source index for proxied env commands.

It now does three things:

1. Maps env/runtime commands from current source.
2. Maps browser-local environment actions that do not exist as direct `env_control` verbs.
3. Returns richer operator-facing help instead of generic one-line summaries.

Per-entry fields now include:

- `summary`
- `when_to_use`
- `what_it_changes`
- `mode_notes`
- `verification`
- `gotchas`
- `failure_modes`
- `aliases`
- `surface_entrypoints`
- `bridges_to`
- `related_commands`
- `source_anchors`

## Important Structural Truth

The help system now distinguishes between:

- proxied env/runtime commands
- browser-surface reachable commands
- UI-local environment actions

That distinction is critical because the theater surface contains real local controls that do not belong to the backend command surface.

Confirmed examples:

- `workbench_set_load_field` = persistent env/runtime command
- `workbench-toggle-load-field` = browser-local helper action that bridges into `workbench_set_load_field`
- `workbench_set_scaffold` = persistent env/runtime command
- `workbench-toggle-scaffold` = browser-local helper action that bridges into `workbench_set_scaffold`
- `workbench-toggle-turntable` = browser-local only, not an `env_control` command
- `focus_actor` = env/runtime command
- `focus-actor` = browser alias/entrypoint now resolvable by `env_help`

## Live Validation

Confirmed live after reset:

- `env_help(topic='index')`
- `env_help(topic='focus-actor')`
- `env_help(topic='workbench-toggle-turntable')`
- `env_help(topic='workbench-toggle-load-field')`
- `env_help(category='surface_bridge')`
- `env_help(search='turntable')`
- `env_help(topic='playbook:builder_helper_strip_review')`

Important validation result:

- alias lookup is now live, not just implemented in source
- UI-local controls are first-class help entries now

## Families

Current family coverage:

- `builder_motion`
- `builder_workbench`
- `camera_pose`
- `capture_observer`
- `character_runtime`
- `environment_misc`
- `focus_navigation`
- `surface_bridge`
- `theater_profile_recipe`

Notable family expansions:

- `builder_motion` now includes local clip/playback controls, not just backend motion verbs
- `builder_workbench` now includes local helper-strip builder controls
- `surface_bridge` now includes local overlay-panel controls
- `character_runtime` now includes the local inhabitant toggle path

## Playbooks

Current playbooks:

- `mounted_asset_inspection`
- `motion_preset_validation`
- `builder_helper_strip_review`
- `builder_blueprint_roundtrip`

These are intended to keep the system practical, not just descriptive.

## What Opus Should Evaluate

Primary evaluation questions:

1. Is the command/action classification honest?
   - especially proxied vs browser-local vs browser-bridged

2. Are the rich fields actually useful?
   - `when_to_use`
   - `what_it_changes`
   - `mode_notes`
   - `failure_modes`

3. Are the family boundaries good enough?
   - especially `builder_motion` vs `builder_workbench`
   - `surface_bridge` vs `environment_misc`

4. Are the browser-local action entries correct?
   - especially helper-strip controls
   - overlay panel controls
   - local camera reset
   - local inhabitant toggle

5. Are there important environment controls still missing from the registry?
   - current expectation is that the main remaining work is refinement, not large missing surfaces

6. Is the system now good enough to serve as the working operator manual while we return to ground interaction and motion confirmation?

## Current Assessment

This is now good enough to use as the active environment help surface.

It is:

- dynamic
- source-derived
- richer than the first scaffold
- honest about UI-local theater controls
- practical enough to use during the next ground-interaction and motion validation passes

It is not “done forever,” but it is no longer a thin prototype.

## Next Step After Opus Review

Assuming Opus does not find a major classification error, the next lane should return to:

1. ground-interaction / motion confirmation
2. builder and mounted-asset motion checks
3. using `env_help` as the reference surface during that validation work
