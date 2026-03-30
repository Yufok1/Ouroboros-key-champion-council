# Character Summoning Catalog Spec

Date: 2026-03-30
Status: Draft
Scope: Character-bound object summoning inside the existing theater/runtime substrate

## Purpose

Define the first formal contract for character-bound object summoning.

This is not a new product family and not a second scene runtime. It is a character-product facility that
lets a mounted character enumerate a bound catalog of objects, summon them into the current environment,
and dismiss them again using the existing scene object substrate.

## Governing Rules

1. Reuse the existing scene object runtime. Summoning v1 must be implemented on top of `env_spawn`,
   `env_mutate`, and `env_remove`.
2. Reuse the existing character command surface. Summoning verbs belong beside `character_play_clip`,
   not in a separate transport.
3. Do not require capsule edits for summoning v1 unless a hard substrate block is proven.
4. Do not bundle object-transform expressiveness upgrades into summoning v1.
5. Desktop companion summoning is downstream reuse of this contract, not a separate summoning design.

## Why This Exists

The architecture already implies character-bound summoning across:

- desktop companion Orientation B
- the current object/runtime substrate
- the product manifest
- utility object / workstation doctrine

What is missing is the named contract that ties those layers together.

## Summoning v1 Scope

Summoning v1 includes:

- a `summoning_catalog` manifest block on the character product
- three character verbs:
  - `character_list_catalog`
  - `character_summon_object`
  - `character_dismiss_object`
- object ownership metadata on summoned scene objects
- optional `lifetime_seconds` auto-dismiss
- optional `interaction_radius` on summoned scene objects
- placement relative to the mounted character using the existing scene/object substrate

Summoning v1 does not include:

- per-axis scale
- pitch / roll
- explicit Z / height placement
- decomposed RGBA input
- scene-fragment composition
- full desktop shell implementation
- attachment/equipment behavior on the character body

Those belong to later object-transform or attachment slices.

## Existing Substrate Reused

Summoning v1 must build on these already-proven layers:

1. Scene object record normalization in `static/main.js`
2. Runtime object lifecycle:
   - `env_spawn`
   - `env_mutate`
   - `env_remove`
3. Existing visual control:
   - `appearance`
   - `appearance.material`
   - `mechanics`
   - `semantics`
   - `attachment`
4. Existing character command transport:
   - mounted owned-surface bridge
   - browser helper bridge
   - direct shell `env_control(character_*)`

This means a summoned object is just a normal scene object with a small amount of additional ownership and
lifecycle metadata.

## Manifest Extension

`summoning_catalog` extends the existing character manifest. It should live under `configuration` rather than
forcing a new manifest family.

Minimal shape:

```json
{
  "manifest_kind": "champion.character_product",
  "configuration": {
    "summoning_catalog": {
      "schema_version": "1.0.0",
      "enabled": true,
      "max_simultaneous": 8,
      "dismiss_on_unmount": true,
      "default_lifetime_seconds": null,
      "placement_policy": {
        "mode": "relative_to_character",
        "default_slot": "front_right",
        "default_distance": 1.8,
        "support_policy": "grounded",
        "clamp_scene_bounds": true
      },
      "entries": [
        {
          "id": "candelabra",
          "label": "Candelabra",
          "tags": ["light", "prop", "gothic"],
          "spawn_template": {
            "kind": "prop",
            "label": "Candelabra",
            "appearance": {
              "asset_ref": "static/assets/packs/gothic/candelabra.glb",
              "material": {
                "asset_tint_mode": "preserve"
              }
            },
            "semantics": {
              "role": "prop",
              "placement_intent": "decoration"
            }
          },
          "default_overrides": {
            "scale": 1.0,
            "tilt": 0
          },
          "default_interaction_radius": 2.0,
          "default_lifetime_seconds": null
        }
      ]
    }
  }
}
```

## Catalog Entry Model

Each catalog entry is a named, reusable spawn template.

Required fields:

- `id`
- `label`
- `spawn_template`

Optional fields:

- `tags`
- `default_overrides`
- `default_interaction_radius`
- `default_lifetime_seconds`
- `notes`

`spawn_template` is intentionally a partial scene object record. It should reuse the same object substrate that
`env_spawn` already understands.

## Scene Object Extensions

Summoning v1 adds a small set of optional fields to the normalized scene object contract:

- `owner_key`
  - object key of the owning character runtime or actor
- `summoned_by`
  - command or actor identity that initiated the summon
- `catalog_entry_id`
  - source entry from the owning character's catalog
