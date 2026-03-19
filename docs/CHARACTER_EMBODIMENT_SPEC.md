# Character Embodiment Spec

Status: Draft
Date: 2026-03-18
Primary workspace: `F:\End-Game\champion_councl`

## Purpose

Define the canonical architecture for agent-, NPC-, creature-, vehicle-, and sellable embodied-asset grade embodiment in the Champion Council environment runtime.

This spec is meant to do three things at once:

1. preserve the working character seam that already exists in the runtime
2. establish an industry-standard-friendly schema for portable embodied assets
3. create a clean path for imported third-party models to participate in the same runtime through retargeting and fallback lanes

This spec is intentionally broader than humanoid avatars. The commercial target includes humanoids, creatures, mounts, ships, and other embodied assets that can participate in the same runtime contract.

This document is intentionally a spec, not a prompt. It is the reference Opus, Codex, and future implementation prompts should align against.

## Scope

This spec covers:

- runtime entity layering
- embodiment and rig family contracts
- appearance and animation contract boundaries
- third-party import and retargeting lanes
- standards and export targets
- phased roadmap integration

This spec does not cover:

- final combat tuning
- full physics implementation
- procedural mesh generation
- marketplace packaging polish
- DCC-specific authoring tutorials

## Codebase Alignment

This spec is additive to the current runtime. It does not replace the existing environment object contract.

Existing seams already present in `static/main.js`:

- `_envNormalizeSceneCharacter(...)`
- `_envNormalizeSceneObjectRecord(...)`
- `_envSceneCharacterForObject(...)`
- inspector character editing
- asset browser NPC spawn
- GLB loading and `AnimationMixer` hookup
- sprite sheet support
- state-driven clip selection
- movement behavior routines for `idle`, `patrol`, `wander`, `follow`, and `guard`

The implementation rule is:

- preserve current behavior
- add new schema fields in a backward-compatible way
- normalize future embodiment data into the existing render and behavior paths

## Core Principles

### 1. The skeleton contract is canonical

The body plan, rig family, joint map, and attachment points define what an entity is physically capable of.

### 2. Appearance is a projection, not the truth

Meshes, sprites, materials, and render modes are swappable representations of the same embodied entity.

### 3. Runtime entity data and sellable asset data are not the same schema

Scene instance state, AI slot bindings, faction, combat stats, and memory are runtime concerns.

Portable asset definitions, rig metadata, clips, attachments, morphs, and export metadata are asset concerns.

These must not be conflated.

### 4. We use rig families, not one universal skeleton

Humanoids, quadrupeds, fliers, serpentine bodies, and ships should not pretend to share one identical skeleton contract.

### 5. External content must degrade gracefully

Third-party content should work through:

- native compliance
- retargeted compliance
- proxy fallback

Failure to fully comply must not make the object unusable.

### 6. Renderer truth remains singular

`appearance.asset_ref` remains the renderer's single source of truth for the active visual asset.

Other fields may template or normalize into it, but rendering should not branch across multiple asset reference sources.

## Layered Runtime Model

At runtime, an embodied scene object is an environment object with optional agent, character, embodiment, retargeting, appearance, and mechanics data.

### Layer A: Scene Object Envelope

This is the existing environment object shell:

- `kind`
- `id`
- `label`
- `meta`
- `state`
- `category`
- `x`
- `y`
- `scale`
- `tilt`
- `data`
- `appearance`
- `mechanics`

This remains the outer contract because the environment runtime already depends on it.

### Layer B: Agent

`agent` binds cognition/runtime identity to an entity instance.

Example responsibilities:

- council slot binding
- runtime identity
- cognition profile
- memory/profile binding

This layer is runtime-only and is not part of a portable sellable character asset.

### Layer C: Character

`character` describes gameplay and social identity.

Example responsibilities:

- archetype
- role
- faction
- voice
- behavior
- equipment slots in use
- runtime stats or game-state overlays

This is instance-facing. Some pieces may be templated by an asset, but the full layer is runtime-driven.

### Layer D: Embodiment

`embodiment` describes the physical body contract.

This is the missing layer in the current runtime and the most important addition in this spec.

It defines:

