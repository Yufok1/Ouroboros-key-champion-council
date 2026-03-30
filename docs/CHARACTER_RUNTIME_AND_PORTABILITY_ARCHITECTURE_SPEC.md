# Character Runtime, Embodiment, and Portability Architecture

Status: Draft, updated for v133b.1 runtime checkpoint  
Date: 2026-03-29  
Scope: Canonical separation of environment products and character products, with mounted character runtime integration

## Purpose

Define the architecture that corrects the failed `npc::resident_primary` experiment.

The key correction is:

- an environment is not a character
- a character is not an actor
- an actor is not a scene object

Champion Council should author environments and characters inside the same theater, but they must remain separate product classes.

The actor/runtime layer is not a separate product or process by default.

It is a facility of the character product that mounts into an environment through an integration contract.

This spec establishes:

1. the two product classes: environment and character
2. the portable interchange/export stack for character products
3. the character runtime facility and mount contract
4. the theater workbench model for environment-scale and character-scale authoring
5. the migration path away from actor-as-scene-object embodiment

## Current Implementation Note

As of 2026-03-29, the runtime already contains:

- derived animation contract generation
- clip inventory and clip resolution
- retargeted clip inventory generation
- mounted runtime refresh/export
- mounted `animation_surface` export
- mounted owned-surface animation control wired into the existing `character_*` handlers

The current worktree also aligns direct shell-level `env_control` ingress for the 7 animation verbs without touching the capsule.

The current public runtime bridge includes:

- `character_mount`
- `character_unmount`
- `character_focus`
- `character_set_model`
- `character_move_to`
- `character_stop`
- `character_look_at`
- `character_play_clip`
- `character_queue_clips`
- `character_stop_clip`
- `character_set_loop`
- `character_set_speed`
- `character_get_animation_state`
- `character_play_reaction`

The immediate remaining architecture task is to keep the mounted runtime animation surface stable and
validate the aligned ingress and UI/runtime state pairing, rather than building a second playback stack.

## Core Correction

The recent failed mobility lane treated the inhabitant as:

```js
{
  kind: 'npc',
  id: 'resident_primary'
}
```

inside the normal scene object registry.

That is the wrong container.

Scene objects are environment-side substrate entities:

- floors
- walls
- stairs
- props
- portals
- landmarks
- utility objects
- workstations

Actors are live mounted runtime instances produced by a character product.

Characters are portable embodiment products that carry their own runtime facility and can be mounted into scenes.

## Two Product Classes and One Mount Contract

### 1. Environment Product

What it is:

- scene composition
- support surfaces
- blockers
- portals
- landmarks
- utility objects
- workstations
- fabrication and interface objects

What it exports:

- environment asset package
- environment manifest
- scene composition metadata
- semantic/taxonomy metadata
- optional standalone viewer/export bundle

Canonical concern:

- substrate truth

### 2. Character Product

What it is:

- rig family
- skeleton contract
- clips
- expressions
- attachment points
- materials
- scale/origin/root-motion policy
- portability metadata
- command surface
- perception surface
- memory/runtime identity surface
- actor runtime facility

What it exports:

- character asset package
- character manifest
- embodiment metadata
- clip index
- retargeting metadata
- character runtime metadata
- mount/integration metadata

Canonical concern:

- embodiment truth plus portable runtime behavior

### 3. Mount / Integration Contract

What it is:

- the binding contract between a character product and an environment product
- the seam through which the character runtime facility consumes environment runtime facilities
- the way a mounted character gains access to support surfaces, blockers, portals, utility objects, workstations, and world state

What it is not:

- a third standalone product class
- a separate process by default
- a reason to externalize the character runtime out of the character product

## Same Theater, Different Authoring Modes

The theater remains the single authoring and inspection surface, but it must support different scales of work.

### Environment Workbench

The theater is occupied by:

- an environment
- its surfaces
- blockers
- portals
- landmarks
- utility and workstation objects

Purpose:

- author scene composition
- inspect support/blocker semantics
- validate exports and staging

### Character Workbench

The theater is occupied by:

- one character embodiment at giant scale

Purpose:

- inspect rig
- inspect origin and scale
- inspect clip behavior
- inspect attachment points
- inspect materials and texture sets
- inspect portability metadata

This is not a second renderer.

It is a camera/workbench mode in the same theater.

### Actor Debug / Runtime View

The theater shows:

- one or more mounted characters operating inside an environment

Purpose:

- direct command validation
- perception validation
- tool-grant and control-unit validation
- live runtime observation

## Product and Runtime Relationship

The correct dependency chain is:

```text
environment product + character product(with character runtime facility) -> mounted live character in environment
```

Not:

```text
npc scene object -> somehow becomes actor
```

The mounted character runtime is produced by the character product and integrated into the environment.

## Character Portability Stack

