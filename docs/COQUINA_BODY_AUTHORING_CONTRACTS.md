# Coquina Body Authoring Contracts

Status: Draft
Date: 2026-03-30
Depends on:
- `docs/COQUINA_DATA_CONTRACTS_2026-03-24.md`
- `docs/COQUINA_PROCEDURAL_SYSTEM_SPEC.md`
- `docs/CHARACTER_EMBODIMENT_SPEC.md`

## Purpose

Extend Coquina from scene-atom composition into scaffold-first character body authoring without inventing:

- a second skeleton truth
- a second palette system
- a second affordance system
- a second scene/runtime model

This document is additive. It does not replace the existing scene-atom contracts.

The governing doctrine remains:

- the skeleton contract is canonical
- rig families are canonical
- appearance is projection
- Coquina emits into the existing substrate

## Relationship To Existing Coquina Contracts

`docs/COQUINA_DATA_CONTRACTS_2026-03-24.md` defines scene-atom contracts:

- Contract 1: atom registry
- Contract 2: affordance slots / channels
- Contract 5: palette checkpoints
- Contract 6: generation checkpoints

Those contracts are correct for scenography. They are not enough for body assembly.

Body authoring reuses the same Coquina composition machinery:

- hull vs affix atoms
- affordance slots / channels
- palette family / role / material-class binding
- checkpoint and provenance rules

What changes is the mounting context and the scaffold relationship.

## Non-Redundancy Rule

This contract layer must not introduce:

- a second body-only palette system
- a second body-only affix system
- a second skeleton naming system
- a second checkpoint store
- a second render/material application lane

All body-authoring extensions must compile back into the canonical embodiment and appearance lanes already described in:

- `docs/CHARACTER_EMBODIMENT_SPEC.md`
- `docs/COQUINA_DATA_CONTRACTS_2026-03-24.md`

## Current Code Reality

The current code already contains the seeds of this system:

- `_ENV_RIG_FAMILY_REGISTRY` defines six families and their canonical joints
- `_ENV_SOURCE_RIG_JOINT_MAPS` defines humanoid-only source-rig retarget maps
- `_ENV_SCAFFOLD_SLOT_REGISTRY` defines a humanoid scaffold body in code
- `_envDetectSourceRig(...)` is humanoid-oriented
- `_envCharacterApplyLocomotionBlend(...)` currently assumes an idle/walk/run biped lane

Current family truth in code:

- `humanoid_biped`
- `quadruped`
- `flying`
- `serpentine`
- `vehicle_ship`
- `custom`

Current scaffold authoring truth in code:

- only `humanoid_biped` has scaffold slot geometry today

This contract layer therefore starts with humanoid authoring first and defers other scaffold families until the humanoid path is stable.

## Canonical Naming Rule

All joint references in this contract layer use canonical family joint IDs.

Examples:

- `head`
- `neck`
- `chest`
- `spine`
- `hips`
- `upper_arm_l`
- `lower_leg_r`

Do not use source-rig bone names here:

- not `Chest`
- not `Spine`
- not `mixamorig:Spine`
- not `J_Bip_C_UpperChest`

Source-rig bone naming belongs exclusively to the retargeting layer.

## Contract 8: Body-Atom Mounting Domain

The current atom registry records describe scene atoms. Body atoms reuse the same geometry/composition model, but they mount against a scaffold instead of world placement hints.

### Design decision

Do not overload `atom_class`.

- `atom_class` continues to describe what the atom is:
  - `hull`
  - `affix`
- `mount_domain` describes where/how the atom mounts:
  - `scene`
  - `body`

These are separate axes and must remain separate.

### Canonical shape

```json
{
  "id": "torso_plate_01",
  "atom_class": "hull",
  "hull_subclass": "surface",
  "mount_domain": "body",
  "source_kind": "asset",
  "asset_pack_id": "character-kit-alpha",
  "asset_id": "torso-plate-01",
  "roles": ["armor", "torso", "surface"],
  "families": ["humanoid_biped"],
  "scale_class": "local",
  "palette_family": "dark_metal",
  "palette_role": "accent",
  "body_binding": {
    "scaffold_slots": ["chest", "spine"],
    "tracking_joints": ["chest", "spine"],
    "deform_mode": "skinned",
    "symmetry": "bilateral",
    "region_class": "torso"
  }
}
```