- rig family
- rig standard
- reference pose
- joint map
- attachment points
- locomotion class
- proportions
- morph profile
- animation contract
- physics profile

### Layer E: Appearance

`appearance` defines how the entity is currently rendered.

It includes:

- render mode
- active mesh asset
- sprite asset
- material overrides
- LOD profile

This is what the renderer consumes directly.

### Layer F: Retargeting

`retargeting` describes how an imported model is mapped into the canonical embodiment contract.

This layer is required for third-party assets and optional for native assets.

## Canonical Runtime Schema

Example runtime entity shape:

```js
{
  kind: 'npc',
  id: 'merlin-01',
  label: 'Merlin',
  state: 'idle',
  category: 'character',
  x: 50,
  y: 50,
  scale: 1.0,
  tilt: 0,

  agent: {
    runtime_id: 'merlin-01',
    slot_id: 3,
    cognition_profile: 'tactical',
    memory_profile: null
  },

  character: {
    archetype: 'wizard',
    role: 'ally',
    faction: 'order_of_merlin',
    voice: 'gandalf_deep',
    behavior: 'patrol',
    equipment: [
      { slot: 'hand_r', item_id: 'staff_oak' },
      { slot: 'back', item_id: 'satchel_leather' }
    ],
    stats: {
      health: 100,
      mana: 200,
      speed: 3.0,
      attack: 15
    }
  },

  embodiment: {
    family: 'humanoid_biped',
    standard: 'vrm_humanoid',
    reference_pose: 'A_POSE',
    joint_map: {
      hips: 'Hips',
      spine: 'Spine',
      chest: 'Chest',
      neck: 'Neck',
      head: 'Head',
      shoulder_l: 'LeftShoulder',
      upper_arm_l: 'LeftUpperArm',
      lower_arm_l: 'LeftLowerArm',
      hand_l: 'LeftHand',
      shoulder_r: 'RightShoulder',
      upper_arm_r: 'RightUpperArm',
      lower_arm_r: 'RightLowerArm',
      hand_r: 'RightHand',
      upper_leg_l: 'LeftUpperLeg',
      lower_leg_l: 'LeftLowerLeg',
      foot_l: 'LeftFoot',
      upper_leg_r: 'RightUpperLeg',
      lower_leg_r: 'RightLowerLeg',
      foot_r: 'RightFoot'
    },
    attachment_points: {
      hand_r: { bone: 'RightHand', offset: [0, 0.1, 0] },
      hand_l: { bone: 'LeftHand', offset: [0, 0.1, 0] },
      head: { bone: 'Head', offset: [0, 0.2, 0] },
      back: { bone: 'Chest', offset: [0, 0, -0.3] }
    },
    locomotion_class: 'biped',
    proportions: {
      height: 1.8,
      arm_span: 1.8,
      leg_ratio: 0.48,
      head_ratio: 0.15,
      bounding_box: [0.6, 1.8, 0.4]
    },
    morph_profile: {
      blink: 0,
      aa: 0,
      oh: 0,
      happy: 0,
      angry: 0
    },
    animation_contract: {
      locomotion: { idle: 'Idle', walk: 'Walk', run: 'Run' },
      action: { attack_light: 'Attack1', attack_heavy: 'AttackHeavy', hit: 'Hit', death: 'Death' },
      gesture: { talk: 'Talk', emote_wave: 'Wave' },
      facial: { blink: 'Blink' },
      transition: { idle_to_run: 'IdleToRun', run_to_idle: 'RunToIdle' }
    },
    physics_profile: {
      spring_bones: ['hair_chain', 'cape_chain'],
      cloth_groups: ['robe_skirt'],
      ragdoll_on_death: true
    }
  },

  retargeting: {
    source_rig_type: 'vrm_humanoid',
    source_joint_map: null,
    rest_pose: 'A_POSE',
    scale_policy: 'uniform',
    translation_policy: 'hips_only',
    twist_policy: 'preserve',
    status: 'exact'
  },

  appearance: {
    mode: 'mesh3d',
    asset_ref: '/static/assets/characters/merlin.glb',
    sprite_ref: null,
    material_overrides: {
      robe: { color: '#2244aa', roughness: 0.8 }
    },
    lod_profile: {
      lod0: 15000,
      lod1: 7500,
      lod2: 3000,
      lod3: 'billboard'
    }
  },

  mechanics: {
    family: 'prop'
  }
}
```

