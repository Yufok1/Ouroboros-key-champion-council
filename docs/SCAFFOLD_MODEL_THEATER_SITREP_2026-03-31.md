# Scaffold Model Theater Sit Rep

Status: Active design brief
Date: 2026-03-31
Scope: Blank character-builder theater for skeleton -> scaffold -> body shell authoring

## Purpose

Define the correct next architectural move for model building inside Champion Council.

This brief exists because the current character workbench is real, but it is still fundamentally an imported-model inspection lane. It is not yet the blank or preset character-building theater the user is asking for.

The target is:

- one theater
- one renderer
- one character-product doctrine
- one skeleton truth
- a true builder subject that can start empty or from a family preset

This brief is not a proposal for a second scene runtime.

## Repo-Proven Current State

The current repo already proves several important pieces:

- canonical rig family registry exists
- source-rig detection exists
- canonical joint mapping exists
- a humanoid scaffold slot registry exists and is now data-driven
- the character workbench already exists as a theater mode
- the workbench can inspect bone inventory, clips, retargeting, and helper overlays
- a scaffold helper overlay can be built on top of a mounted imported asset when that asset has a usable canonical joint map

Recent committed arc:

- `17ef0a0` scene-atom schema baseline
- `80270a8` body-authoring contracts
- `21bde2c` body-authoring schemas
- `efabbf0` humanoid scaffold slots migrated to JSON-backed loading
- `643f665` humanoid scaffold slot data source added

Current local worktree also contains an uncommitted control/telemetry patch:

- `server.py`
- `static/main.js`

That local patch adds:

- `workbench_set_scaffold`
- mirrored `workbench_surface`
- agent-facing scaffold toggle/readback

That patch is useful, but it does not change the deeper architectural fact below.

## What The Current System Actually Is

The current scaffold builder is not a blank builder.

It is a helper overlay on a mounted imported model.

The proof is in the current code path:

- `_env3DBuildPrimitiveScaffoldBody(mesh)` requires `mesh.userData._canonicalJointMap`
- it also requires `mesh.userData.assetClone`
- it resolves scaffold pieces by finding actual bones on the imported clone and attaching primitive meshes to them

That means the current scaffold path depends on:

- a mounted runtime mesh
- an imported asset clone
- a detected source rig
- a successful canonical joint map

If those are missing or partial, scaffold build fails.

So the current workbench is:

- imported-model workbench
- helper overlay inspection
- retarget/clip/bone inspection

It is not yet:

- blank model theater
- procedural skeleton authoring
- bone-by-bone topology construction
- family preset instantiation without imported mesh

## Interpreted User Requirement

The request should not be taken as a literal "freeform anything generator from any word instantly."

The durable requirement is:

- start in a blank theater field
- optionally instantiate a family preset
- optionally start from a single seed bone or anchor
- inspect bones individually, by branch, or as a full system
- edit articulation and proportions directly
- orient the whole structure from a chosen anchor or seed point
- derive scaffold regions from that skeleton
- later populate those scaffold regions with Coquina body atoms, surface passes, or both

The intended authoring sequence is:

1. skeleton truth
2. scaffold projection
3. body-shell / atom population
4. palette and surface treatment
5. runtime animation/export validation

This matches the newer embodiment and Coquina doctrine.

## Naming Discipline

Keep these terms separate:

- `skeleton` = canonical joints/bones/topology truth
- `scaffold` = parametric authoring envelope anchored to the skeleton
- `body shell` / `body hulls` / `body atoms` = visible Coquina-mounted body pieces
- `surface pass` = material, skin, decal, palette treatment

Do not let `scaffold` mean both helper envelope and finished visible shell.

## Architectural Decision

The right direction is:

- keep the same theater
- keep the same renderer
- keep the same character-product doctrine
- add a new builder subject mode inside character workbench

The workbench should support three subject modes:

1. `mounted_asset`
   - current imported-model inspection path
2. `preset_skeleton`
   - family preset instantiated without imported mesh
3. `custom_skeleton`
   - blank or seed-bone authoring path

Imported assets remain important, but as:

- validation targets
- retarget references
- compatibility proofs
- optional starting templates

They should not remain the only way to enter character-building theater.

## Required Builder Subject

The missing subject is a procedural authoring object for the workbench, not a scene object and not an imported asset.

Call it a builder subject or skeleton blueprint.

Minimal conceptual shape:

```json
{
  "subject_mode": "preset_skeleton",
  "family": "humanoid_biped",
  "compatibility_profile": "humanoid_strict",
  "anchor_bone": "hips",
  "bones": [
    {
      "id": "hips",
      "parent_id": null,
      "canonical_joint": "hips",
      "length": 0.18,
      "orientation": [0, 0, 0],
      "roll": 0,
      "radius_profile": [0.12, 0.10],
      "mirror_of": null,
      "enabled": true
    }
  ],
  "overlays": [],
  "scaffold_projection": {
    "enabled": true,
    "slot_family": "humanoid_biped"
  }
}
```

This is not a second scene model.

It is a workbench-only authoring subject for the character product lane, analogous to how the mounted runtime is already not treated as a normal environment scene object.

## Visual Layers In The Blank Model Theater

The builder view should expose explicit visual layers:

