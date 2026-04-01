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

## Current State

Committed HEAD is now:

- `802e038` Add blank model theater builder subject (Slice 1)
- `0bde3e7` Add structure-mode builder editing commands (Slice 2 - bone edit, chain isolate, blueprint save/load)

Current local worktree contains an uncommitted Slice 3a interaction patch in:

- `static/main.js`
- `server.py`

Slice 2 is complete and live-validated:

- `workbench_set_bone`
- `workbench_isolate_chain`
- `workbench_save_blueprint`
- `workbench_load_blueprint`
- structure-mode editing loop closed

Current local Slice 3a adds:

- `_envBuilderInteraction`
- `workbench_select_bone`
- `workbench_set_editing_mode`
- click selection on builder helper/scaffold meshes
- selected/hover highlighting
- mirrored selection state in `workbench_surface`
- session persistence for selection and editing mode

Current live truth for Slice 3a:

- direct select via env control works
- click selection works
- real bone ids reach the mirror
- `editing_mode` survives refresh

Current open issue:

- `selected_bone_id` restore across refresh is not yet proven cleanly
- do not commit Slice 3a until that restore edge is fixed

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

The workbench mirror is now materially stronger than this brief originally assumed:

- mirrored `workbench_surface`
- agent-facing scaffold toggle/readback
- builder blueprint readback
- current selected bone readback
- current editing-mode readback

That does not change the deeper architectural fact below, but it does change what can be reused for the next layer.

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

## Selection Substrate

The selection substrate is now the practical bridge between whole-body builder work and part-focused authoring.

Current doctrinal shape:

- `selected_bone_id` identifies the active part
- `hover_bone_id` is transient feedback only
- `editing_mode` remains separate from structure truth
- selection belongs to interaction/session state, not blueprint state

The current workbench already supports:

- direct command selection
- click-to-select in the builder theater
- mirrored selection state in `workbench_surface`

This means the next layer should extend the existing workbench interaction substrate, not invent a separate part-editing runtime.

## Body-Part Authoring Substrate

The next serious extension after selection is a body-part-focused work cell inside the same workbench.

This is not a new theater mode.

It is a narrower focus scope inside the same character builder:

- `body`
  - current whole-skeleton builder view
- `part`
  - central isolated part work cell with reference rack
- later `cluster`
  - multi-part grouping derived from bones

The intended body-part authoring view is:

- one central active work cell
- eight surrounding reference slots
- arranged as two layers of four around the main work cell
- each slot independently visible, hideable, promotable, and replaceable

The central work cell is the live editable target.

The rack is a comparison and checkpoint substrate.

The rack is not the procgen system itself.

## Subtarget Contract

Body parts should become first-class observer subtargets, not fake scene objects.

Start with bone-only identity:

- `character_runtime::mounted_primary#bone:<bone_id>`

Do not introduce separate `#chain:` or `#cluster:` identities yet.

Chains and clusters should be derived views over the selected bone:

- chain = current ancestor/descendant walk
- cluster = named grouping resolved from registries/lookup tables

Derived part surface contract:

```json
{
  "part_key": "character_runtime::mounted_primary#bone:upper_arm_l",
  "bone_id": "upper_arm_l",
  "canonical_joint": "upper_arm_l",
  "parent_id": "shoulder_l",
  "child_ids": ["lower_arm_l"],
  "mirror_of": "upper_arm_r",
  "length": 0.18,
  "orientation": [0, 0, 0.35],
  "roll": 0,
  "radius_profile": [0.05, 0.04],
  "enabled": true,
  "world_anchor": [0, 0, 0],
  "world_bounds": { "min": [0, 0, 0], "max": [0, 0, 0] },
  "local_basis": {
    "forward": [0, 0, 1],
    "up": [0, 1, 0],
    "right": [1, 0, 0]
  },
  "adjacent_part_keys": [
    "character_runtime::mounted_primary#bone:shoulder_l",
    "character_runtime::mounted_primary#bone:lower_arm_l"
  ],
  "chain_ids": ["chest", "shoulder_l", "upper_arm_l", "lower_arm_l", "hand_l"],
  "isolated": false,
  "editing_mode": "structure"
}
```

This contract should be derived on demand from:

- `_envBuilderSubject.bones[]`
- family registries
- live mesh world state

