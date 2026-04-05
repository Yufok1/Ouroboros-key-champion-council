# Balance Settle Trajectory Sitrep 2026-04-05

Scope:

- current ground/contact/load lane status
- why this lane should now be treated as a balance system
- next trajectory for visible settle / rebalance work
- handoff for Opus before the next design or implementation pass

## Core Conclusion

The ground interaction lane is not just a floor-contact patch anymore.

It is already a balance system:

- contact/support truth
- support polygon
- projected center of mass
- stability margin
- dominant support side
- per-segment load/support scores

The next honest step is not just a static "level" widget or prettier load visuals.

The next honest step is:

- visible settle / rebalance behavior
- generated from the same balance truth
- first as builder-side preview/authoring intelligence
- later as runtime balance assist under async character control

The best first product is not an invisible snap correction.

It is a short generated corrective reaction clip:

- bad pose -> recover
- worse pose -> step
- failed recovery -> brace
- failed brace -> fall / collapse

If the generated settle looks good, it can become valuable motion in its own right rather than a hidden cleanup step.

## What Already Exists In Source

### Balance Sensors

The system already computes the main signals a rebalance controller needs:

- `supportingFeet` seed in `static/main.js`
- `projected_center_of_mass`
- `support_polygon`
- `stability_margin`
- `inside_support_polygon`
- `dominant_support_side`
- alerts including:
  - `outside_support_polygon`
  - `stability_risk`
  - `foot_slide_risk`
  - `support_overload`
  - `hand_brace`
  - `knee_brace`

Relevant anchors:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L2507)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L2710)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L2838)

### Pose / Correction Actuators

The builder lane already has direct actuation paths:

- `workbench_set_pose`
- `workbench_set_pose_batch`

Relevant anchors:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L16772)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L16885)

### Async Runtime Surface Already Exists

The mounted runtime already has async-style control verbs and surfaces:

- `character_move_to`
- `character_stop`
- `character_look_at`
- `character_play_clip`
- `character_queue_clips`
- `navigation_surface`
- locomotion blend state

Relevant anchors:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L12148)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L13534)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L14813)
- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L25435)

So the architecture is already split the right way:

- balance sensors exist
- correction actuators exist
- async runtime verbs exist

The missing layer is the controller that ties them together.

## Current Validation State

### Builder-Subject Motion Checks

Builder-side motion is now reading coherently against balance/contact truth.

Mid-scrub validation at `normalized: 0.5` showed:

- `idle_shift`
  - `double_support`
  - both feet grounded
  - `support_y = 0.02`
- `step_left`
  - `single_support_right`
  - `foot_r` planted
  - `foot_l` in swing
  - `support_y = 0.02`
- `brace_crouch`
  - `double_support`
  - both feet grounded
  - `support_y = 0.02`
- `torso_twist`
  - `double_support`
  - lower body remains anchored
  - `support_y = 0.02`

### Capture Corroboration Nuance

`capture_time_strip` reliably writes the time-strip JPG.

But the mirror fields can lag:

- `latest_time_strip_motion_summary`
- `last_time_strip_frame_count`

For some presets this summary settles later than the saved JPG appears.

This should be treated as a corroboration timing seam, not immediate evidence that the preset failed.

### Mounted-Asset Validation Note

`GhostArmature.glb` is not valid planted-feet evidence.

It is useful only for mounted-path plumbing:

- model swap
- clip playback
- probe path

For honest mounted-asset ground validation:

- `npc.glb` is the current better default

`kenney-blocky-characters/character-a.glb` does have feet, but its visual quality is poor enough that it should not be the default inspection subject.

## Important Constraints

### Solver Constraint

The current load/support solver is still feet-first:

- `supportingFeet`

Not yet generic:

- `supportingContacts`

So the first honest settle/rebalance controller should be:

- humanoid-biped first
- builder-first

Do not overclaim hand/knee/elbow load redistribution until the solver is generalized.

### Pose Constraint

Non-root arbitrary offsets are intentionally rejected to preserve scaffold continuity:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js#L16824)

That means the first settle controller should be mostly:

- rotational
- hips/root-aware
- torso/leg/arm counter-rotation

Not "drag every limb anywhere."

## Recommended Next Trajectory

### 1. Builder-Only Settle Preview

Add a builder-side settle operator that reads current balance truth and generates a short corrective reaction.

Suggested commands / concepts:

- `workbench_preview_settle`
- `workbench_commit_settle`
- or equivalent internal helpers first, then command surface later

This should not silently mutate authored work without operator intent.

### 2. Settle Should Generate A Short Reaction Timeline

Do not make the first settle an instant snap.

Instead:

- generate a 3-8 pose corrective micro-timeline
- preview/play it
- optionally bake it into the builder timeline or authored clip

This is the key trajectory shift:

- settle is not just cleanup
- settle can become useful generated motion

This is effectively a reverse-engineered reaction clip capture.

### 3. Reaction Ladder

The first settle logic should branch by severity:

1. mild imbalance
   - ankle strategy
   - hips/spine/chest counter-rotation
2. stronger imbalance
   - step strategy
   - corrective foot placement
3. failed recovery
   - brace strategy
   - hands / knees as visible contact candidates
4. too far gone
   - fall / collapse settle

The visible settle is better than a hidden correction because it shows what the body had to do to survive the pose.

### 4. Make The Woodworker Level A Control Signal

The balance/level instrument should not be display-only.

It can become the driver:

- level error = CoM drift relative to support polygon
- controller maps error -> corrective pose batch
- visible level and corrective motion come from the same truth

### 5. After Builder Settle Works, Bridge Toward Async Runtime

Only after builder settle/rebalance is good:

- add balance assist during `character_move_to`
- let the little dude recover while walking / stopping / turning / looking

That is the realistic bridge toward asynchronous control of the runtime character.

## Practical Product Framing

The best first product is:

- not fully autonomous balance AI
- not hidden auto-fix

It is:

- builder-side visible settle / resettle preview
- generated from current balance truth
- optionally baked into timeline/clip work when it looks good

That gives immediate value:

- less fake posing
- less impossible stance drift
- reaction clips that may actually be worth keeping
- a clean bridge from diagnostics to behavior

## Questions For Opus

1. Does the visible-settle-first trajectory still look like the cleanest next move, or is there a better first control surface?
2. Should the first settle operator emit:
   - a transient preview timeline
   - or a normal authored clip object immediately
3. Does the branch ladder look right:
   - recover
   - step
   - brace
   - fall
4. What is the minimum good first joint set for balance recovery:
   - ankles / knees / hips / spine / chest / shoulders / arms
5. Where should the first operator live:
   - explicit workbench command
   - helper-strip action
   - playbook-driven sequence only

## Recommended Immediate Order

1. Lock the balance-system framing
2. Design builder-side visible settle preview
3. Keep it rotational / root-aware first
4. Use current balance truth as the control signal
5. Only then consider runtime balance assist during async movement
