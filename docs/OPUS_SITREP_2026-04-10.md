# Opus Sitrep 2026-04-10

Use this as the current grounded baseline after the settle removal and pose-authority reset.

## Baseline

- Repo baseline is still `33cae7f` plus the post-baseline rebuild work now in the worktree
- `settle` is removed as a first-class facility from source/help/text-theater/docs
- The load/balance contract restore remains in place:
  - `gravity_vector`
  - `support_frame`
  - `projected_com_world`
  - `support_polygon_world`
  - `balance_mode`
- Manual pose rotations are now authoritative again: the destructive live clampback was removed from the builder pose sanitizer on 2026-04-10

## What Is True In Source

### Settle

- `workbench_preview_settle` and `workbench_commit_settle` were removed from the active command surface
- text theater no longer renders a settle section
- help registry no longer lists settle commands
- docs treat settle as historical only

### Pose Authority

- `_envBuilderSanitizePoseTransform(...)` still normalizes pose payload shape and preserves the non-root offset gate
- Manual rotations are authoritative for the general builder pose path
- `_envBuilderClampPoseMechanics(...)` is now only used as a narrow lower-leg guard rail for `lower_leg_l` / `lower_leg_r`
- No broad pose-wide clampback should silently rewrite live manual edits outside that two-bone guard rail

### Mechanics Substrate

- Load/support/balance truth is still live in source and export paths
- Motion diagnostics still carry:
  - support phase
  - contacts
  - support surface
  - alerts
  - load field
- Current contact candidate lane still includes:
  - feet
  - knees
  - hands
  - head
- The chosen-contact stage realization seam is closed in the current worktree:
  - explicit support-contact staging no longer immediately loses its group-local correction to a generic parent mesh resnap
  - support-floor staging was generalized from foot-only logic to `_envBuilderLowestSupportPatchY(...)`
- Only feet currently have the most mature patch-family treatment

## Product Doctrine

- Dev diagnostics are for building the product, not for shipping the product
- Final product should hide instrumentation and show only believable grounded motion
- Terrain/support truth must become the real ground-contact substrate, not scenery
- Recovery returns later as a runtime controller, not as the deleted settle workflow

## Blackboard / Visual Doctrine

- The blackboard is still a spatial, camera-relative, dynamically repopulating system
- It is not a flat 2D HUD
- It is a dev-mode consumer of the mechanics substrate
- It is not a raw shared-state dump; it is a curated projection of snapshot truth into operator-readable rows
- Immediate space around the model should hold raw measurements
- Background space behind/above the workbench can hold articulated readouts, grouped slates, and explanatory math
- Near-field measurements can connect to far-field readouts via leader lines / indicators
- Visual state should use a graded stoplight spectrum, not a binary red/green alarm view

## Theater-First Verification Doctrine

- After any command that changes staged pose, contact staging, or local builder framing, read the text theater render first
- Preferred order of evidence:
  - `text_theater.current_full/current_compact` when attached to the command result
  - `env_read(query='text_theater_embodiment')` or `env_read(query='text_theater')`
  - `env_read(query='text_theater_snapshot')` for structured corroboration
  - `capture_probe('character_runtime::mounted_primary')` when visual ambiguity or renderer disagreement remains
  - `env_read(query='shared_state')` only as tertiary corroboration
- The render is the cheapest way to catch obvious visual nonsense immediately
- The snapshot is the machine-readable explanation layer
- The probe image is the expensive visual triangulation artifact
- The mirror/shared-state lane can lag and should not be treated as first evidence for theater-affecting edits

## Honest Remaining Seams

1. `scripts/eval_workbench_mechanics.py` was removed on 2026-04-10 by operator directive after the automated knee probe produced bad pose behavior; contact verification now requires live-operator corroboration instead of blind automated pose sweeps
2. `workbench_stage_contact` exists as a deterministic staging gate, not as a router or fake support solver
3. The active blocker is no longer the old realization seam; it is composite support-topology authoring:
   - honest two-knee brace staging now works
   - mixed support sets like half-kneel, tripod brace, and forearm-plank are still awkward to author with raw single-bone rotations
   - multi-target staging still reduces requested contacts independently instead of jointly solving the intended support set
4. The existing batch pose lane is already the canonical mutation surface:
   - `workbench_set_pose_batch` owns atomic coordinated pose commits
   - grouped / chain / marionette-style authoring should feed native `{ poses:[...] }` payloads into that lane
   - do not build a second pose substrate or gizmo-only commit path
