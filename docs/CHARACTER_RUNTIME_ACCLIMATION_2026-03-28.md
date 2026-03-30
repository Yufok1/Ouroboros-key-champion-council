# Character Runtime Acclimation 2026-03-28

Status: Active handoff, updated for runtime checkpoint
Date: 2026-03-29
Scope: Compression-safe acclimation for new agents landing on the current embodiment/runtime lane

## Purpose

Give a fresh agent the minimum real context needed to work on the current character roadmap without
replaying old transcript drift.

## Read Order

1. `docs/rode.txt`
2. `docs/CHAMPION_COUNCIL_ROADMAP_2026-03-24.md`
3. `docs/CHARACTER_RUNTIME_AND_PORTABILITY_ARCHITECTURE_SPEC.md`
4. `docs/CHARACTER_COMMAND_REGISTRY.md`
5. `docs/CHARACTER_EMBODIMENT_SPEC.md`

## Current Truth

The active runtime direction is:

- keep the restored environment runtime stable
- continue the `v133` embodiment/portable-character lane
- keep `v133b.1` on the mounted animation-command lane until the full agent ingress path is aligned
- validate on humanoids first
- defer the animal/quadruped lane until the humanoid command lane is proven

Current runtime checkpoint:

- mounted runtime animation handlers now exist in `static/main.js`
- mounted runtime exports a live `animation_surface`
- mounted owned-surface control now works through `open_surface` + `surface_input` + `surface_action`
- workbench/model-swap menu sync is fixed in the browser/runtime lane
- animation-selection highlight lag is fixed in the browser/runtime lane
- direct `env_control(command="character_play_clip")` style dispatch is now aligned through the editable shell proxy and validated live against the existing browser/runtime handlers

## Current Code Anchors

The current `HEAD` already contains the primitive animation machinery in `static/main.js`:

- `_env3DBuildDerivedAnimationContract(...)`
- `_env3DClipInventory(...)`
- `_env3DResolveAnimationClip(...)`
- `_env3DBuildRetargetedClipInventory(...)`
- `_envRefreshInhabitantRuntimeState(...)`
- `_envQueueControl(...)`

Current ingress truth:

- raw `env_control(character_*)` ingress for the 7 animation verbs is now aligned through `server.py`
- mounted owned-surface control remains the safest operator-facing lane
- public browser helper bridge remains working

That means the next step is cohort validation and queue/interrupt follow-through, not reinvention.

## Current Milestone

`v133b` first slice is already present in working form:

- derived animation contract
- flattened clip map
- extended clip classification
- retargeted inventory
- mounted export improvements

The exact command set for `v133b.1` is:

- `character.play_clip`
- `character.queue_clips`
- `character.stop_clip`
- `character.set_loop`
- `character.set_speed`
- `character.get_animation_state`
- `character.play_reaction`

## Validated Humanoid Test Cohort

These are the best immediate validation assets because they are humanoid and carry large clip sets.

- `static/assets/packs/kenney-mini-characters-1/character-male-a.glb` — 32 clips
- `static/assets/packs/kenney-mini-characters-1/character-female-a.glb` — 32 clips
- `static/assets/packs/kenney-mini-dungeon/character-human.glb` — 32 clips
- `static/assets/packs/kenney-graveyard-kit/character-skeleton.glb` — 32 clips
- `static/assets/packs/kenney-graveyard-kit/character-vampire.glb` — 32 clips
- `static/assets/packs/kenney-graveyard-kit/character-zombie.glb` — 32 clips

Representative clips on that family include:

- `idle`
- `walk`
- `sprint`
- `jump`
- `fall`
- `crouch`
- `sit`
- `drive`
- `die`
- `pick-up`
- `emote-yes`

## Immediate Implementation Order

1. Keep dotted `character.*` names canonical in docs and buyer surfaces.
2. Alias underscored runtime host ids internally instead of letting the two naming schemes diverge.
3. Keep the mounted `animation_surface` and owned-surface control lane stable.
4. Validate the now-aligned direct shell ingress path for raw animation verbs on the humanoid cohort.
5. Validate the verb set on the humanoid cohort above with clearly dissimilar clips.
6. Only after that, implement queue/interrupt semantics for `v133b.2`.

## Explicit Deferral

Do not fold these into the current milestone:

- quadruped/animal scaffold work
- quadruped family inference changes
- beast-specific bone/body rendering

Those belong to a later embodiment-family pass after the humanoid lane is stable.

## Deferred Animal Lane

A later embodiment-family lane should add proper animal support through:

- animal rig-family detection
- animal scaffold and bone body-language rules
- animal locomotion/action contracts
- animal validation cohorts and import rules

This is not active work for `v133b.1`.