Do not store this contract as a second truth.

## Variant Rack Model

The body-part rack should live in interaction state, not blueprint state.

Suggested shape:

```json
{
  "enabled": false,
  "layout": "ring_8",
  "active_compare_slot": -1,
  "promoted_slot": -1,
  "slots": [
    {
      "slot_id": 0,
      "occupied": false,
      "label": "",
      "content_type": "none",
      "source_bone_id": "",
      "source_part_record": null,
      "visibility": true,
      "pinned": false
    }
  ]
}
```

Start with mixed slot content types:

- `frozen_clone`
- `capture_plane`
- `none`

Delay `live_linked` until the flat rack is stable.

Critical rule:

- blueprint save/load never includes rack contents
- rack state is a workbench interaction substrate, not authored anatomy truth

## Camera / Perspective Recipes

Do not author camera arrays per body-part type.

Part-local camera recipes should derive from:

- `world_anchor`
- `world_bounds`
- `local_basis`

That way dynamically generated or newly added parts inherit the same observer treatment automatically.

The existing theater vision system should remain authoritative:

- `capture_focus`
- `capture_probe`
- `capture_supercam`
- `probe_compare`

These commands should learn to resolve part subtargets rather than being replaced.

Expected adaptations:

- `capture_focus(part_key)`
  - frame the selected part bounds
- `capture_probe(part_key)`
  - build a multi-angle atlas from derived part camera recipes
- `capture_supercam(part_key or part cluster)`
  - broader comparative survey around the part and its local context
- `probe_compare(part current vs slot snapshot)`
  - compare live center state against a rack snapshot

## Build Order

Revised post-Slice-3d build order:

1. Slice 3a
   - selection substrate
   - landed
2. Slice 3b
   - derive and expose part surface contract
   - landed
3. Slice 3c
   - part-local camera recipes
   - extend observer/capture target resolution to part subtargets
   - landed
4. Slice 3c.1 / 3c.2
   - visual selection grammar
   - display scopes
   - landed
5. Slice 3d
   - structure-mode gizmo bridge
   - `local_offset`
   - part work-cell staging
   - part-aware focus rig
   - landed
6. Slice 4a
   - `pose_state` substrate
7. Slice 4b
   - reset verbs
   - `workbench_clear_pose`
   - `workbench_reset_bone`
8. Slice 4c
   - `joint_limits` data model
9. Slice 4d
   - pose-mode gizmo
10. Slice 4e
    - timeline / key-pose data model
11. Slice 4f
    - clip compiler into the existing playback contract
12. Slice 4g
    - `docs/rode.txt` milestone naming

Do not add recursive sub-grids until the flat 8-slot rack has survived real use.
Defer flat-rack comparison work until the structure and pose authoring loop is stable.

## Immediate Implementation Sequence

1. Add `pose_state` as a separate live overlay on top of structure.
2. Add reset verbs for pose and structure cleanup.
3. Add `joint_limits` as the guard-rail layer.
4. Add pose-mode gizmo control on top of `pose_state`.
5. Add timeline / key-pose shared state.
6. Compile authored motion into the existing playback contract.
7. Resume rack / frozen-clone comparison work after the structure and pose loop is stable.

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
  - add the post-structure-authoring milestone naming after Slice 3d

## Invariants

The following rules should remain hard constraints:

- one theater
- one renderer
- one observer system
- one builder truth for structure
- structure and pose remain separate mutation paths
- scaffold derives from structure, not pose
- body-part views reuse existing theater/capture infrastructure where possible
- rack state is interaction state, not blueprint state
- recursive sub-grids wait until the flat rack is stable

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
- blank/preset builder subject exists
- structure-mode editing loop is real
- selection substrate exists locally
- theater vision system exists and should be reused
- body-part authoring now needs a subtarget and comparison substrate, not a second scene

What does not exist yet:

- `pose_state`
- reset verbs
- `joint_limits`
- pose-mode gizmo
- timeline / key-pose substrate
- clip compiler
- flat 8-slot reference rack

The right move is not to overload the imported-model helper path.

The right move is to build a true blank/preset character-builder subject in the same theater, with:

- skeleton first
- scaffold second
- shell third

That is the clean path from current code to the generative body-building system the user is actually describing.