5. Pan, the future contact placement router, is not built yet; it should consume blocked/accepted staging reports after primitives and affordances exist
6. Roadmap rigidity is now a real sequencing risk:
   - some later named systems are required earlier in thin contract form
   - if a deferred system is the minimum honest way to close the current blocker, pull forward its contract, not its full implementation
   - current examples:
     - Pan-style route reports over support-topology authoring
     - blackboard-ready grouped-controller / corroboration exports
     - primitive labels attached to support-transition macros and route outcomes
7. `supportingFeet -> supportingContacts` is still not complete; non-foot patch families remain underbuilt
8. Terrain/support records still lean too hard on flat support assumptions
9. Gravity-vector control is present in the contract but not yet exposed as a true live operator lane
10. Runtime recovery/stumble/brace/fall behavior still needs to be rebuilt as a locomotion/runtime system
11. The rich dev-only visual consumers remain partially dormant or missing:
   - scaffold weight dynamics
   - bone carpenter
   - support polygon / CoM / drift / contact overlay
   - richer blackboard consumers
12. The next mobility lane should be framed as a primitive-based reactive controller stack, not a special-case stunt mode:
   - passive rebalance and aggressive traversal should ride the same contact/support substrate
   - see `docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md`

## Recommended Next Trajectory

1. Keep mechanics verification live-operator-driven; do not reintroduce automated pose-sweep evals for contact placement
2. Preserve `workbench_stage_contact` as the deterministic gate for chosen contact targets; do not treat it as a router
3. Treat the existing batch pose lane as canonical:
   - `workbench_set_pose_batch` stays the only commit surface for coordinated builder pose mutation
   - grouped/chain controllers, macros, and future marionette-like handles should emit native batch-pose payloads instead of writing a parallel pose state
4. Build the next operator-facing authoring substrate around support topology and controller parity:
   - grouped multi-bone / centroid pivots
   - chain selection via the existing isolation-chain substrate
   - controller registry per body plan and dynamic grouped-controller allocation from selected chains / pairs / ad hoc selections
   - authored support-transition macros such as `half_kneel_l`, `half_kneel_r`, `rest_kneel`, `tripod_brace_l`, `tripod_brace_r`
   - honest export of grouped preview state for web view, text theater, and future blackboard parity
5. Pull forward thin enabling contracts from later systems when they are the minimum honest path through the current blocker:
   - Pan-v0 route report shape:
     - intended support set
     - realized support set
     - missing support participants
     - blocker summary
     - next suggested adjustment
   - blackboard-ready corroboration/export fields should move early when they are needed for theater parity
   - primitive names may appear early on macros and route reports without claiming the full primitive/runtime system is finished
6. Use those authoring surfaces to continue the mechanics substrate return:
   - generalize from `supportingFeet` to `supportingContacts`
   - add the next patch families
7. Make terrain/support surfaces authoritative
8. Add real gravity-control / reorientation inputs
9. Formalize primitive vocabulary and affordance contracts before building full Pan
10. Build full Pan as the contact placement router:
   - Tinkerbell points
   - Pan routes
   - code stays concrete as `contact_router` / `contact_placement_router`
   - route proposals can later be emitted as workflow DAG artifacts for inspection, replay, and reuse
11. Rebuild runtime recovery as a locomotion/controller lane
12. Rebuild dev-only visual consumers on top of that truthful substrate
13. Keep product mode clean: grounded motion visible, diagnostics hidden

Workflow note:

- do not run live frame mechanics through the MCP workflow engine
- use workflows later for route artifacts, debug recipes, gravity sweeps, and training-data generation only after a live-operator-reviewed protocol exists

## Key Source Anchors

- Pose mechanics reference lane: `static/main.js` `_envBuilderPoseMechanicsSpec(...)`
- Shared pose sanitizer: `static/main.js` `_envBuilderSanitizePoseTransform(...)`
- Timeline compiler: `static/main.js` `_envBuilderTimelineClipDescriptor(...)`
- Balance assert: `static/main.js` `_envWorkbenchAssertBalance(...)`
- Contact staging gate: `static/main.js` `_envWorkbenchStageContact(...)`
- Load-field restore: `static/main.js` load-field return with world-space balance exports
- Text snapshot balance threading: `static/main.js` `_envBuildTextTheaterSnapshot(...)`

## Bottom Line

The project is back on track because the destructive builder seams are being stripped out instead of rationalized:

- settle is gone
- manual pose rotations are authoritative again
- the mechanics substrate is still alive underneath
- the chosen-contact realization seam is closed

The next correct move is not another blind verification harness pass. It is to improve chain-aware posing and support-topology authoring so realistic mixed contacts can be staged intentionally, then keep driving toward terrain-aware support, gravity-aware balance, runtime recovery, and dev-only spatial instrumentation that feeds a clean final product.
