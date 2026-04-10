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
- It no longer rewrites manual rotations through `_envBuilderClampPoseMechanics(...)`
- The shared clamp removal applies across the builder pose path, not to one limb only

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
- Immediate space around the model should hold raw measurements
- Background space behind/above the workbench can hold articulated readouts, grouped slates, and explanatory math
- Near-field measurements can connect to far-field readouts via leader lines / indicators
- Visual state should use a graded stoplight spectrum, not a binary red/green alarm view

## Honest Remaining Seams

1. The new honest eval harness was deleted and has not yet been rebuilt against the current baseline
2. `supportingFeet -> supportingContacts` is still not complete; non-foot patch families remain underbuilt
3. Terrain/support records still lean too hard on flat support assumptions
4. Gravity-vector control is present in the contract but not yet exposed as a true live operator lane
5. Runtime recovery/stumble/brace/fall behavior still needs to be rebuilt as a locomotion/runtime system
6. The rich dev-only visual consumers remain partially dormant or missing:
   - scaffold weight dynamics
   - bone carpenter
   - support polygon / CoM / drift / contact overlay
   - richer blackboard consumers

## Recommended Next Trajectory

1. Rebuild the honest mechanics eval harness against the current post-settle, post-pose-authority baseline
2. Continue the mechanics substrate return:
   - generalize from `supportingFeet` to `supportingContacts`
   - add the next patch families
3. Make terrain/support surfaces authoritative
4. Add real gravity-control / reorientation inputs
5. Rebuild runtime recovery as a locomotion/controller lane
6. Rebuild dev-only visual consumers on top of that truthful substrate
7. Keep product mode clean: grounded motion visible, diagnostics hidden

## Key Source Anchors

- Pose mechanics reference lane: `static/main.js` `_envBuilderPoseMechanicsSpec(...)`
- Shared pose sanitizer: `static/main.js` `_envBuilderSanitizePoseTransform(...)`
- Timeline compiler: `static/main.js` `_envBuilderTimelineClipDescriptor(...)`
- Balance assert: `static/main.js` `_envWorkbenchAssertBalance(...)`
- Load-field restore: `static/main.js` load-field return with world-space balance exports
- Text snapshot balance threading: `static/main.js` `_envBuildTextTheaterSnapshot(...)`

## Bottom Line

The project is back on track because the destructive builder seams are being stripped out instead of rationalized:

- settle is gone
- manual pose rotations are authoritative again
- the mechanics substrate is still alive underneath

The next correct move is to rebuild the truthful verification baseline, then keep driving toward terrain-aware support, gravity-aware balance, runtime recovery, and dev-only spatial instrumentation that feeds a clean final product.
