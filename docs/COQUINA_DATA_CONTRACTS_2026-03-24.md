# Coquina Data Contracts

Status: Draft
Date: 2026-03-24
Baseline commit: `8599b3e`
Depends on: `docs/COQUINA_PROCEDURAL_SYSTEM_SPEC.md`

## Purpose

Define the minimal machine-readable contracts required to implement the coquina procedural system without inventing a parallel runtime model.

This document is intentionally narrower than the coquina system spec. It answers one question:

How do coquina atoms, affixes, palette evolution, and checkpoints fit into the runtime that already exists?

The answer is scenographic, not engine-forking: coquina emits canonical scene objects into the existing substrate.

## Non-Redundancy Rule

Coquina extends the current environment runtime. It does not replace it.

Do not add:

- a second scene object model
- a second asset reference lane
- a second palette application lane
- a second checkpoint store
- a second render/material path
- a second world-profile selection system

Coquina must build on the seams that already exist in `static/main.js`:

- scene object normalization
- appearance normalization
- object `data`
- object `semantics`
- object `mechanics`
- profile kits and world profiles
- tile/substrate procedural geometry
- live/shared-state mirror
- FelixBag/file checkpointing

## Existing Runtime Seams To Reuse

### 1. Scene Object Envelope

The current canonical object envelope already exists and stays canonical:

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
- `semantics`

Coquina outputs are normal scene objects using this envelope.

### 2. Appearance Lane

The current appearance lane already supports:

- `appearance.color`
- `appearance.geometry`
- `appearance.asset_ref`
- `appearance.material`
- `appearance.palette_family`
- `appearance.palette_role`
- `appearance.palette_group`

Coquina must reuse these fields instead of inventing `coquina_appearance` or a second palette block.

### 3. Asset / Geometry Lane

The current runtime already has two geometry source lanes:

- asset-driven objects through `data.asset_pack_id` + `data.asset_id`
- constructive geometry through `kind: "substrate"` or `kind: "tile"` plus `data.recipe` / `data.material`

Coquina atoms must compile into one of those existing lanes.

### 4. Semantics Lane

The current runtime already supports:

- `semantics`
- `data.semantics`
- `data.semantics_authored`

Coquina should place classification, authored overrides, and generation tags into the semantics lane where appropriate, not invent a second semantic system.

### 5. Checkpoint Lane

The project already has working checkpoint/versioning surfaces through:

- FelixBag document/file checkpoints
- persisted environment snapshots
- live/shared-state mirror surfaces

Coquina checkpoints should be stored as normal JSON documents through the existing storage/versioning paths.

## Contract 1: Atom Registry Record

An atom registry record is not a scene object. It is a reusable source descriptor that can be expanded into scene objects later.

### Canonical shape

```json
{
  "id": "wall_slab_rough_01",
  "atom_class": "hull",
  "hull_subclass": "solid",
  "source_kind": "asset",
  "asset_pack_id": "modular-stone-kit",
  "asset_id": "wall-slab-rough",
  "roles": ["wall", "boundary", "structural"],
  "families": ["historical", "sanctuary", "fortress"],
  "scale_class": "local",
  "bbox_meters": [4.0, 3.0, 0.5],
  "natural_orientation": "vertical",
  "support_surfaces": ["bottom"],
  "attachment_surfaces": ["front", "back", "top"],
  "connectors": ["wall_adjacent", "corner_join", "gate_flank"],
  "repeatability": "tileable",
  "palette_family": "cool_stone",
  "palette_role": "dominant",
  "tint_mode": "multiply",
  "detail_affordances": ["trim_top", "trim_bottom", "decal_face", "rib_line"],
  "theme_affinity": ["medieval", "ruin", "sanctuary"],
  "placement_hints": {
    "min_spacing": 0,
    "snap_grid": 2.0,
    "prefer_edge": true,
    "avoid_water": false,
    "floor_only": false
  }
}
```

### Source mapping rules

| Atom source | Existing runtime lane |
|-------------|-----------------------|
| `source_kind: "asset"` | `data.asset_pack_id` + `data.asset_id` |
| `source_kind: "substrate"` | `kind: "substrate"` + `data.recipe` + `data.material` |
| `source_kind: "tile"` | `kind: "tile"` + `data.recipe` or tile-width/depth/material fields |

