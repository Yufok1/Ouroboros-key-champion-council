# Text Theater Glyph Articulation Mapping 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- ground the user's "keyboard legionnaire" / glyph-body idea in the systems that already exist
- map workbench gizmo, bone, and batch-pose authority onto a future glyph articulation layer
- keep glyph articulation as a consumer of existing truth, not a second control plane

Related docs:

- [BUILDER_THEATER_SESSION_HANDOFF_2026-03-31.md](/F:/End-Game/champion_councl/docs/BUILDER_THEATER_SESSION_HANDOFF_2026-03-31.md)
- [TEXT_THEATER_PIVOT_HANDOFF_2026-04-05.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PIVOT_HANDOFF_2026-04-05.md)
- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)

## Bottom Line

The user is not crazy.

The mapping is real.

The repo already has:

- a builder/workbench articulation authority
- gizmo mode and gizmo space control
- canonical bones and selected/posed bone sets
- batch pose commands
- settle/controller preview and commit commands
- mirrored workbench state in snapshot/text theater

What does **not** exist yet is the next layer:

- a glyph rig that treats characters as scaffold/body pieces
- a glyph articulation consumer that reads those existing workbench controls

So the correct read is:

**the articulation control surface already exists**

but:

**the glyph/state-space consumer of that surface has not been built yet**

## 2026-04-11 Data-First Pivot

Later in the same session, the direction narrowed further:

- letters and numbers stay the primary readable data carriers
- blackboard variables and measurements should remain solid text
- future articulated depiction should be limited to non-alphanumeric symbol fields, ascii geometry, and granular fill support

So this file should no longer be read as "build whole bodies out of letters and digits."

The safer and more useful interpretation is:

- keep alphanumerics for state and measurement truth
- let symbolic fields carry contour/orientation experiments
- let dot/block/braille systems blend and stabilize those symbolic fields

## What Already Exists

## 1. Builder / Workbench Control Surface

Corroborated from [BUILDER_THEATER_SESSION_HANDOFF_2026-03-31.md](/F:/End-Game/champion_councl/docs/BUILDER_THEATER_SESSION_HANDOFF_2026-03-31.md):

- `workbench_set_bone`
- `workbench_set_gizmo_mode`
- `workbench_set_gizmo_space`
- `workbench_select_bone`
- `workbench_frame_part`
- display scopes
- part staging / focus rig
- mirrored `workbench_surface`

This is already a real articulation surface over canonical bones.

## 2. Pose / Batch / Settle Commands

Corroborated from [TEXT_THEATER_PIVOT_HANDOFF_2026-04-05.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PIVOT_HANDOFF_2026-04-05.md):

- `workbench_set_pose`
- `workbench_set_pose_batch`
- `workbench_preview_settle`
- `workbench_commit_settle`

This means the system already has:

- single-bone pose writes
- multi-bone pose batch writes
- controller-style corrective pose generation

Those are exactly the kinds of authorities a glyph rig would want to consume.

## 3. Text-Theater Mirror Of That State

Corroborated from [scripts/text_theater.py](/F:/End-Game/champion_councl/scripts/text_theater.py):

- `workbench` diagnostics section exposes:
  - selected bones
  - posed bones
  - gizmo mode
  - gizmo space
  - active controller
  - route report
  - preview clip / speed / loop

That means the text theater already sees the articulation authority.

## The Correct Mapping

The user's proposed mapping is:

- treat a glyph or group of glyphs as a scaffold/body
- treat glyph edges, corners, slants, and fill as geometric material
- let workbench articulation drive those glyph-surface pieces the same way it currently drives bones/parts

That is valid.

But it must be built in the correct order:

1. existing workbench/gizmo/batch-pose remains the authority
2. glyph rig becomes a derived subject model
3. text theater / blackboard / future web-space glyph fields consume that model

## Glyph Rig Model

The clean model is:

### 1. Glyph Box

Each glyph occupies a canonical box:

- width
- height
- baseline
- occupancy mask
- edge/corner descriptors

This is the buoyant reference surface from the glyph orientation spec.

### 2. Glyph Skeleton

Each glyph can be decomposed into scaffold-like parts:

- stems
- bars
- diagonals
- bowls
- corners
- terminals
- voids

Example:

`A`

- left diagonal
- right diagonal
- crossbar
- apex
- interior void

That is already close to a simple articulated body.

### 3. Glyph Joints

A glyph skeleton has attachment/junction points:

- endpoints
- corners
- crossings
- branch points
- void boundaries

These can be treated like mini-joints or anchors.

### 4. Glyph Field

A group of glyph boxes can be treated as:

- a tiled scaffold
- a surface patch
- a contour-following field
- a semantic layer carrying actual symbols

This is the user's "legionnaire" concept.

## How Existing Workbench Controls Map

## 1. `workbench_set_bone`

Current role:

- edits canonical bone structure parameters

Glyph-mapped role:

- edits a glyph-part descriptor
- for example:
  - diagonal slope
  - bar thickness
  - corner flare
  - void width

In other words:

`bone edit` becomes `glyph-part edit`

## 2. `workbench_set_pose`

