# Validation Habitat Spec

Status: Active
Date: 2026-03-25
Scope: Canonical zero-based test habitat for Path A and future theater/runtime validation

## Purpose

Define the one environment we should build first now that the substrate is empty.

This habitat is not a showcase scene.
It is not a lore scene.
It is not a content experiment.

It is the canonical environment for:

- grounding tests
- blocker taxonomy tests
- perception tests
- spectator/camera tests
- command-surface validation
- future workflow/facility validation

## Design Rules

1. Build from zero.
2. Every object must have a reason to exist.
3. No large decorative slabs or fake terrain shells.
4. Support surfaces must be explicit.
5. Blockers must be explicit.
6. Sightlines must be legible from overview and focus modes.
7. The scene must remain small, inspectable, and repeatable.

## Environment Role

This habitat is a test instrument.

It should answer questions like:

- can the inhabitant spawn on the correct support?
- can it avoid a solid blocker?
- can it distinguish support from overhead geometry?
- can it report what it sees in front of it?
- can the operator inspect the result clearly?

## Required Zones

### 1. Central Support Pad

Purpose:

- canonical spawn and grounding surface
- first support key
- first focus target

Requirements:

- explicitly marked as standable support
- no ambiguous overlap with other geometry

### 2. Side Support Pads

Purpose:

- validate side placement and off-center support selection

Requirements:

- one east pad
- one west pad
- both explicitly marked standable

### 3. Solid Blocker Lane

Purpose:

- validate path blocking
- validate LOS occlusion

Requirements:

- one west blocker
- one east blocker
- both semantically solid
- enough spacing to test navigation around them

### 4. Overhead / Portal Structure

Purpose:

- validate non-floor geometry above the inhabitant
- validate portal classification

Requirements:

- one central arch/gate/portal structure
- should not become a support surface by accident

### 5. Access Structure

Purpose:

- validate stairs/transition support semantics

Requirements:

- one stair or transition object
- explicit transition/support classification

## Minimum Object Set

The habitat should start with approximately this object set:

- 1 title marker
- 1 central support pad
- 2 side support pads
- 2 solid blockers
- 1 portal/arch structure
- 1 stair/transition structure
- 2 distant reference landmarks

That gives a target range of 8-10 authored objects.

## Semantics Requirements

Every object should declare a semantic role or explicit support override when relevant.

Required authored semantics for the habitat:

- `role = floor|platform|path|transition` for standable surfaces
- `role = wall|rock|barrier` for solids
- `role = portal|gate|archway` for thresholds
- `placement_intent` for every authored object

Use explicit support flags when needed:

- `data.support_surface = true`
- `data.walkable_surface = true`

## Camera Requirements

The habitat must work from:

- overview
- inhabitant follow/focus
- capture focus
- probe comparison

The operator should be able to understand the entire scene from one overview frame without giant occluding shells.

## Spectator Requirements

The habitat must support later spectator surfaces without redesign.

Reserve clear lines for:

- one follow camera
- one orbit view
- one overview capture
- one future per-inhabitant debug panel

## Validation Tasks This Habitat Must Support

### Grounding

- spawn on central pad
- spawn on side pads
- reject unsupported positions
- reject arbitrary prop tops

### Blocking

- route around west blocker
- route around east blocker
- reject path through solid geometry

### Perception

- see a landmark directly ahead
- hide a landmark behind a blocker
- report visible object count
- report visible focus key
- report occluded object count

### Camera / Spectator

- switch overview to follow cleanly
- keep the inhabitant readable in focus mode
- preserve legible overview after returning

## Build Pattern

Use the canonical environment pattern:

1. `env_spawn`
2. `env_mutate`
3. `env_persist`

Do not build the habitat from recycled snapshots.

## Naming

Recommended canonical scene name:

- `validation_habitat_v2_20260325`

If a new revision is needed, increment the suffix rather than mutating doctrine around an unclear scene identity.

## Acceptance Criteria

The habitat is ready when:

1. It is the only saved validation scene.
2. It contains only deliberate authored objects.
3. It has no ambiguous floor-covering shell geometry.
4. The inhabitant can be tested repeatedly without scene confusion.
5. Probe/capture/follow views are readable without cleanup work first.

## Immediate Follow-On

After the habitat is built:

1. validate grounding follow-up code there
2. validate perception v1 there
3. commit the runtime follow-up
4. use this habitat as the canonical Path A test surface going forward