- `lifetime_seconds`
  - optional auto-dismiss timeout
- `interaction_radius`
  - optional base interaction radius for the summoned object
- `dismiss_on_owner_unmount`
  - defaults to `true`

These fields should be treated as runtime metadata, not a second object taxonomy.

## Character Verbs

### `character_list_catalog`

Returns the mounted character's available catalog entries.

Return shape should be lightweight and agent-friendly:

- `available`
- `entry_count`
- `entries`
  - `id`
  - `label`
  - `tags`
  - `kind`
  - `notes`

### `character_summon_object`

Summons one object from the mounted character's catalog into the current environment.

Minimal request shape:

```json
{
  "entry_id": "candelabra",
  "placement": {
    "slot": "front_right",
    "distance": 1.8,
    "lateral_offset": 0.4
  },
  "overrides": {
    "scale": 1.15,
    "tilt": 18,
    "appearance": {
      "material": {
        "asset_tint_mode": "multiply",
        "color": "#caa76a",
        "emissive": "#ffb347",
        "emissiveIntensity": 0.15
      }
    }
  },
  "interaction_radius": 2.5,
  "lifetime_seconds": 120
}
```

Rules:

1. Resolve the entry from `configuration.summoning_catalog.entries`
2. Merge `spawn_template` with `default_overrides`
3. Merge caller `overrides` on top
4. Compute placement relative to the mounted character
5. Stamp ownership/lifecycle fields
6. Call the existing object spawn substrate

### `character_dismiss_object`

Dismisses a previously summoned object.

Accepted targets:

- specific summoned object key
- specific `catalog_entry_id`
- `dismiss_all: true` for all objects owned by the character

This is a removal/lifecycle verb, not a persistence tool.

## Placement Policy

Summoning v1 uses relative placement only.

The placement solver should derive a world/scene position from:

- mounted character scene/world position
- mounted character facing / yaw
- a simple relative slot
- optional distance / lateral offset

Recommended v1 slots:

- `front`
- `front_left`
- `front_right`
- `left`
- `right`
- `behind`

V1 placement uses:

- existing scene `x` / `y`
- existing `tilt`
- existing uniform `scale`
- existing grounded support logic

V1 does not attempt:

- vertical placement authoring
- pitch/roll
- attachment-to-bone
- formation layout

## Ownership and Lifecycle

Default lifecycle rules:

1. Summoned objects are owned by the mounted character that created them.
2. By default, summoned objects are dismissed when the owner unmounts.
3. `lifetime_seconds` auto-dismisses the object if provided.
4. Dismissal must use the existing object removal pipeline.
5. Summoned objects may be mutated after spawn through the existing object mutation substrate.

This makes summoning a reversible runtime behavior, not silent scene pollution.

## Control and Expressiveness

Summoning v1 already inherits substantial expressive power from the existing object substrate:

- uniform scale
- yaw/tilt
- asset selection
- tint mode
- diffuse color
- emissive color and intensity
- transparency
- metalness / roughness
- wind / reaction / LOD / physics blocks
- semantic role / placement intent
- HTML panel content and actions

That is enough for a meaningful first slice. Do not hold summoning v1 hostage to future transform upgrades.

## Non-Goals

Do not include these in summoning v1:

- per-axis scale (`scaleX`, `scaleY`, `scaleZ`)
- full Euler rotation (`pitch`, `roll`)
- explicit `z` / height placement
- decomposed RGBA authoring
- `character_arrange_objects`
- `character_summon_scene`
- generative object creation
- desktop-only shell behavior

Those belong to later environment-fragment, transform, or attachment slices.

## Relationship To Other Planned Slices

Recommended sequence:

1. `v133c` locomotion blend tree
2. Trust-Graduated Agency Model schema
3. `v134-thin` one utility object + one workstation
4. Summoning spec
5. Summoning v1 implementation
6. `v135` attachment / equipment

Summoning v1 should come after `v134-thin`, because the utility/workstation slice proves that characters can
gain environment-bound capabilities before they start carrying a bound summon catalog.

## Desktop Companion Relationship

Desktop companion Orientation B already implies summoning.

This spec should be treated as the reusable runtime contract that desktop later consumes:

- theater/workbench first
- desktop companion later

The same catalog and verb model should port across both surfaces.

## Implementation Note

The first implementation should stay thin:

- list catalog
- summon object
- dismiss object
- ownership + lifetime
- relative placement

Do not upgrade the scene object transform system in the same slice.