### Required rules

When `mount_domain = "body"`:

- `body_binding` is required
- `placement_hints` is not required

When `mount_domain = "scene"` or absent for backward compatibility:

- `placement_hints` is required as defined in Contract 1
- `body_binding` is absent

### `body_binding` fields

- `scaffold_slots`
  - scaffold slot ids this atom covers
  - must resolve against the scaffold slot table for the selected family
- `tracking_joints`
  - canonical family joint ids this atom tracks at runtime
- `deform_mode`
  - `skinned`
  - `rigid`
  - `cloth`
- `symmetry`
  - `bilateral`
  - `unique`
  - `radial`
- `region_class`
  - semantic body region such as `head`, `torso`, `arm`, `hand`, `leg`, `foot`, `hair`, `horn`, `tail`, `wing`, `accessory`

### Mounting semantics

- `skinned` means the atom is expected to deform with the skeleton
- `rigid` means the atom is mounted to joints/slots but does not deform
- `cloth` means the atom participates in secondary motion or later physics-driven facilities

### Body affordances

Body atoms still use the same affordance-slot/channel model as scene atoms.

Examples:

- armor plates expose trim and decal zones
- hair hulls expose ornament channels
- shoulder hulls expose pauldron or drape slots

There is no separate body-affordance grammar.

## Contract 9: Body-Plan Overlay

Body-plan overlays declare topology variation on top of a rig family's canonical skeleton.

They are the contract for:

- missing limbs
- extra limbs
- extra heads
- tails
- wings
- horns
- other structured anatomy extensions

They are not permission to arbitrarily break the skeleton.

### Canonical shape

```json
{
  "overlay_id": "four_armed_humanoid",
  "family": "humanoid_biped",
  "label": "Four-Armed Humanoid",
  "compatibility_grade": "extended",
  "base_chains": ["spine", "arm_l", "arm_r", "leg_l", "leg_r", "head"],
  "chain_overrides": {
    "arm_l": { "cardinality": 2, "mirror": true },
    "arm_r": { "cardinality": 2, "mirror": true }
  },
  "extra_chains": [
    {
      "chain_id": "tail",
      "root_joint": "hips",
      "segment_count": 4,
      "mirror": false,
      "purpose": "tail"
    }
  ],
  "scaffold_params": {
    "shoulder_width_multiplier": 1.3
  },
  "animation_notes": {
    "locomotion_affected": false,
    "extra_channels_required": ["secondary_arm_motion"],
    "mirror_policy": "procedural"
  }
}
```

### `compatibility_grade`

- `strict`
  - canonical topology only
  - VRM/avatar-safe
  - no extra chains
  - no chain cardinality changes beyond canonical form
- `extended`
  - topology changes allowed
  - extra limbs / extra heads / missing limbs allowed
  - breaks VRM export guarantees
  - GLB-first export lane
- `custom`
  - non-standard family or non-standard topology with no export promise beyond declared packaging

### `chain_overrides`

Per-chain changes on top of the family baseline.

Supported conceptual fields:

- `cardinality`
  - `0` means missing
  - `1` means canonical
  - `2+` means repeated instances
- `segments`
  - optional segment-count override where allowed by the family
- `optional`
  - chain may be omitted
- `mirror`
  - whether the chain expects a symmetric counterpart or mirrored generation rule

### `extra_chains`

New chains not present in the canonical family.

Required concepts:

- `chain_id`
- `root_joint`
- `segment_count`
- `mirror`
- `purpose`

`root_joint` must be an existing canonical joint id from the selected family.

Purpose examples:

- `tail`
- `wing`
- `horn`
- `tentacle`
- `extra_arm`

### `animation_notes`

Body-plan overlays must declare how animation should be interpreted for altered topology.

Important fields:

- `locomotion_affected`
- `extra_channels_required`
- `mirror_policy`

`mirror_policy` values:

- `mirror`
- `independent`
- `procedural`

For v1, `procedural` should be the default for extra appendages so the system is not blocked on authored mutant clip sets.

## Contract 10: Data-Driven Scaffold Slot Registry

The current humanoid scaffold body is hardcoded in `_ENV_SCAFFOLD_SLOT_REGISTRY`.

For scaffold-first authoring, this must become data-driven.

### Canonical shape