1. world/grid layer
   - empty field, neutral workbench lighting, orientation axes
2. skeleton layer
   - joints, bones, hierarchy, names, local axes
3. scaffold layer
   - slot volumes, region colors, anchor points
4. body shell layer
   - Coquina hulls and affixes when present
5. surface preview layer
   - palette/material/skin treatment

Every layer should be independently togglable.

Every layer should be inspectable:

- single bone
- branch/chain
- full system

## What "Start Anywhere" Should Mean

For MVP, "start anywhere" should be interpreted as:

- choose a seed bone
- choose an anchor point in the theater
- grow the skeleton outward from that seed
- or instantiate a preset and then re-anchor / isolate any branch

That means:

- start from `hips` for a standard humanoid
- start from `head` or `foot_l` if the user wants a different anchor
- start from a custom root in `custom_skeleton`

What it should not mean yet:

- unbounded topology invention with no family discipline
- skipping canonical naming entirely
- letting every generated part ignore articulation rules

The right balance is:

- disciplined skeleton authoring
- flexible anchor/entry point

## Proof That The Blank Builder Is Feasible

This is feasible inside the existing theater stack.

Why:

- the renderer already supports workbench-focused display logic
- the code already has family registries and canonical joint semantics
- scaffold slots already exist as data records
- bone inventory and helper overlays already exist for imported assets
- Three.js can render procedural joint/bone hierarchies and helper meshes without needing a pre-authored GLB

What is not yet built is the procedural subject itself.

The blank builder is therefore a missing authoring runtime, not a missing graphics capability.

## Honest Boundaries

Near-term truth:

- `humanoid_biped` is ready to be the first real builder family
- `quadruped`, `flying`, `serpentine`, and `vehicle_ship` exist doctrinally as families
- but they do not yet have mature scaffold slot tables or body-authoring follow-through

So the honest first pass is:

- humanoid blank builder first
- custom skeleton seed mode second
- other family presets after the builder subject is stable

For non-humanoid families in the first builder milestone:

- allow preset skeleton display if possible
- do not promise mature scaffold projection/body population until their slot tables exist

## Minimum Viable Blank Builder

The first serious builder slice should do exactly this:

1. Enter a blank character-builder theater with no imported asset required
2. Let the operator choose:
   - `humanoid_biped` preset
   - `custom_skeleton`
3. Let the operator choose a seed anchor:
   - `hips`
   - `head`
   - `foot_l`
   - `custom_root`
4. Render:
   - joints
   - bones
   - hierarchy labels
   - local axes
5. Allow editing of:
   - parent/child relationship
   - bone length
   - orientation
   - mirror pair
   - enabled/disabled state
6. Project the humanoid scaffold layer from the builder skeleton
7. Save/load the blueprint as JSON

Do not require body atoms in the first slice.

Do not require skinning/export in the first slice.

Do not require quadruped scaffold authoring in the first slice.

## Immediate Implementation Sequence

1. Stabilize the current local scaffold control/readback patch and keep it as a useful bridge for imported-model workbench inspection.
2. Add a dedicated builder-subject state model for character workbench.
3. Add an empty character-builder theater mode that does not require `asset_ref`.
4. Add procedural skeleton rendering for builder subjects.
5. Add bone/branch/full-system selection and editing.
6. Add scaffold projection from builder skeleton for `humanoid_biped`.
7. Add blueprint persistence.
8. Add body-plan overlay support.
9. Add Coquina body population into scaffold regions.
10. Add surface-only and hybrid population modes.

## What Must Be Updated In Doctrine

After this direction is accepted, the next docs to update are:

- `docs/CHARACTER_EMBODIMENT_SPEC.md`
  - add builder-subject / blank workbench authoring lane
- `docs/COQUINA_BODY_AUTHORING_CONTRACTS.md`
  - explicitly anchor body population to scaffold builder subjects
- `docs/CONTROL_UNIT_AND_UTILITY_OBJECT_SPEC_2026-03-25.md`
  - replace the older vague workbench-mode note with the real blank-builder direction
- `docs/CHAMPION_COUNCIL_ROADMAP_2026-03-24.md`
  - insert blank model-theater / builder-subject milestone after current scaffold/runtime stabilization
- `docs/rode.txt`
  - add this as the next named milestone once implementation begins

## Questions For Opus

Use this brief to answer these concretely:

1. Should the builder subject live as a new workbench subject mode or as a deeper extension of the mounted runtime lane?
2. What is the exact MVP shape for the blank builder?
3. What should the first preset and first seed-anchor defaults be?
4. How should body-plan overlays integrate with builder subjects before Coquina body atoms land?
5. Which doc should become the single canonical builder doctrine after this brief?

## Bottom Line

Where we are now:

- imported-model workbench exists
- scaffold data exists
- scaffold helper control/readback is nearly operator-complete
- body-authoring doctrine exists

What does not exist yet:

- blank model theater
- procedural skeleton authoring subject
- bone-by-bone builder flow
- scaffold-first builder independent of imported meshes

The right move is not to overload the imported-model helper path.

The right move is to build a true blank/preset character-builder subject in the same theater, with:

- skeleton first
- scaffold second
- shell third

That is the clean path from current code to the generative body-building system the user is actually describing.