Current role:

- pose one target

Glyph-mapped role:

- articulate one glyph or one glyph-part
- for example:
  - rotate a slash-derived limb
  - tilt a corner cluster
  - stretch a vertical stem

## 3. `workbench_set_pose_batch`

Current role:

- coordinated multi-target pose update

Glyph-mapped role:

- coordinated field deformation
- for example:
  - a block of `A` glyphs marching in formation
  - a contour patch of `/` and `\\` glyphs rotating as one surface
  - a diagnostic number field wrapping onto a support polygon or body patch

This is probably the most important direct mapping.

Batch pose is already the right mental model for glyph-field articulation.

## 4. `workbench_set_gizmo_mode`

Current role:

- switch rotate / translate / scale behavior

Glyph-mapped role:

- rotate:
  - orientation of glyph or glyph-part
- translate:
  - glyph anchor movement in state space
- scale:
  - glyph occupancy scale or box deformation

This is effectively a glyph-space transform mode selector.

## 5. `workbench_set_gizmo_space`

Current role:

- local vs world articulation frame

Glyph-mapped role:

- local:
  - deform relative to the glyph's own box/cornice
- world:
  - deform relative to state-space/world axes

That distinction matters for:

- object labels
- shirt/sign/newspaper-scale text
- blackboard slates attached to bodies or world surfaces

## 6. `workbench_preview_settle` / `workbench_commit_settle`

Current role:

- generate and commit corrective articulation

Glyph-mapped role:

- preview and commit glyph-field stabilization
- for example:
  - settle a text surface so it remains legible under perspective change
  - settle a glyph patch around a scaffold segment
  - settle a diagnostic overlay against a moving support/configuration

This is the correct controller logic for keeping glyph fields coherent instead of haphazard.

## Character Classes That Map Best

Not every character has the same articulation value.

### 1. Constant orientation scaffold glyphs

Best examples:

- `|`
- `-`
- `_`
- `/`
- `\\`
- `(`
- `)`
- `[`
- `]`
- `<`
- `>`
- box-drawing glyphs

These are the most useful because they behave like reusable edge/corner/body primitives.

### 2. Semantic alphanumeric glyphs

Best examples:

- `8`
- `31.2`
- `yaw`
- `risk`
- `load`

These are useful when you want:

- symbolic identity
- immediate semantic meaning
- stable readable data inside the blackboard

They are not the preferred material for large articulated surface depiction.

### 3. Measurement / telemetry glyphs

Examples:

- digits
- `%`
- `°`
- arrows
- comparison operators

These are essential for blackboard diagnostics because they carry direct meaning and can still behave as shape material.
These should remain in the informative lane first and only borrow minimal shape value second.

## State-Space Rules

The user's important point is correct:

- the tiny default character is not a failure
- it is the reference-world calibration

So the state-space rules should be:

### 1. Reference LOD

If a surface patch can truthfully hold one readable default-size character:

- render the actual character

Examples:

- a shirt print
- a small label
- a newspaper-scale patch
- a distant sign

### 2. Fused LOD

If more legibility is required:

- re-render the same variable as an enlarged fused glyph inside its box

This is the operator menu / blackboard row case.

### 3. Granular LOD

If the renderer needs a larger articulated surface:

- expose non-alphanumeric scaffold/cornice/occupancy structure
- preserve alphanumeric values as separate readable overlay data

This is the symbolic patch / scaffold / state-space accent case.

### 4. Field LOD

If many glyphs act together:

- treat them as a coordinated symbolic field
- keep measurement/value rows separate and readable

This is the contour patch / diagnostic hull / orientation surface case.

## What Should Be Built

## 1. Glyph articulation registry

Needed:

- glyph box metrics
- glyph skeleton decomposition
- joint/anchor descriptors
- edge/cornice descriptors
- glyph class tags

## 2. Workbench-to-glyph adapter

Needed:

- map selected bone ids to glyph rig segments
- map pose batch targets to glyph field clusters
- map gizmo mode/space to glyph transforms

## 3. Glyph field controller

Needed:

- continuity / settle behavior
- perspective-relative re-ranking
- orientation-aware field stabilization

This is the piece that stops the glyph field from looking random.

## 4. Blackboard consumer over glyph field

Needed:

- row families choose glyph vocabularies
- row families protect semantic value readability
- state-space overlays use glyph articulation where appropriate
- same truth, different consumer

## What Must Not Happen

Do not build glyph articulation as:

- a second authority plane
- a replacement for workbench truth
- a random decorative ASCII shader
- an unconstrained per-frame recompute loop

It must remain:

- a consumer of existing articulation truth
- profile-aware
- blackboard-compatible
- and session/projection coherent

## Practical Conclusion

The right sentence is:

**treat glyphs as rigged micro-subjects and glyph fields as batch-poseable surface subjects**

That is the bridge between:

- current workbench/gizmo/batch-pose authority
- future blackboard/state-space glyph surfaces

So the user's instinct is not just poetic.

It is a valid implementation direction.

The repo already has the articulation examples.

What needs to be built now is the adapter and glyph rig.