The portable character stack should be layered intentionally.

### Runtime Delivery Truth

Primary runtime format:

- `glTF 2.0`
- packaged as `.glb` by default

Why:

- API-neutral runtime interchange
- strong engine/tool support
- compact packaging
- materials, skeletons, and animations travel together

### Humanoid Avatar Lane

Humanoid specialization:

- `VRM 1.0`

Why:

- humanoid avatar contract
- expressions / look-at conventions
- avatar-grade export/import target

### Composition / Pipeline Truth

Authoring and composition format:

- `OpenUSD`

Why:

- layered non-destructive composition
- references, overrides, variants
- strong DCC and pipeline interoperability

OpenUSD is the composition truth, not the lightweight runtime truth.

### Material / Look Interchange

Material exchange:

- `MaterialX`

Why:

- open material/look description interchange
- better cross-tool authoring portability

### Texture Transport

Portable runtime texture container:

- `KTX 2.0`

Why:

- GPU-oriented compressed textures
- runtime-friendly transport

### Compatibility Lane

Secondary compatibility export:

- `FBX`

Why:

- still widely consumed
- useful for downstream compatibility

But:

- not the canonical truth
- not the schema anchor

## Environment Portability Stack

Environment products have a similar but not identical stack.

Primary lanes:

- `.glb` or scene asset bundle for runtime interchange
- `OpenUSD` for layered composition and authoring
- manifest + scene metadata sidecars
- optional standalone web viewer/export

Environment exports carry:

- object placement
- semantics/taxonomy blocks
- support/blocker/portal metadata
- utility/workstation metadata
- visual asset references

## Character Product Package

Every portable character package should be able to ship with:

- primary `.glb`
- optional `.vrm`
- optional `.usd` / `.usdz`
- optional `.fbx`
- textures, ideally KTX2 when appropriate
- material/look metadata
- embodiment metadata
- joint map / attachment map
- clip inventory
- scale/origin policy
- root-motion policy
- manifest

### Required Sidecar Concepts

At minimum, the character sidecar contract must define:

- `rig_family`
- `reference_pose`
- `joint_map`
- `attachment_points`
- `locomotion_profile`
- `clip_index`
- `expression_profile`
- `scale_policy`
- `origin_policy`
- `root_motion_policy`
- `collision_proxy_policy`

## Character Runtime Facility and Mount Contract

The character product carries its own runtime facility.

That runtime facility is what becomes a live mounted character when bound into an environment.

It is not a separate product, and it should not be treated as an external process by default.

Minimal mounted character shape:

```js
{
  character_runtime_id: 'resident_primary',
  environment_ref: 'validation_habitat_v2_20260325',
  character_ref: 'character://resident_primary',
  state: 'idle',
  pose: {
    world_position: { x: 0, y: 0, z: 0 },
    facing_yaw: 0
  },
  command_surface: {
    version: '1.0.0',
    verbs: [
      'mount',
      'unmount',
      'focus',
      'set_model',
      'move_to',
      'stop',
      'look_at',
      'play_clip',
      'queue_clips',
      'stop_clip',
      'set_loop',
      'set_speed',
      'get_animation_state',
      'play_reaction'
    ]
  },
  animation_surface: {
    available: true,
    active_clip: 'idle',
    active_clip_raw: 'Idle',
    active_clip_source: 'native',
    paused: false,
    loop_mode: 'repeat',
    speed: 1,
    override_active: false,
    queue: [],
    queue_cursor: 0,
    contract_clip_count: 12,
    native_clip_count: 32,
    last_command: '',
    last_reaction: '',
    updated_ts: 1774790000000
  },
  perception_surface: {
    support_key: '',
    visible_object_keys: [],
    occluded_object_keys: [],
    focus_key: ''
  },
  capability_surface: {
    granted_tools: [],
    active_utility_keys: []
  },
  memory_surface: {
    namespace: 'character.resident_primary'
  }
}
```

### Rules

1. The mounted character is not stored in the environment object registry as a normal scene object.
2. The character runtime facility belongs to the character product.
3. The character runtime consumes environment-side facilities when mounted.
4. The mounted character can read scene objects and interact with them.
3. Scene objects remain taxonomy-classified substrate entities.
5. Perception is computed from mounted character pose, not from a scene-object surrogate.
6. Commands bind to the mounted character runtime, not to a prop pretending to be a character.

## Command and Perception Surfaces

The character runtime facility should continue to use the multi-surface model already established:

1. structured world state
2. symbolic perception state
3. direct command surface
4. memory
5. activity history
6. tool grants via utility objects
7. optional visual perspective

This remains correct.

What changes is the host container:

- these surfaces belong to the character runtime facility
- they do not belong to a scene object kind

### Animation Surface

The mounted runtime must expose animation state as a first-class surface, not as hidden workbench UI
state.

