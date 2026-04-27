# Codex v132 Scope Brief — Agent Spatial Presence on Restored Baseline

Prepared by: Codex
Date: 2026-03-25
Base commit: `abc2774`
Base runtime: restored pre-underdepths baseline
Target bundle: `132`

## Context

The runtime has been rolled back to a pre-underdepths baseline and then patched with a small set of generic fixes.

This means `v132` is no longer "player presence on top of a cave generator." It is now "agent spatial presence on top of the restored general environment runtime."

The current live baseline already has:

- environment theater
- live/shared-state mirror
- optional Rapier scaffold
- world profiles and strata
- asset-driven scene composition
- observer / bounds / verification substrate
- agent-kind visual support
- behavior-driven movement seams for agent-like objects

The current live baseline does not have:

- a first-class inhabitant runtime state
- a canonical local agent presence toggle
- clean inhabitant camera binding
- inhabitant telemetry in live/shared payloads

## Existing Runtime Surfaces

These surfaces already exist in `static/main.js` at `abc2774`:

- `_envBuildLiveMirrorSurface()` at `20730`
- `_envBuildLiveSyncPayload(reason)` at `21018`
- `_env3DPhysicsSnapshot()` at `21444`
- `_env3DInitPhysics(RAPIER)` at `21477`
- `_env3DEnsurePhysicsInit()` at `21502`
- `_env3DIsAgentKind(kind)` at `24119`
- `_env3DAdvanceCharacterBehavior(mesh, obj, dt)` at `27402`
- `_env3DAdvanceMeshLocomotion(mesh, key, dt, isAgent)` at `27477`
- `_envWorldProfiles` at `24743`
- `_env3DSyncObjects(objects)` at `29915`
- `_env3DAnimate()` at `30275`
- `_envFindAssetRecord(packId, assetId)` at `33137`

Implementation should extend these surfaces, not create a second runtime lane.

## v132 Deliverables

### 1. Inhabitant Runtime State

Add a first-class local inhabitant state with at least:

- `enabled`
- `mode`
- `position`
- `facing`
- `behavior`
- `visual_mode`
- `activity`
- `camera_binding`
- `spawn_source`

This state must be visible through the live/shared-state payload.

### 2. Visible Inhabitant

Add one canonical inhabitant entity to the scene graph:

- use the existing object contract and agent-kind rendering surfaces
- choose the cheapest legible representation that works now: sprite, marker, or mesh
- keep the representation interchangeable so richer embodiment can replace it later
- do not fork a second object model just for inhabitant presence

### 3. Behavior-Driven Movement

Use the existing non-physics locomotion seams:

- idle
- goto
- patrol
- wander
- follow

The first pass should favor deterministic, visually legible movement over rigid body realism.

For the canonical inhabitant lane, default presence should be idle / anchored until an explicit command or objective is assigned. Ambient random wandering is not the default operating mode.

Do not make Rapier a dependency of `v132`.

### 4. Camera Binding + Entry / Exit

Add a minimal inhabitant presence mode to the theater:

- camera can follow the inhabitant while active
- camera can return cleanly to current overview/orbit behavior when disabled
- inhabitant presence can be entered and exited cleanly
- the active camera relationship is visible in runtime state

### 5. Spawn / Recovery Path

Add deterministic inhabitant placement:

- safe spawn in the active scene
- bounded fallback if no authored spawn exists
- recovery if the inhabitant leaves valid space or route planning fails
- no cave-, generator-, or player-start-specific assumptions

### 6. Mirror / Debug Visibility

Expose inhabitant telemetry through the existing mirror/debug path:

- current inhabitant state in live/shared payloads
- current behavior and camera-binding summary
- clear indicator that inhabitant presence is active
- enough data to verify behavior over MCP, not only by visual inspection

Verification must be possible over MCP, not only by visual inspection.

## What Not To Do

- Do not rebuild procedural generation in `v132`
- Do not add broader multi-inhabitant embodiment yet
- Do not add combat, projectiles, or equipment yet
- Do not add equipment runtime yet
- Do not replace the entire camera architecture
- Do not make physics mandatory
- Do not create a second movement/runtime model
- Do not introduce cave- or underdepth-specific assumptions

## Success Criteria

1. Inhabitant presence can be entered from the restored theater runtime
2. A visible inhabitant can be observed in active scenes without introducing a second runtime lane
3. Existing behavior-driven movement seams can move the inhabitant through authored scenes
4. Live/shared-state payloads expose inhabitant position, behavior, and camera-binding state
5. The restored runtime remains healthy on local startup and MCP sync
6. Existing asset-driven scenes remain stable while inhabitant presence is active

## Verification Criteria

Verify against the actual restored runtime, not archived cave fixtures:

- local server boots cleanly on the configured ports
- panel and health endpoints remain healthy
- inhabitant presence can be entered and exited cleanly
- observer/live-mirror payloads remain valid while the inhabitant moves
- no new bounds/coordinate regressions are introduced
- no physics dependency is required for the first pass

## File Touchpoints

Expected primary touchpoints:

- `static/main.js`
- `static/panel.html`

Possible secondary touchpoints if needed:

- `server.py` for minimal API or diagnostics support only

## Notes

- The archived cave-era `v132` brief is historical only and should not be used as the active scope source.
- Rapier remains available as a dormant facility. It is not the validation substrate for `v132`.
- If procedural generation returns later, it should be rebuilt as generative scenography that emits canonical scene objects into the existing substrate.
