# Champion Council Roadmap

Status: Active
Date: 2026-03-28
Baseline commit: `abc2774`
Runtime baseline: restored pre-underdepths environment runtime with generic fixes reapplied

## Canonical Identity

Champion Council is a self-verifying AI capsule with an inhabitable spatial substrate, a sandboxed agent workspace, and a live operational theater.

Its three fused surfaces are:

- spatial substrate
- agent workspace
- verifiable runtime

Champion Council is not a game engine, simulation engine, or fixed VFX pipeline. It is inhabitable procedural media with agent co-presence.

## Current Position

Champion Council is back on a pre-underdepths baseline.

The tracked code no longer includes the underdepth / cave-first procedural generation branch that lived from `7a57590` through `bcc259f`. That branch is archived as historical exploration, not current product direction.

The live baseline at `abc2774` keeps:

- environment theater and live mirror
- optional Rapier scaffold
- world profiles and profile kits
- asset ingestion and pack registry
- observer / bounds / scene-truth systems
- behavior-driven movement seams for agent-like objects
- generic runtime fixes reapplied after restore

The baseline does not keep:

- underdepths-specific world assumptions
- cave-chamber / cave-passage recipes
- procedural recipe / vocab files
- `generate_scene` / `clear_generated_scene`
- cave-first scoring and archetype thresholds

## Facilities and Workstations

Facilities and workstations are the preferred organizing language for Champion Council.

- A facility is a capability blueprint the substrate may activate
- A workstation is a bound instance of that facility in the current environment

Physics, palette evolution, spatial theater, agent presence, export, and diagnostics should be treated as optional facilities. They can be inhaled when useful, left dormant when not, and recombined without forcing the whole system through a fixed engine hierarchy.

## Four Phases

### Phase 1 — HTML Agent Surface

Status: Complete

Delivered:

- standalone web shell
- local/capsule orchestration
- health, activity, and tool surfaces

### Phase 2 — Operational Environment Runtime

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

### Phase 3 — Agent Presence and Embodiment

Status: Active

This is the current execution lane.

Focus:

- agent spatial presence
- inhabitant embodiment
- portable character runtime
- animation command surface promotion
- optional interaction/mechanics facilities
- attachment/runtime assembly
- clean procgen rebuild from a neutral ontology

### Phase 4 — Agent Co-Presence and World Evolution

Status: Future

Focus:

- agent societies
- human + agent co-presence
- dynamic encounters when useful
- broader world evolution loops
- richer facility orchestration

## Version Map

### Shipped Baseline

The active shipped baseline is `abc2774`, built on `e9e9a39`.

This baseline includes:

- optional physics scaffold
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

Historical artifacts may exist locally under `docs/archive/rollback-2026-03-24/`, but they are not part of the canonical tracked runtime doctrine unless explicitly committed later.

### Next Active Milestones

#### v132 — Agent Spatial Presence

Target:

- local inhabitant runtime state
- visible inhabitant entity in the scene graph
- behavior-driven movement via existing locomotion lanes
- camera binding for inhabitant presence mode
- spawn / recovery path
- live mirror exposure for inhabitant telemetry

#### v133 — Inhabitant Embodiment Pipeline

Target:

- canonical runtime entity lane
- embodied inhabitant instances
- retargeting-aware character normalization
- animation/control seam for non-player actors

Current state:

- model identity lane stabilized
- derived animation contract + clip resolver lane present
- mounted export improved
- mounted `animation_surface` now exports live browser/runtime state
- mounted owned-surface animation control now works in the browser/runtime lane
- remaining gap is upstream direct `env_control(character_*)` validation, not local playback plumbing

Execution note:

- validate on humanoid models first
- do not mix animal/quadruped scaffold work into this slice

#### v134 — Optional Interaction and Physics Facilities

Target:

- action-ready runtime state
- optional projectile or physics-backed interaction facilities when justified
- optional water interaction and buoyancy facilities when justified
- mechanics integration with embodiment runtime only when a live facility needs them

#### v135 — Attachment + Equipment Facility

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
- serve as generative scenography, not a fixed level-design pipeline
- support multiple world families instead of one archetype family
- include runtime contracts and audit tooling from the start

Design reference:

- `docs/PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md`

## Immediate Priorities

1. Keep the restored runtime stable on `abc2774`
2. Keep the mounted animation surface and owned-surface command lane stable
3. Align the remaining upstream agent ingress path for raw `character_*` animation verbs
4. Validate the command lane on the current humanoid cohort before adding queue/interrupt complexity
5. Reconcile roadmap/spec/command docs so fresh agents land on the same version truth
6. Defer animal/quadruped embodiment work until the humanoid lane is stable
7. Rebuild procedural generation later as a general scene system, not a cave-first system
