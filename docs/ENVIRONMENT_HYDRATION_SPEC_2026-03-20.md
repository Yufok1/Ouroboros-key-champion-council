# Environment Hydration Spec 2026-03-20

This document defines the intended reconnect and reload behavior for the Environment tab.

## Problem

The current failure mode is not data loss. It is presentation drift during reconnect:

- the browser can briefly show the default workflow shell as the apparent primary scene
- a half-hydrated or empty scene can appear before the persisted scene state is restored
- operators then lose trust in whether the observer is seeing live truth or an intermediate shell state

The goal is to remove that ambiguity.

## Scope

This spec is intentionally narrow.

It does **not** attempt to solve every browser cache edge case or every service worker race.

It does define one operator-facing rule:

- if a persisted environment snapshot or persisted custom scene exists, that state should win the reconnect race over the default shell

## Primary Rule

After reconnect, the first scene that should read as authoritative to the operator is the persisted environment state when one exists.

The default workflow shell is only the visible fallback when no persisted scene state is available to restore.

## Intended Sequence

1. Browser reconnect begins.
2. The environment runtime checks for persisted scene state:
   - persisted custom scene objects
   - active persisted snapshot identity
   - preserved empty-scene state
3. If persisted scene state exists, restore it before presenting the default shell as the apparent primary scene.
4. Only if no persisted scene state exists should the runtime settle on the default workflow shell.
5. Once restore is complete, the mirror/readback surfaces should reflect the same active scene:
   - `current_snapshot`
   - object count
   - habitat object list
   - observer captures

## Behavioral Requirements

- Reconnect should prefer persisted scene truth over shell truth.
- An intentionally empty scene must remain empty after reload instead of rehydrating an older shell snapshot.
- Snapshot identity helpers must not revive a stale scene while persisted custom-scene hydration is still unresolved.
- Observer captures taken after reconnect should target the restored scene, not the interim shell.

## Observable Success Criteria

The hydration path is working correctly when all of these are true:

- after reconnect, the live mirror reports the restored snapshot or restored empty state without first surfacing the shell as the active scene
- live object count and habitat object count agree with the restored scene
- observer captures and focus/probe metadata resolve against the restored objects
- a user does not have to manually reload a desired snapshot after ordinary reconnect

## Current Recommended Implementation Direction

The preferred model is server-backed or persisted-state-first restore during reconnect, not "render shell immediately and replace it later."

That means:

- scene restore should happen before shell identity helpers are allowed to win
- preserved emptiness should be treated as a real state, not as missing data
- reconnect logic should bias toward continuity of the last authoritative environment state

## Relationship To Other Docs

- [THEATER_VISION_SYSTEM.md](/F:/End-Game/champion_councl/docs/THEATER_VISION_SYSTEM.md) defines the observer authority model that depends on stable hydration.
- [DEBUG_SYSTEM_ALIGNMENT_2026-03-19.md](/F:/End-Game/champion_councl/docs/DEBUG_SYSTEM_ALIGNMENT_2026-03-19.md) defines the operator debug triad used to verify hydration.
- [ENVIRONMENT_MEMORY_INDEX.md](/F:/End-Game/champion_councl/docs/ENVIRONMENT_MEMORY_INDEX.md) treats this behavior as part of the canonical environment continuity model.