## Portable Asset Schema

Portable sellable embodied assets must not include runtime-only state like slot bindings, health, or faction.

Canonical portable asset schema:

```js
{
  asset_type: 'embodied_asset',
  asset_id: 'merlin_humanoid_v1',
  family: 'humanoid_biped',
  standard: 'vrm_humanoid',
  version: '1.0.0',

  character_defaults: {
    archetype: 'wizard',
    equipment_slots: ['hand_r', 'hand_l', 'head', 'back'],
    suggested_behavior: 'patrol',
    suggested_voice_type: 'male_elder'
  },

  embodiment: { ... },
  appearance_defaults: { ... },
  export_targets: ['glb', 'vrm'],
  preview: { thumbnail: '...', turntable: '...' },
  provenance: { source: 'native', license: 'commercial' }
}
```

Portable asset data must be usable without any knowledge of:

- slot IDs
- cognition profile
- current faction
- current HP or combat state
- scene placement

Rules:

- portable sellable assets are not limited to humanoids
- `asset_type` is `embodied_asset` because the commercial product line includes creatures, mounts, vehicles, and other embodied non-humanoid assets
- `character_defaults` may provide suggested archetype, equipment slots, and behavior hints, but not authoritative runtime state
- export targets vary by family; VRM is the humanoid avatar lane, not the only sellable lane

## Retarget Profile Schema

Imported third-party models require a dedicated retarget profile.

Canonical retarget profile:

```js
{
  profile_type: 'retarget_profile',
  source_rig_type: 'mixamo',
  target_family: 'humanoid_biped',
  source_joint_map: {
    'mixamorig:Hips': 'hips',
    'mixamorig:Spine': 'spine',
    'mixamorig:Head': 'head'
  },
  rest_pose: 'T_POSE',
  scale_policy: 'limb_normalized',
  translation_policy: 'hips_only',
  twist_policy: 'preserve',
  root_motion_policy: 'extract_optional',
  status: 'partial'
}
```

This profile may live:

- embedded on an entity instance
- embedded on an imported asset record
- in a reusable retarget profile registry

## Rig Families

Initial required rig families:

- `humanoid_biped`
- `quadruped`
- `flying`
- `serpentine`
- `vehicle_ship`
- `custom`

Notes:

- `humanoid_biped` is the first-class interoperability family because VRM exists
- `quadruped`, `flying`, `serpentine`, and `vehicle_ship` are also first-class commercial families through canonical GLB/FBX packaging
- `vehicle_ship` exists so naval systems do not get forced through humanoid assumptions
- `custom` is allowed, but not a substitute for family discipline

### Vehicle Ship Canonical Skeleton Hint

`vehicle_ship` does not need humanoid-style anatomy, but it still benefits from a canonical articulation map.

Minimum recommended canonical joints:

```js
{
  hull: 'Hull',
  rudder: 'Rudder',
  mast_main: 'MainMast',
  mast_fore: 'ForeMast',
  sail_main: 'MainSail',
  cannon_port_1: 'PortCannon1',
  cannon_starboard_1: 'StarboardCannon1',
  flag: 'Flag'
}
```

This is a starter contract, not a maximum contract. Individual ships may expose additional cannon ports, sails, anchors, oars, cargo hooks, and deck mounts.

## Import Lanes

### Lane 1: Native

Our own models built to our embodiment contract.

Properties:

- exact joint compliance
- exact attachment compliance
- exact clip contract
- full export fidelity

This is the premium lane and the foundation for sellable assets.

### Lane 2: Retargeted

Third-party rigged models mapped to the canonical embodiment contract.

Examples:

- VRM humanoids
- Mixamo humanoids
- generic glTF humanoids with usable joints

Properties:

- full or partial animation support
- explicit retarget profile
- no promise of perfect compliance

### Lane 3: Proxy

Noncompliant or static content that can still participate in the runtime at reduced fidelity.

Examples:

- billboard sprites
- static GLBs with no skeleton
- hybrid objects with limited animation

Properties:

