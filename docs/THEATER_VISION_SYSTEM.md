# Theater Vision System

## Purpose

The theater vision system is the Environment tab's primary observation instrument for world-building and scene correction. It exists so agents can see the real theater from multiple angles, tie those images back to the real object graph, and run before/after experiments without inventing a second scene model.

This system is intended to be used actively during environment creation, not only for debugging after the fact.

## Authority Model

The system is authoritative because it reuses existing runtime state:

- normalized scene object records
- normalized scene semantics
- semantic observation captured from the normal object lifecycle
- live 3D meshes and transforms
- render truth
- layout snapshot
- live mirror state
- capture history ring

It does **not** maintain a duplicate scene description.

It should also be able to tell the difference between:

- authored appearance intent
- resolved mesh/material state
- rendered visual outcome

## Capture Commands

Issue these through `env_control`.

- `capture_frame`
  - captures the current observer frame
- `capture_frame_overview`
  - captures a named overview pose
- `capture_strip`
  - captures an orbit strip around the scene
- `capture_supercam`
  - captures a multi-angle survey atlas for whole-scene judgment
- `capture_focus`
  - captures a close inspection of one target object or cluster
- `capture_probe`
  - captures a target-pinned experiment atlas for subtle local work

## Readback Queries

Issue these through `env_read`.

- `query='frame'`
- `query='frame_strip'`
- `query='supercam'`
- `query='probe'`
- `query='probe_compare'`
- `query='debug_state'`
- `query='live'`

The readback payloads return metadata and file URLs into `static/captures/`, plus live observation context such as physics state.

## Best Workflow

### Whole Scene

1. Run `capture_supercam`.
2. Read `env_read(query='supercam')`.
3. If the result is suspicious, read `env_read(query='debug_state')` and `feed(n=...)` before assuming the capture path is broken.
4. Inspect the atlas and identify structural failures:
   - discontinuous walls
   - broken floor continuity
   - isolated props
   - wrong scene scale
   - unreadable sightlines

### Local Experiment Loop

1. Run `capture_probe` on the target object key.
2. Read `env_read(query='probe')`.
3. Read `env_read(query='debug_state')` if the probe metadata looks inconsistent with the visible scene.
4. Make one local change.
5. Run `capture_probe` again on the same target.
6. Read `env_read(query='probe_compare')`.
7. Decide whether the change improved the local cluster.

### Single-Object Inspection

1. Run `capture_focus` on the object key.
2. Read `env_read(query='frame')` or the returned focus payload.
3. Use the target and neighbor metadata to reason about attachment, clearance, and silhouette.

## Probe Metadata

`capture_probe` is the strongest environment-authoring view right now. A probe includes:

- target object identity
- target semantics
- target semantic provenance and confidence
- neighbor set
- neighbor semantics
- target world position and size
- per-tile camera metadata
- per-tile screen-space projections
- local bounds snapshot
- helper suppression state
- render truth and physics snapshot

This makes probe captures suitable for microscopic placement work, not just macro scene review.

Asset-backed objects now also expose a `material_observation` block when available. The observer now measures resolved clone materials and the runtime applies a default asset-tint policy so authored scene colors can actually reach the visible GLTF clone instead of stopping at the hidden primitive base mesh.

Current material observation fields include:

- authored color intent
- authored material override
- asset clone presence
- primitive visibility
- clone mesh/material counts
- resolved submaterial summaries
- dominant resolved color
- tint capability
- tint mode / tint applied state
- tint mismatch flag

Current asset tint policy is intentionally simple:

- default mode is `multiply` when an authored color exists
- transparent/glass-like materials default to `preserve`
- per-object material config can opt into `preserve`, `multiply`, `replace`, or `none`

This keeps the observer and the runtime aligned: authored pigment intent, resolved clone material state, and capture metadata are now tied together through the same path.

Palette grammar should extend this same observer path instead of creating a separate color-debug plane.

Current palette-facing observer targets:

- grouped objects should be able to declare `palette_group` and `palette_role`
- probe and supercam captures should surface `palette_coherence` summaries for grouped objects
- palette checks should validate resolved colors against authored family bounds, not only against single-object tint intent

## Current Strengths

- multi-angle visual confirmation
- tied directly to object keys
- tied directly to object semantics when present
- stable before/after comparison
- physics state exposed in the live payload
- file-backed artifacts for reuse and inspection
- material-resolution telemetry for asset-backed objects

## Semantic Layer

The observer now understands an explicit `semantics` block on scene objects.

Current semantics fields:

- `role`
- `room_id`
- `supports`
- `anchors`
- `priority`
- `placement_intent`

These fields are reused by:

- habitat object export
- focus candidate ranking
- probe target and neighbor payloads
- screen-space projection payloads
- inspector display

They should be preferred over regex-style inference whenever available.

## Automatic Semantic Capture

The runtime now captures semantic context automatically during the processes that already exist:

- `env_spawn`
- `env_mutate`
- snapshot hydrate / load
- profile-kit spawn
- asset-browser spawn

It does this in the existing object normalization path, not in a parallel metadata pipeline.

The automatic lane records:

- `semantics_authored`
  - the explicit semantic fields authored by the operator or tool call
- `semantics_observation`
  - provenance, confidence, evidence, and context such as snapshot/profile/asset ids
- `semantics`
  - the merged final semantic block used by the observer

Current automatic evidence sources include:

- asset metadata already attached to object records
- kind/category/label/meta text already present on the object
- current snapshot context
- active profile-kit context
- active world-profile context

This means agents should prefer the merged semantic contract plus `semantics_observation` before inventing new labels or structural stories.

## Current Limitations

The system is strong, but not infinite. Known limitations:

- many objects still do not have their `semantics` block populated richly enough yet
- automatic capture is strong for role/room/priority/intent, but support and anchor relationships are still mostly authored
- rendered pixel truth is still weaker than resolved material truth; the observer now knows more about clone materials than about final framebuffer samples
- captures are only as good as the scene content and object contracts they observe
- helper suppression and annotation modes are good, but still tunable

## Phase 3 Pixel Truth Direction

The next observer step should strengthen rendered pixel truth without replacing the current pipeline.

Preferred design:

- use a dedicated offscreen observer render target for sampling
- do not read back from the main live renderer unless there is no better fallback
- do not sample from the annotated/composited browser surface
- perform sampling on demand for `focus`, `probe`, and `supercam` work, not as a continuous per-frame cost

The purpose of the offscreen path is to associate three truths cleanly:

- authored appearance intent
- resolved clone material state
- rendered sampled color truth

This should support later mismatch judgments such as:

- authored brown, resolved pale
- resolved brown, rendered washed out
- submesh divergence inside a single asset-backed object
- local palette incoherence across neighboring objects

Phase 3 should stay observer-scoped. It is not a second scene model and not a second control plane.

## What "Perfect" Means Here

"Perfect" does not mean replacing the current pipelines. It means strengthening this one until it can support nearly all environment-authoring decisions.

That would include:

- richer structural object semantics
- stronger support/attachment metadata
- smarter annotation policies by object role
- target-local diff scoring
- experiment loops that can evaluate a single placement adjustment quantitatively and visually

## Implementation Anchors

The core runtime lives in:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js)
- [server.py](/F:/End-Game/champion_councl/server.py)

Key concepts in code:

- observer renderer
- capture queue
- capture ring
- live mirror physics snapshot
- probe compare payload

## Directive For Future Agents

If you are building or correcting a 3D environment, use this system early. Do not rely only on verbal inference from object lists or render telemetry when the observer can give you visual evidence tied to the real object graph.
