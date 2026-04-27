# NPC Perception And Grounding Spec

Status: Draft
Date: 2026-03-25
Scope: Post-v132 stabilization and next-step runtime hardening

## Purpose

Define the next implementation target after `v132` so inhabitant presence becomes reliable in real scenes.

This spec covers:

- grounding and support-surface rules
- blocker taxonomy
- floor / wall / overhead distinctions
- first-pass perception surfaces
- operator spectator requirements

It does not cover:

- combat
- equipment
- multi-inhabitant orchestration
- full image-model vision loops
- procgen rebuild

## Why This Exists

`v132` proved that one inhabitant can exist in the theater and be controlled through the existing runtime seams.

What it did not solve cleanly:

- some scenes use large visual shell meshes instead of explicit support surfaces
- terrain is currently a visual substrate, not authoritative physical terrain
- inhabitant placement can sample the wrong support if scene semantics are weak
- the inhabitant still has no perception surface

This spec turns inhabitant presence from "visible" into "grounded and situationally aware."

## Current Truth

The runtime already has:

- canonical inhabitant runtime state
- spawn / despawn / focus controls
- behavior-driven movement seams
- grid pathing
- live/shared-state mirror

The runtime does not yet have:

- authoritative support classification
- no-under-scenery guarantees
- field of view
- line of sight
- perceived-object state
- spectator views for inhabitant perspective

## Primary Goals

1. The inhabitant must stand on valid support, not under scenery and not on arbitrary prop tops.
2. The inhabitant must know what counts as floor, wall, ceiling, overhead, blocker, and pass-through.
3. The inhabitant must expose a first-pass perception state that can later feed model reasoning.
4. Operators must be able to inspect inhabitant perspective without interrupting runtime operation.

## Support Surface Rules

### 1. Valid Standable Support

Treat these as valid support surfaces:

- `tile`
- `substrate`
- objects with semantic role `floor`
- objects with semantic role `transition`
- objects with semantic role `path`
- objects with semantic role `platform`
- objects whose semantic text clearly implies ground/support:
  - floor
  - ground
  - foundation
  - base
  - deck
  - platform
  - walkway
  - path
  - road
  - terrain

### 2. Invalid Standable Support

Do not stand on:

- arbitrary prop tops by default
- `wall`
- `ceiling`
- `overhang`
- `canopy`
- `light`
- `landmark`
- `target`
- `reference`
- `marker`
- `zone`
- `decal`
- `vegetation_patch`

### 3. Explicit Override

If an object needs to be standable despite its normal classification, it must say so explicitly through authored semantics or data.

Recommended explicit fields:

- `data.support_surface = true`
- `data.walkable_surface = true`
- `semantics.role = floor|platform|transition|path`

### 4. Grounding Rule

The inhabitant should be snapped so its bottom rests slightly above the highest valid support under its X/Z.

Do not use:

- raw default kind height alone
- visual terrain alone
- arbitrary highest hit without semantic filtering

## Blocker Taxonomy

Every scene object should be interpretable into one of these runtime blocker classes:

- `support`
  - valid walking / standing surface
- `solid`
  - blocks passage and line of sight
- `overhead`
  - above the inhabitant, not a standing surface
- `decorative`
  - visible but non-blocking
- `soft`
  - may be traversed or ignored at first pass
- `portal`
  - opening / threshold / doorway / transition

### First-Pass Mapping

Recommended initial mapping:

- `tile`, `substrate`, floor/path/platform semantics -> `support`
- wall/cliff/barrier/facade semantics -> `solid`
- ceiling/roof/overhang/canopy semantics -> `overhead`
- decal/marker/zone -> `decorative`
- vegetation_patch -> `soft`
- portal/gate/door/archway -> `portal`

This classification should drive:

- navigation blocking
- line-of-sight occlusion
- support sampling
- recovery placement

## Navigation Requirements

### Required

- pathing should avoid `solid` blockers
- pathing should prefer reachable `support` surfaces
- recovery placement should reject unsupported points
- the inhabitant must not route under scenery unless that space is explicitly valid

### Not Required Yet

- ladders
- jump links
- climbing
- crouch volumes
- physics-based stepping

## Perception v1

Perception v1 is symbolic, not image-model-based.

### Required Fields

Add a bounded inhabitant perception state with:

- `fov_degrees`
- `sight_range`
- `visible_object_keys`
- `visible_focus_key`
- `last_seen`
- `occluded_object_keys`
- `support_key`
- `grounded`

### Required Operations

- forward direction from current facing
- FOV cone test
- line-of-sight ray tests
- visibility filtering by blocker class
- recent-memory retention for last seen objects

### Non-Goals For v1

- continuous image capture
- multimodal model inference per frame
- semantic segmentation
- depth maps
- expensive observer capture loops

## Spectator / Operator Requirements

Operators must be able to inspect inhabitant perspective without interrupting runtime behavior.

Minimum spectator surfaces:

- follow camera
- orbit around inhabitant
- quick toggle between overview and inhabitant perspective
- visible display of current target / support / visible object count

Later:

- multi-inhabitant camera wall
- per-inhabitant debug panels
- optional render-target first-person preview

## Runtime Contract Additions

### Inhabitant State

Add to inhabitant runtime state:

- `grounded`
- `support_key`
- `support_kind`
- `perception`

### Shared / Live Mirror

Expose in live/shared payloads:

- grounded yes/no
- support object key
- visible object count
- primary visible object key
- occluded object count

## Validation Criteria

The implementation passes when:

1. The inhabitant no longer spawns under floor-covering scene meshes.
2. The inhabitant no longer snaps onto arbitrary tower/prop tops unless explicitly marked standable.
3. The inhabitant can report what surface it is standing on.
4. The inhabitant can report a bounded set of visible objects in front of it.
5. The mirror exposes grounding and perception state over MCP.

## Recommended Execution Order

1. Finalize support-surface classification and grounding rules.
2. Move nav blocking to blocker taxonomy rather than kind-only shortcuts.
3. Add perception v1 state and LOS checks.
4. Add spectator/debug view controls.
5. Only then consider image-based or model-consumed vision.

## Relationship To Roadmap

This is Path A after `v132`.

It is the practical bridge between:

- visible inhabitant presence

and

- future character products that can operate reliably across varied scenes.