### Required fields

Always required:

- `id`
- `atom_class`
- `source_kind`
- `roles`
- `families`
- `scale_class`
- `palette_family`
- `palette_role`
- `placement_hints`

Required for hull atoms:

- `hull_subclass`
- `bbox_meters`
- `natural_orientation`
- `support_surfaces`
- `attachment_surfaces`
- `detail_affordances`

Required for asset atoms:

- `asset_pack_id`
- `asset_id`

Required for substrate/tile atoms:

- `recipe`

## Contract 2: Affordance Slot / Channel Record

Affordance slots belong to atoms, not scene objects. They describe where affixes may attach when the atom is expanded.

### Canonical shape

```json
{
  "slot_id": "opening_a",
  "slot_type": "opening_grid",
  "surface": "front",
  "anchor_local": [0.0, 1.2, 0.25],
  "span_meters": [1.8, 2.4],
  "channels": [
    { "id": "cutout", "required": true },
    { "id": "frame", "required": false },
    { "id": "lintel", "required": false },
    { "id": "sill", "required": false }
  ]
}
```

### Storage rule

Store authored affordance definitions under the atom registry record, for example:

- `atom.affordance_slots`

Do not store them as a separate scene graph structure.

### Emission rule

When an atom is expanded into a scene object, the selected affix results become normal child/adjacent scene objects. The slot metadata itself should remain traceable under:

- `data.coquina.affordance_slot_id`
- `data.coquina.affordance_channel_id`

## Contract 3: Generated Scene Object

A generated coquina object is a normal scene object plus coquina provenance.

### Canonical shape

```json
{
  "kind": "substrate",
  "id": "courtyard_wall_01",
  "label": "Courtyard Wall",
  "state": "idle",
  "category": "structure",
  "x": 42,
  "y": 48,
  "scale": 1.0,
  "tilt": 0,
  "appearance": {
    "geometry": "box",
    "material": "stone",
    "palette_family": "cool_stone",
    "palette_role": "dominant",
    "palette_group": "courtyard_walls"
  },
  "data": {
    "material": "stone",
    "recipe": {
      "type": "extrude",
      "points": [[0,0],[4,0],[4,0.5],[0,0.5]],
      "height": 3.0
    },
    "coquina": {
      "generation_id": "coquina_v1_seed42",
      "checkpoint_id": "courtyard_seed42:3",
      "atom_id": "wall_slab_rough_01",
      "atom_class": "hull",
      "hull_subclass": "solid",
      "stage": "structural_placement",
      "rule_id": "district_courtyard",
      "district_id": "courtyard_core",
      "slot_id": null,
      "channel_id": null,
      "material_class": "stone",
      "locked": false
    }
  },
  "semantics": {
    "roles": ["wall", "boundary", "structural"],
    "families": ["historical", "sanctuary"]
  }
}
```

### Mapping rule

| Coquina concept | Existing field |
|-----------------|----------------|
| world-space object | normal scene object envelope |
| asset source | `data.asset_pack_id` / `data.asset_id` |
| constructive source | `kind: "substrate"` or `kind: "tile"` + `data.recipe` |
| palette family | `appearance.palette_family` |
| palette role | `appearance.palette_role` |
| palette variation/audit group | `appearance.palette_group` |
| generated metadata | `data.coquina` |
| structural/semantic role | `semantics.roles` |
| author override semantics | `data.semantics_authored` |

### Rule

`data.coquina` is the extension lane for generation provenance. Do not add top-level fields like:

- `coquina_atom`
- `coquina_stage`
- `generated_by`
- `palette_state`

Those belong under `data.coquina` or the existing appearance/semantics lanes.

## Contract 4: Palette Binding and Surface Class

Coquina should reuse the existing appearance palette fields first:

- `appearance.palette_family`
- `appearance.palette_role`
- `appearance.palette_group`

### Binding model

The canonical surface class identity is:

```text
surface_class_key = palette_family + ":" + palette_role + ":" + material_class
```

Where:

- `palette_family` comes from `appearance.palette_family`
- `palette_role` comes from `appearance.palette_role`
- `material_class` lives in `data.coquina.material_class`

### `palette_group` reuse rule

Reuse `appearance.palette_group` for:

- audit grouping
- seeded palette variation cohorts
- optional local grouping inside one surface class

