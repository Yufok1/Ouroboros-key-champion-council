# Character Template Spec

Status: Draft
Date: 2026-03-25
Scope: Proof-of-concept individual inhabitant product

## Purpose

Define one minimal character product that proves the contract end-to-end.

This is not a squad template. It is a single-character template that can later be composed into packs or groups.

## Template Goals

The proof product should demonstrate:

1. one visible inhabitant in the theater
2. one portable asset package
3. one bounded command surface
4. one bounded memory layout
5. one deployable runtime package

## Product Identity

The proof character should have:

- stable `character_id`
- display name
- short commercial description
- explicit product version
- explicit capsule mode: free / optional / required

## Embodiment Requirements

Minimum embodiment lane:

- one supported family
- one rig profile
- one locomotion profile
- one visual mode that is cheap and legible now

The first pass may use a sprite, marker, or simple mesh if that is what the runtime can support cleanly.

## Asset Requirements

Minimum shipping set:

- primary runtime asset
- preview image
- product metadata

Preferred lanes:

- GLB first
- VRM optional for humanoid avatar grade
- FBX optional only as a companion export

## Runtime Requirements

The proof character should support:

- enabled / disabled state
- visible position in the environment
- facing direction
- one active behavior
- one active goal
- one camera-binding state

The runtime layer described here belongs to the character product.

It mounts into environment facilities.

It should not be modeled as a normal scene object kind.

The default runtime stance should be idle until an explicit command or objective is assigned. Do not make ambient random wandering the default product behavior.

## Required Capabilities

The proof character should implement at least:

- idle
- move_to
- look_at
- stop
- set_goal
- inspect

Optional in the first pass:

- speak
- follow
- memory writeback beyond simple state

## Command Set

The proof product must expose:

- `character.info`
- `character.status`
- `character.spawn`
- `character.despawn`
- `character.move_to`
- `character.look_at`
- `character.stop`
- `character.set_goal`
- `character.inspect`
- `character.config_get`
- `character.config_set`

## Memory Layout

Use bounded namespaces only.

Recommended first-pass namespaces:

- `character/<id>/profile`
- `character/<id>/state`
- `character/<id>/goals`
- `character/<id>/memory`

Do not introduce shared group/radio namespaces in this template.

## Workflow Bindings

Recommended first-pass workflow ids:

- `character_spawn`
- `character_despawn`
- `character_move_to`
- `character_look_at`
- `character_set_goal`
- `character_inspect`
- `character_stop`

If a command does not need a workflow, it may bind directly to a runtime handler instead.

## Integration Expectations

The proof product should be operable through:

- the theater runtime
- the live/shared-state mirror
- a future HTTP command facade
- a mount contract into environment-side facilities

The first proof does not need Unity, Unreal, or Godot packages yet, but it must be designed so those adapters can wrap it later.

## Product Variations

The same proof character may eventually ship as:

1. asset-only
2. mount-ready
3. live-runtime-backed

Asset-only ships the embodiment package and metadata only.

Mount-ready ships the embodiment package plus runtime/mount metadata.

Live-runtime-backed ships the embodiment package plus a runtime host or hosted runtime dependency.

## Relationship To v132

This template depends on `v132` agent spatial presence.

Without one visible inhabitant in the theater, the proof character is only an API object and does not demonstrate the medium properly.

## Non-Goals

- group behavior
- shared memory across multiple characters
- combat
- equipment
- full commercial embodiment export
- advanced voice stack
