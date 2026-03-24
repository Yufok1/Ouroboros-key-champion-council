# Codex v132 Scope Brief — Player Presence on Restored Baseline

Prepared by: Codex
Date: 2026-03-24
Base commit: `abc2774`
Base runtime: restored pre-underdepths baseline
Target bundle: `132`

## Context

The runtime has been rolled back to a pre-underdepths baseline and then patched with a small set of generic fixes.

This means `v132` is no longer "player presence on top of a cave generator." It is now "player presence on top of the restored general environment runtime."

The current live baseline already has:

- environment theater
- live/shared-state mirror
- Rapier initialization and physics stepping
- world profiles and strata
- asset-driven scene composition
- observer / bounds / verification substrate

The current live baseline does not have:

- a first-class local player entity
- traversal mode
- player camera binding
- player telemetry in live/shared payloads

## Existing Runtime Surfaces

These surfaces already exist in `static/main.js` at `abc2774`:

- `_envBuildLiveMirrorSurface()` at `20730`
- `_envBuildLiveSyncPayload(reason)` at `21018`
- `_env3DPhysicsSnapshot()` at `21444`
- `_env3DInitPhysics(RAPIER)` at `21477`
- `_env3DEnsurePhysicsInit()` at `21502`
- `_envWorldProfiles` at `24743`
- `_env3DSyncObjects(objects)` at `29915`
- `_env3DAnimate()` at `30275`
- `_envFindAssetRecord(packId, assetId)` at `33137`

Implementation should extend these surfaces, not create a second runtime lane.

## v132 Deliverables

### 1. Player Runtime State

Add a first-class local player state with at least:

- `enabled`
- `mode`
- `position`
- `velocity`
- `yaw`
- `pitch`
- `grounded`
- `spawn_source`

This state must be visible through the live/shared-state payload.

### 2. Rapier-Backed Controller

Add a player body that uses the existing Rapier world:

- initialize physics on demand when player mode activates
- create a dedicated player rigid body / collider
- collide against the current environment
- support gravity and recovery without falling through the world

Do not create a second physics world.

### 3. Traversal Input + Camera Binding

Add a minimal traversal mode to the theater:

- movement input
- look input
- player-follow camera while active
- clean return to current free/orbit behavior when disabled

The first pass should favor reliability over polish.

### 4. Spawn / Recovery Path

Add deterministic player placement:

- safe spawn in the active scene
- floor-aware fallback if no ideal spawn exists
- recovery if the player leaves valid bounds or physics setup fails

This must work without assuming a cave or generator-specific entry point.

### 5. Mirror / Debug Visibility

Expose player telemetry through the existing mirror/debug path:

- current player state in live/shared payloads
- player physics summary
- clear indicator that player mode is active

Verification must be possible over MCP, not only by visual inspection.

## What Not To Do

- Do not rebuild procedural generation in `v132`
- Do not add NPC embodiment yet
- Do not add combat or projectiles yet
- Do not add equipment runtime yet
- Do not replace the entire camera architecture
- Do not introduce cave- or underdepth-specific assumptions

## Success Criteria

1. Player mode can be entered from the restored theater runtime
2. Rapier initializes and the player can traverse active scenes without falling through the floor
3. Live/shared-state payloads expose player position, velocity, and grounded state
4. The restored runtime remains healthy on local startup and MCP sync
5. Existing asset-driven scenes remain stable while player mode is active

## Verification Criteria

Verify against the actual restored runtime, not archived cave fixtures:

- local server boots cleanly on the configured ports
- panel and health endpoints remain healthy
- player mode can be entered and exited cleanly
- observer/live-mirror payloads remain valid while the player moves
- no new bounds/coordinate regressions are introduced

## File Touchpoints

Expected primary touchpoints:

- `static/main.js`
- `static/panel.html`

Possible secondary touchpoints if needed:

- `server.py` for minimal API or diagnostics support only

## Notes

- The archived cave-era `v132` brief is historical only and should not be used as the active scope source.
- If procedural generation returns later, it should be rebuilt as a neutral world system, not used as the validation substrate for `v132`.