- scene presence
- state and behavior participation
- limited or no full-body retargeting

Important rule:

Lane 3 runtime support is not a promise of automatic high-quality rigging for arbitrary meshes.

Full auto-rigging and skinning should be treated as an offline conversion pipeline, not a browser-runtime guarantee.

## Animation Contract

The long-term animation contract should be layered, not flat.

Required channels:

- `locomotion`
- `action`
- `gesture`
- `facial`

Recommended optional channel:

- `transition`

This avoids the future problem of one flat clip map trying to represent:

- walking
- attacking
- talking
- emoting
- facial movement

all at the same time.

The current runtime already supports a flat clip map and state-derived selection. That remains valid as the compatibility layer.

The spec direction is:

- current runtime: flat compatibility
- future runtime: layered channels

Transition clips are optional. If they do not exist, the runtime may crossfade directly between channels. If they do exist, the runtime should prefer them for cleaner state changes like idle-to-run, run-to-idle, jump start/land, and draw/sheathe weapon.

### VRM Expression Naming

When a family or standard supports facial expressions, morph/expression naming should follow VRM 1.0 conventions where possible.

Recommended expression keys:

- emotional: `happy`, `angry`, `sad`, `relaxed`, `surprised`
- blink: `blink`, `blinkLeft`, `blinkRight`
- lip sync: `aa`, `ih`, `ou`, `ee`, `oh`

## Procedural Animation Position

Procedural animation is important, but it should not be treated as the first or only path.

Priority order:

1. native authored clips
2. retargeted imported clips
3. procedural fallback and augmentation

Procedural systems should initially focus on:

- foot grounding
- stride correction
- head look
- upper-body aim offsets
- fallback walk cycles for proxy actors

This is safer than trying to make procedural motion the entire baseline before retargeting is mature.

## Standards

### Runtime Standard

Canonical runtime delivery format:

- `glTF 2.0 / GLB`

### Commercial Family-Agnostic Baseline

Canonical sellable baseline for all supported families:

- `GLB`
- optional `FBX` companion export

This is the baseline for humanoids, creatures, mounts, ships, and other non-humanoid embodied assets.

### Commercial Humanoid Avatar Standard

Canonical humanoid avatar export target:

- `VRM 1.0`

### Commercial Non-Humanoid Standard

Canonical non-humanoid sellable export target:

- `GLB` with family metadata, attachment contract, and animation contract metadata
- optional `FBX` for DCC/toolchain compatibility

### Future Authoring / DCC Interchange

Deferred pipeline-scale interchange:

- `OpenUSD / UsdSkel`

### Optional Exports

Useful but not canonical:

- `FBX`
- texture PNG sets
- thumbnails
- LOD-derived alternates

Rule:

- runtime stays GLB-first
- humanoid commercial avatars additionally target VRM
- non-humanoid commercial assets remain first-class products through GLB-first packaging
- USD remains future-facing, not MVP

## Physics Runtime Note

This spec does not hard-lock a physics engine yet because no dedicated physics runtime is currently integrated in this codebase.

Near-term preferred candidate:

- `cannon-es` for rigid bodies, constraints, buoyancy approximation, and ragdoll scaffolding

Possible higher-fidelity alternative if later justified:

- `ammo.js`

Implementation rule:

- keep `physics_profile` schema engine-agnostic until the actual runtime dependency is introduced

## Migration Rules

### Backward Compatibility

The current runtime already stores meaningful data inside `character`.

Preserve these fields:

- `asset_ref`
- `sprite_ref`
- `anim_set`
- `behavior`
- `voice`
- `equipment`
- `scale`
- `clip_map`
- `sprite_layout`

### Additive Growth

Add these fields without breaking existing objects:

- `agent`
- `embodiment`
- `retargeting`

### Render Rule

Continue normalizing all visual asset decisions into:

- `appearance.asset_ref`

This prevents renderer fragmentation.

### Behavior Rule

Behavior remains a movement/decision concept.

Animation remains a render/embodiment concept.

Do not couple:

- `behavior` directly to clip names

Instead:

- behavior drives targets and intent
- locomotion/action state chooses animation output

## Roadmap Integration

### v128 — SHIPPED

Embodiment schema and migration layer.