Do not use `palette_group` as a replacement for the full surface-class identity.

That means:

- surface class answers "what kind of surface is this?"
- palette group answers "which local group or cohort does this instance belong to?"

## Contract 5: Palette Checkpoint Record

Palette checkpoints are JSON records stored through the existing checkpoint/document systems.

### Canonical shape

```json
{
  "checkpoint_id": "courtyard_seed42:3",
  "scene_id": "courtyard_seed42",
  "seed_palette": [
    { "role": "dominant", "L": 0.55, "C": 0.04, "H": 250 },
    { "role": "accent", "L": 0.65, "C": 0.12, "H": 45 }
  ],
  "applied_transforms": [
    { "name": "weathered", "delta_C": -0.02, "delta_L": -0.05 }
  ],
  "per_surface_class_bindings": {
    "cool_stone:dominant:stone": {
      "base_oklch": { "L": 0.50, "C": 0.03, "H": 252 },
      "micro_variance": {
        "delta_L": [-0.03, 0.03],
        "delta_C": [-0.01, 0.01],
        "delta_H": [-2, 2]
      }
    }
  }
}
```

### Runtime application rule

Palette checkpoints do not bypass the current tint/material path.

They resolve into:

- `appearance.color` when a resolved override is materialized
- or the existing `paletteResolve(...)` / tint pipeline inputs through `appearance.palette_*`

In other words: coquina computes palette state, but the existing renderer still applies the color.

## Contract 6: Generation Checkpoint Record

Generation checkpoints are also normal JSON records. They describe the output of one generation pass, not a second scene model.

### Canonical shape

```json
{
  "checkpoint_id": "courtyard_seed42:3",
  "scene_id": "courtyard_seed42",
  "world_profile_id": "historical_sanctuary",
  "seed": 42,
  "grammar_id": "courtyard_v1",
  "palette_checkpoint_id": "courtyard_seed42:palette:1",
  "object_ids": ["courtyard_wall_01", "courtyard_floor_01"],
  "warnings": ["empty_affordance:opening_b"],
  "scores": {
    "silhouette": 0.82,
    "palette": 0.91,
    "budget": 0.88
  },
  "dirty_targets": [
    { "type": "district", "id": "courtyard_core" }
  ],
  "needs_review": false
}
```

### Storage rule

Store these through the existing checkpoint surfaces:

- FelixBag document/file records
- exported JSON snapshots
- live/shared-state excerpts when needed

Do not invent a dedicated `coquina_db` or separate checkpoint backend.

## Contract 7: Author Overrides

Coquina authored overrides should reuse the existing object/data semantics rather than inventing a second authoring store.

### Object-level authored lock

Store on the generated object under:

- `data.coquina.locked`

### Semantic override

Store authored semantic patches under the existing lane:

- `data.semantics_authored`

### Palette pin

Store as:

- explicit `appearance.color`
- plus `data.coquina.palette_locked: true`

This preserves compatibility with the existing renderer and makes the override legible.

## Implementation Rules

### Rule 1

The atom registry is the only new top-level data model introduced by coquina.

Even then, it is not a second scene model. It is a source library that compiles into normal scene objects.

### Rule 2

All generated outputs must round-trip through `_envNormalizeSceneObjectRecord(...)`.

If an implementation cannot express its output as a normal scene object record, it is the wrong implementation.

### Rule 3

Palette evolution must terminate in the current appearance/tint path.

If an implementation bypasses `appearance.palette_*`, `appearance.color`, or the existing material/tint logic, it is building a competing system.

### Rule 4

Constructive coquina blanks should prefer the existing substrate/tile lanes before inventing a new geometry kind.

That means:

- large generated hulls -> `substrate` where possible
- simple repeated floor/wall panels -> `tile` where possible
- asset-authored pieces -> existing asset lane

### Rule 5

Checkpointing should reuse the project's current JSON + FelixBag/file checkpoint model.

If an implementation proposes a second persistence layer for coquina alone, reject it.

## Immediate Deliverables

Before any procgen implementation starts, the first concrete artifacts should be:

1. atom registry JSON schema
2. affordance slot/channel JSON schema
3. palette checkpoint JSON schema
4. generation checkpoint JSON schema

Those should be derived from this document and validated against the existing object contract, not invented independently.