Minimum required fields:

- `available`
- `active_clip`
- `active_clip_raw`
- `active_clip_source`
- `paused`
- `loop_mode`
- `speed`
- `override_active`
- `queue`
- `queue_cursor`
- `contract_clip_count`
- `native_clip_count`
- `last_command`
- `last_reaction`

Implementation rule:

- animation commands bind to the mounted runtime facility
- clip resolution uses the existing contract/native resolver lane
- workbench remains an inspection surface, not the canonical control surface

## Object Taxonomy Relationship

The scene taxonomy remains valid for scene-side objects:

- support surfaces
- solid blockers
- portals
- landmarks
- utility objects
- workstations
- fabrication objects
- containers
- transport objects
- tools/instruments
- interface objects
- passive props

Correction:

- agent embodiments should not remain a scene-object taxonomy class
- embodiments belong to character products
- mounted character runtime belongs to the character product and integrates with the environment at mount time

So the taxonomy should describe what mounted characters operate through, not what characters fundamentally are.

## Theater Workbench Mode

Workbench mode should support:

1. environment workbench
2. character workbench

### Character Workbench Requirements

- isolate one embodiment as the whole theater subject
- orbit and zoom for close inspection
- root/origin visualization
- attachment point visualization
- clip preview
- material and texture inspection
- portability validation readouts

This is the correct place to solve:

- origin placement
- clip metadata
- portability issues
- attachment consistency

before the character is mounted into an environment as a live runtime entity

## Portability Validation Gates

Character products should not ship until they pass portability gates.

### Gate A: Geometry and Transform Hygiene

- clean origin
- clean scale
- declared up-axis policy
- no accidental baked offset
- stable reference pose

### Gate B: Skeleton and Embodiment Contract

- rig family declared
- joint map valid
- attachment points declared
- clip index present

### Gate C: Runtime Asset Validation

- `.glb` loads cleanly
- textures resolve correctly
- clips are present and named/mapped correctly

### Gate D: Specialized Avatar Validation

If humanoid avatar lane is present:

- `VRM 1.0` validates

### Gate E: Cross-Tool Composition Validation

If pipeline lane is present:

- USD composition package opens correctly
- material/look references resolve

### Gate F: Cross-Engine Sanity Validation

The character package should be checked in:

- Blender
- Unity
- Godot
- Unreal

The goal is not engine-specific perfection in every case.

The goal is:

- no catastrophic transform or rig breakage
- predictable import
- no “flying model” class of portability failure

## Migration from v132

What remains reusable from the committed v132 work:

- perception builder logic
- camera binding logic
- command surface ideas
- support/blocker taxonomy concepts
- mirror/debug surface ideas

What must change:

- stop representing the mounted character runtime as `npc::*` inside the scene registry
- stop grounding and locomotion through a scene-object surrogate
- move mounted pose/state into a character runtime facility store
- mount the character asset through the character runtime facility into the environment

## Immediate Next Deliverables

1. Refactor the actor out of the scene object registry.
2. Preserve the environment object taxonomy for scene-side substrate only.
3. Add workbench mode for character-scale inspection.
4. Define character portability sidecar schema in more detail.
5. Define the character-runtime-to-environment-facilities mount contract explicitly.
6. Resume command/perception work only after the character runtime container is correct.

## Non-Goals

This spec does not require:

- a game engine pivot
- combat systems
- permanent physics simulation
- autonomous NPC sandbox behavior as default
- image-model vision as the primary cognition channel

## Summary

Champion Council should author both scenes and characters inside the same theater.

But the canonical architecture must separate:

- environment products
- character products
- the mount contract between environment facilities and character runtime facilities

The actor/runtime layer belongs to the character product.

It mounts into environments.

That separation is what makes portability, runtime embodiment, and cross-engine export sane.

## Desktop Companion Renderer Adaptation

The theater Three.js renderer adapts for desktop companion delivery with these changes:

| Theater | Desktop |
|---|---|
| Orbit camera | Fixed orthographic or tight perspective |
| Environment lighting + HDR | Simplified: 1 directional + ambient |
| Visible ground plane | Transparent shadow catcher |
| Full-scale scene | Character fills ~100-200px |
| All LODs | Lowest LOD only, <20k triangles |
| Full post-processing | Minimal or none (alpha channel issues) |

What transfers directly from the theater renderer:

- GLB/VRM loading pipeline
- AnimationMixer + clip resolver
- Rig detection + joint mapping
- animation_surface state tracking
- All animation command handlers
- Character command surface

The desktop companion is a new runtime host, not a new renderer. The character product is the same. The mount contract is the same. Only the shell and the environment perception surface differ.

Full spec: `docs/DESKTOP_COMPANION_ARCHITECTURE_SPEC_2026-03-29.md`