Delivered (v128/128a/128b):

- additive `embodiment` and `retargeting` schema on object contract
- compatibility normalization from current `character`
- rig family registry
- canonical joint map definitions
- env_control proxy fix for `sample_now` / `toggle_stream`

### v129

Rapier physics substrate for world and mechanics.

Deliver:

- Rapier WASM integration into the Three.js runtime
- rigid body / collider primitives for scene objects
- gravity, collision response, and trigger volumes
- physics-aware object contract extensions (`mechanics.physics`)
- water buoyancy foundation (surface plane interaction)

### v130

Player character controller on Rapier.

Deliver:

- kinematic character controller (ground detection, slopes, steps)
- input binding (keyboard/gamepad → movement intent)
- camera follow modes (third-person, first-person, orbit)
- collision with world geometry and other bodies

### v131

Retarget import lane and procedural augmentation (merged).

Deliver:

- VRM adapter
- Mixamo adapter
- generic glTF humanoid adapter
- attachment point contract
- grounding and stride correction
- limited fallback locomotion
- proxy-mode actor support

Family-general rule:

- the schema remains multi-family from day one even if humanoid adapters land first for speed

### v132

Combat, projectiles, buoyancy, and ship controller.

Deliver:

- locomotion/action separation
- hit/death/block/talk/emote layering
- combat-ready animation contract
- projectile physics (Rapier raycasts or kinematic bodies)
- `vehicle_ship` embodiment family
- ship locomotion/controller contract (buoyancy + helm input)
- captain agent and ship embodiment separation

### v133

Attachment and equipment runtime.

Deliver:

- slot-based equipment binding
- visual snap points
- stat and silhouette changes

### v134

Commercial export pipeline.

Deliver:

- GLB packaging
- VRM humanoid export
- GLB/FBX packaging for non-humanoid sellable families
- LOD packaging
- preview renders

## Non-Goals For The First Pass

These are explicitly not required for the first implementation wave:

- one universal skeleton for every creature and object type
- runtime auto-rigging of arbitrary third-party meshes
- procedural mesh generation as the core embodiment system
- full facial capture pipeline
- perfect compatibility with every third-party rig on first import

## Immediate Implementation Guidance

When implementation begins, the first coding pass should:

1. introduce `embodiment` and `retargeting` additively into normalization
2. preserve the current character inspector and asset browser behavior
3. keep `appearance.asset_ref` canonical for rendering
4. add a family registry for rig definitions
5. avoid breaking current NPC spawn, clip resolution, or sprite layering

## Quick Start

### To create a new native humanoid asset

1. Model in Blender using the canonical humanoid family expectations and a stable rest pose.
2. Rig to a compatible humanoid contract with clear spine, limb, hand, and foot joints.
3. Author PBR materials and keep runtime texture budgets explicit.
4. Provide minimum locomotion and action clips: `Idle`, `Walk`, `Run`, `Hit`, `Death`.
5. Export as `GLB`.
6. Add portable asset metadata with `character_defaults`, `embodiment`, `appearance_defaults`, and export targets.
7. Validate the output with a glTF validator and family-contract checks.
8. If the asset is humanoid-avatar grade, run the VRM 1.0 export lane.

### To create a new native non-humanoid asset

1. Choose the correct family first: `quadruped`, `flying`, `serpentine`, `vehicle_ship`, or `custom`.
2. Define the canonical articulation map and attachment points for that family.
3. Author the model and clips around that family contract instead of forcing it into humanoid assumptions.
4. Export as `GLB`, and optionally `FBX` for DCC compatibility.
5. Add portable asset metadata with `character_defaults` if applicable, plus family-specific `embodiment` and `appearance_defaults`.
6. Validate joint naming, attachment points, and bounding-box hints before ingest.

## Decision Summary

The canonical direction is:

- body contract first
- rig family first
- retargeting first
- appearance as projection
- portable asset schema separate from runtime instance schema

The immediate practical direction is:

- extend the current runtime seam
- do not replace it
- use standards where they help portability
- avoid over-promising universal runtime auto-rigging

This is the foundation for:

- NPC systems
- creature systems
- ship embodiment
- retargeted third-party content
- sellable humanoid products
