# The Cage Showcase Resource

`The Cage` is the first `showcase_sequence` resource for the humanoid builder/workbench lane.

It is not a scripted autoplay loop.
It is a dynamic authoring resource that the runtime can:

- recognize from timeline/clip/controller context
- interpret into named phases
- expose through `workbench` and `sequence_field`
- render as split-drop / heel-drive / finisher corridors

## Intent

Use `The Cage` as the stream-facing hero sequence:

- camera-facing neutral guard
- controlled lower into split
- exaggerated floor impact
- proud split hold
- heel-driven rise back to neutral
- optional DBZ-style punch finisher

## Resource Contract

Family: `humanoid_biped`

Mode: `showcase_sequence`

Resource id: `the_cage`

Primary surfaces:

- `workbench.sequence_resource_registry`
- `sequence_field.resource_*`
- `sequence_field.split_profile`
- `text_theater_embodiment`
- `text_theater_snapshot`

## Phases

1. `enter_cage`
   Neutral / guard / set.

2. `lower_into_cage`
   Controlled split descent.

3. `cage_impact`
   Floor-hit / contact emphasis.

4. `cage_hold`
   Showboat freeze in the split.

5. `rise_from_cage`
   Heel-driven recovery back upward.

6. `cage_break`
   Camera-facing finisher, typically the punch burst.

## Current Runtime Behavior

When the resource is active, `sequence_field` can switch from generic `strike_corridor` reading into a showcase-oriented read:

- `cage_split_drop`
- `cage_heel_drive`
- optional strike-finisher lanes during `cage_break`

This keeps the sequence dynamic and inspectable while still letting the user author poses and clips directly in the workbench.
