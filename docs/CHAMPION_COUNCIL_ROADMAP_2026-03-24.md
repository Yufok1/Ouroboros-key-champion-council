# Champion Council Roadmap

Status: Active
Date: 2026-03-24
Baseline commit: `abc2774`
Runtime baseline: restored pre-underdepths environment runtime with generic fixes reapplied

## Current Position

Champion Council is back on a pre-underdepths baseline.

The tracked code no longer includes the underdepth / cave-first procedural generation branch that lived from `7a57590` through `bcc259f`. That branch is archived as historical exploration, not current product direction.

The live baseline at `abc2774` keeps:

- environment theater and live mirror
- Rapier initialization and physics scaffold
- world profiles and profile kits
- asset ingestion and pack registry
- observer / bounds / scene-truth systems
- generic runtime fixes reapplied after restore

The baseline does not keep:

- underdepths-specific world assumptions
- cave-chamber / cave-passage recipes
- procedural recipe / vocab files
- `generate_scene` / `clear_generated_scene`
- cave-first scoring and archetype thresholds

## Four Phases

### Phase 1 — HTML Agent Surface

Status: Complete

Delivered:

- standalone web shell
- local/capsule orchestration
- health, activity, and tool surfaces

### Phase 2 — Productionalized Environment Runtime

Status: In progress

Delivered:

- environment theater
- live mirror and persistence loop
- world-profile-aware rendering
- asset browser and pack ingestion
- observer and scene-verification substrate

Open:

- stronger operator ergonomics
- cleaner product-facing docs
- tighter runtime verification loops

### Phase 3 — Embodiment and World Runtime

Status: Active

This is the current execution lane.

Focus:

- player presence
- NPC embodiment
- combat/mechanics
- equipment/runtime assembly
- clean procgen rebuild from a neutral ontology

### Phase 4 — Agent Sim / Game Runtime

Status: Future

Focus:

- agent societies
- dynamic encounters
- player + AI co-presence
- broader world evolution loops

## Version Map

### Shipped Baseline

The active shipped baseline is `abc2774`, built on `e9e9a39`.

This baseline includes:

- physics scaffold
- live/shared-state mirror
- world profiles
- asset pipeline
- observer scene bounds and verification substrate
- restored generic runtime fixes

### Removed Branch

The following line is no longer part of the active tracked runtime:

- `v129u` underdepths foundation
- `v130` cave procedural generator + sync
- `v130o` water / seabed cave shaping
- `v131a` passage archetype expansion
- `v131b` cave scoring recalibration

These artifacts are archived under `docs/archive/rollback-2026-03-24/`.

### Next Active Milestones

#### v132 — Player Presence + Character Controller

Target:

- local player runtime state
- Rapier-backed traversal controller
- camera binding for player mode
- spawn / recovery path
- live mirror exposure for player telemetry

#### v133 — NPC Embodiment Pipeline

Target:

- canonical runtime entity lane
- embodied NPC instances
- retargeting-aware character normalization
- animation/control seam for non-player actors

#### v134 — Combat + Projectiles + Buoyancy

Target:

- combat-ready action state
- projectile simulation
- water interaction and buoyancy
- mechanics integration with embodiment runtime

#### v135 — Attachment + Equipment Runtime

Target:

- slot-based attachment system
- equipment-driven appearance/state changes
- runtime snap-point binding

#### v136 — Commercial Export Pipeline

Target:

- export-ready embodied assets
- packaging for portable runtime/content products
- preview and metadata generation

## Procedural Generation Status

Procedural generation is still a strategic goal, but it is not present in the active tracked runtime.

Reason:

- the removed implementation was too tightly shaped around the underdepth / cave branch
- it should not define the future ontology of the system

Return conditions:

- rebuild from a neutral world ontology
- emit canonical scene objects into the existing substrate
- support multiple world families instead of one archetype family
- include runtime contracts and audit tooling from the start

Design reference:

- `docs/PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md`

## Immediate Priorities

1. Keep the restored runtime stable on `abc2774`
2. Write and execute `v132` against the restored baseline
3. Update embodiment/runtime docs so version numbering matches reality
4. Rebuild procedural generation later as a general scene system, not a cave-first system