```json
{
  "family": "humanoid_biped",
  "slot": "head",
  "joint": "head",
  "geometry": "ellipsoid",
  "default_scale": [0.14, 0.18, 0.13],
  "parametric_ranges": {
    "scale_x": [0.08, 0.25],
    "scale_y": [0.10, 0.30],
    "scale_z": [0.08, 0.22]
  },
  "surface_classes": ["skin", "hair", "horn"],
  "region_class": "head",
  "authoring_anchor": true,
  "up_offset": [0, 0.08, 0]
}
```

### Required fields

- `family`
- `slot`
- `joint`
- `geometry`
- `default_scale`
- `parametric_ranges`
- `surface_classes`
- `region_class`
- `authoring_anchor`

Optional helper fields may include:

- `target_joint`
- `follow_child`
- `project_from_parent`
- `axis`
- `up_offset`
- default debug/display color

### Meaning

- `joint`
  - canonical family joint id the slot tracks
- `parametric_ranges`
  - bounds for authoring-time proportion changes
- `surface_classes`
  - material/surface families that may legally resolve on that region
- `region_class`
  - shared semantic tag used by body atoms
- `authoring_anchor`
  - whether a user can begin authoring from this slot

### Humanoid first-pass slot table

The current humanoid scaffold defaults in code define these slots:

- `head`
- `neck`
- `chest`
- `spine`
- `hips`
- `upper_arm_l`
- `lower_arm_l`
- `hand_l`
- `upper_arm_r`
- `lower_arm_r`
- `hand_r`
- `upper_leg_l`
- `lower_leg_l`
- `foot_l`
- `upper_leg_r`
- `lower_leg_r`
- `foot_r`

These should become the first data-driven family slot table.

### Deferred families

Do not force scaffold-slot authoring for other families into the first pass.

Defer scaffold slot tables for:

- `quadruped`
- `flying`
- `serpentine`
- `vehicle_ship`

Those families already exist doctrinally and in the family registry, but not as a mature scaffold authoring lane.

## Humanoid Compatibility Profiles

These are compatibility profiles, not separate rig families.

### `humanoid_strict`

- standard canonical topology only
- no `extra_chains`
- no non-canonical cardinality changes
- VRM/avatar export safe

### `humanoid_extended`

- topology overlays allowed
- extra limbs / extra heads / missing limbs allowed
- GLB-first export lane
- not VRM-safe

Both profiles still inherit from `humanoid_biped`.

## Validation Rules

### 1. Skeleton truth first

Body-plan overlays and scaffold mutations must compile into a valid skeleton topology before:

- animation binding
- atom expansion
- export

### 2. Canonical naming only

All references in this layer use canonical family joint ids and scaffold slot ids.

### 3. Shared Coquina machinery

Body authoring reuses:

- atom registry machinery
- affordance slot/channel machinery
- palette checkpoint machinery
- checkpoint/provenance machinery

### 4. No body-only palette fork

Palette checkpoints already generalize to body materials. Keys like `warm_skin:base:skin` and `dark_metal:accent:armor_plate` should remain valid through the existing palette model.

### 5. Authoring constraints, not physics promises

Scaffold ranges are authoring bounds. They are not automatically physics constraints.

### 6. Procedural first for mutant appendages

Do not block v1 body-plan overlays on authored clip libraries for every topology permutation.

Default to:

- canonical locomotion on primary chains
- procedural or mirrored secondary motion on extra chains

## Sequencing

This document is a contract-layer draft only. It does not require immediate code changes.

After this document, the next steps are:

1. schema files for Contracts 8, 9, and 10 under `schemas/coquina/`
2. extend `atom-registry.schema.json` with `mount_domain` and conditional `body_binding`
3. migrate `_ENV_SCAFFOLD_SLOT_REGISTRY` from hardcoded JS into data
4. tag existing CC0 assets as scene atoms first, body atoms later
5. build the palette resolver against the existing checkpoint/material lane
6. build scaffolded character assembly on top of the scaffold/body-plan/atom contracts

## Decision Summary

The correct extension is:

- family contract first
- body-plan overlay second
- scaffold slot registry third
- body-mounted Coquina atoms fourth
- animation/export validation on top

Not:

- arbitrary mesh kitbashing first
- source-rig naming in body contracts
- a second body-only Coquina system
