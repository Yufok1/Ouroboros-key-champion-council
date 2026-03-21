# Environment Memory Index

This file is the continuity index for the Environment tab runtime and its operator-facing observation tools.

## Priority Truths

- The Environment tab's primary 3D observation instrument is the theater vision system.
- Use the observer capture system before making major spatial judgments about scene composition, enclosure, scale, local placement, or subtle prop correction.
- The observer system is authoritative because it reuses the live scene, live object records, live mesh transforms, render truth, layout snapshot, and the existing capture ring.
- Scene objects now have an explicit `semantics` lane for structural meaning. Prefer it over heuristic guessing when available.
- Semantic context is now auto-captured during normal spawn, mutate, and hydrate flows. Prefer the captured `semantics_observation` and authored/inferred merge over ad hoc relabeling.
- Do not build alternate scene descriptions or parallel metadata models when the observer/capture path already exposes the needed information.
- On reconnect, persisted scene state should beat the default workflow shell whenever persisted state exists.

## Canonical References

- [THEATER_VISION_SYSTEM.md](/F:/End-Game/champion_councl/docs/THEATER_VISION_SYSTEM.md)
- [ENVIRONMENT_HYDRATION_SPEC_2026-03-20.md](/F:/End-Game/champion_councl/docs/ENVIRONMENT_HYDRATION_SPEC_2026-03-20.md)
- [PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md](/F:/End-Game/champion_councl/docs/PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md)
- [DEBUG_SYSTEM_ALIGNMENT_2026-03-19.md](/F:/End-Game/champion_councl/docs/DEBUG_SYSTEM_ALIGNMENT_2026-03-19.md)
- [WORLD_OBJECT_RUNTIME_PLAN.md](/F:/End-Game/champion_councl/docs/WORLD_OBJECT_RUNTIME_PLAN.md)
- [V101_SURFACE_AND_CHARACTER_PLAN.md](/F:/End-Game/champion_councl/docs/V101_SURFACE_AND_CHARACTER_PLAN.md)
- [CHARACTER_EMBODIMENT_SPEC.md](/F:/End-Game/champion_councl/docs/CHARACTER_EMBODIMENT_SPEC.md)

## Agent Guidance

- Start with `capture_supercam` to understand the whole scene.
- Use `capture_probe` on the current target object for local experiments and placement refinement.
- Use `probe_compare` after a change to verify what moved, what did not move, and whether neighbors shifted.
- Use `capture_focus` when an individual object or local cluster needs closer visual inspection.
- Use `env_read(query='debug_state')` when you need a compact summary of the current debug substrate without leaving the environment tool path.
- Prefer procedural generation work that emits normal scene objects through the existing substrate over ad hoc one-off scene composition.
- Trust the observer metadata over guesswork:
  - object keys
  - object semantics
  - semantic provenance and confidence
  - neighbor sets
  - tile camera poses
  - screen-space projections
  - physics snapshot
  - render truth

## Why This Matters

The observer system is no longer a novelty screenshot path. It is a practical build instrument for:

- scene composition review
- local structure correction
- subtle prop placement
- before/after experiment loops
- grounded visual reasoning tied to real object identities

The debug system should be treated the same way:

- the authoritative debug substrate is the existing mirror plus `feed`
- the Debug tab is a filtered browser surface
- `env_read(query='debug_state')` is the compact operator-facing summary of that existing substrate

Any agent working on environment construction should prefer this resource over ad hoc verbal inference.
