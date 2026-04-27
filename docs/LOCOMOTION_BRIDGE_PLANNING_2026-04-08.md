# Locomotion Bridge Planning 2026-04-08

## Purpose

This document scopes the next honest step after visible mechanics, observer anchor, prospect anchor, and env_help alignment:

- not locomotion implementation
- not fake displacement clips
- not hidden translation glued onto in-place studies

It defines how the existing workbench motion lane, mounted runtime movement lane, and support/load substrate should be bridged into grounded locomotion work later.

## Guardrails

- No ghost-skating.
- No arbitrary drag translation that is decoupled from contacts.
- No claim that current motion presets are already true locomotion clips.
- Contact truth and balance truth must remain the same shared substrate used by both theaters, assertions, observer, and prospect.
- The first bridge should stay humanoid-biped first, because the current solver is still feet-first.

## Grounded Current State

### 1. Builder motion studies exist and are verified

The current workbench motion lane is real and healthy:

- `workbench_apply_motion_preset`
- `workbench_compile_clip`
- `workbench_play_authored_clip`
- `capture_time_strip`

The current verified presets are:

- `idle_shift`
- `step_left`
- `brace_crouch`
- `torso_twist`

Mechanics eval is currently green at `32/32`, and the existing strip summaries already expose:

- `support_phase`
- `dominant_support_phase`
- `balance_mode`
- contact/load diagnostics

### 2. Current presets are still in-place studies

Even when a preset implies stepping, the current authored data is still joint-transform animation without displacement metadata.

Current honest classification:

| Preset | Current role | Honest displacement mode | Why |
| --- | --- | --- | --- |
| `idle_shift` | support/readability study | `in_place` | weight shifts but no root travel contract |
| `step_left` | stepping mechanics study | `in_place` | exercises single-support and leg lift, but does not encode world displacement |
| `brace_crouch` | crouch / brace study | `in_place` | double-support bend and recovery |
| `torso_twist` | upper-body articulation study | `in_place` | lower body remains anchored |

### 3. Authored clips exist, but their schema is transform-only

The current authored clip spec stores:

- `name`
- `duration`
- `tracks`
- `compiled_at`
- `source_timeline_duration`
- `source_key_pose_count`

That is enough for playback, but not enough for grounded locomotion. There is no explicit:

- displacement policy
- root trajectory
- contact-phase plan
- balance expectation

### 4. Runtime movement already exists as a separate truth lane

The mounted runtime already has:

- `character_move_to`
- navmesh path request / reroute / stop
- locomotion blend state
- support snapping / authored-support rejection

That means displacement is not missing. What is missing is the controller that couples:

- path intent
- clip semantics
- contact sequencing
- support-frame evaluation
- recovery

### 5. The balance substrate is already good enough to drive later locomotion work

The existing shared substrate already exports the fields that grounded locomotion will need:

- `gravity_vector`
- `support_frame`
- `support_polygon_world`
- `projected_com_world`
- `balance_mode`
- `support_phase`
- contact geometry
- segment/load diagnostics

Observer and prospect now add:

- who is looking
- what is being looked at
- why
- what view is proposed next

That is enough to plan, debug, and later supervise locomotion without inventing a new reasoning plane.

## Required Metadata Additions

The next locomotion bridge should begin by extending clip metadata rather than immediately writing movement code.

## 1. Displacement classification

Every authored clip should eventually declare:

```json
{
  "displacement_mode": "in_place"
}
```

Planned vocabulary:

- `in_place`
  - articulation study only
  - no world displacement claim
- `root_motion`
  - authored displacement track exists
  - playback may move the mounted runtime root directly
- `contact_driven`
  - displacement is validated against contact phases and support truth
  - root advance is not accepted unless contact expectations and balance checks remain coherent

Initial classification plan:

- all current presets and compiled outputs from them default to `in_place`
- no current preset should silently upgrade itself into `root_motion`

## 2. Contact-phase schema

Current `support_phase` is a useful global summary, but locomotion will need per-contact expectations.

Proposed clip-side schema:

```json
{
  "contact_phases": [
    {
      "time": 0.0,
      "contacts": {
        "foot_l": { "state": "planted", "weight_bias": 0.5 },
        "foot_r": { "state": "planted", "weight_bias": 0.5 }
      },
      "support_phase": "double_support"
    }
  ]
}
```

Planned per-contact states:

- `planted`
- `loading`
- `unloading`
- `swing`
- `brace`
- `airborne`

Notes:

- This is proposed metadata, not a live runtime field yet.
- The global `support_phase` summary should remain derivable from the per-contact table.
- First version should stay foot-first and biped-specific.

## 3. Root trajectory format

Locomotion planning needs an explicit displacement track instead of inferring travel from leg motion.

Proposed schema:

```json
{
  "root_trajectory": {
    "space": "world",
    "reference": "support_frame",
    "samples": [
      { "time": 0.0, "position": [0.0, 0.0, 0.0], "yaw_deg": 0.0 }
    ]
  }
}
```

Important distinction:

- `root_trajectory` describes intended embodiment displacement
- CoM samples remain diagnostic truth, not the authoritative travel track

If needed, a later extension can add:

```json
{
  "diagnostic_trajectory": {
    "projected_com_world": [],
    "com_world": []
  }
}
```

That keeps authored travel and derived balance truth separate.

## Bridge Architecture

The bridge should connect three existing lanes, not replace them.

### Lane A: workbench authoring

Existing responsibilities:

- build key poses
- compile authored clips
- preview/play study timelines

Needed additions:

- displacement classification
- contact-phase annotations
- optional root trajectory authoring or capture

### Lane B: runtime displacement

Existing responsibilities:

- `character_move_to`
- nav resolution / reroute
- runtime position and rotation updates
- support snapping and authored-support rejection
- locomotion blend state

Needed additions:

- clip-aware movement controller
- path-to-contact-plan translation
- balance evaluation during movement

### Lane C: support/balance substrate

Existing responsibilities:

- contact/support geometry
- support polygon
- projected CoM
- balance mode
- observer/prospect corroboration

Needed additions:

- movement-time validation of expected contact phases
- recovery triggers based on failed support assumptions

## Proposed Runtime Bridge

The first honest runtime bridge should work like this:

1. Path intent arrives through `character_move_to`.
2. Navigation produces a corridor and short-term goal.
3. Locomotion controller selects a clip family and pace from the current embodiment lane.
4. Clip metadata declares whether the selected motion is:
   - `in_place`
   - `root_motion`
   - `contact_driven`
5. Runtime only accepts real displacement when:
   - a displacement track exists, or
   - a contact-driven controller computes displacement from planted contacts and support truth.
6. On every update tick, balance substrate evaluates:
   - expected contact state
   - actual contact/support state
   - projected CoM vs support polygon
   - current `balance_mode`
7. If the plan degrades, runtime transitions into corrective behavior rather than continuing to "pedal" through failure.

## Recovery Protocol

The recovery ladder should be explicit from the start.

### Nominal

- `balance_mode = supported`
- controller stays on planned clip / planned path

### Mild degradation

Trigger examples:

- support margin shrinking
- projected CoM nearing polygon edge
- planned planted contact getting noisy

Response:

- local correction only
- minor pelvis / hips / spine compensation
- preserve current displacement plan

### Failed stance / unstable step

Trigger examples:

- expected planted foot not actually supporting
- support polygon no longer matches plan
- projected CoM leaves the support polygon briefly

Response:

- corrective step or brace candidate
- transition away from nominal clip
- temporarily prioritize support recovery over path progress

### Fall / collapse regime

Trigger examples:

- `balance_mode = falling`
- support plan fully lost

Response:

- abandon nominal locomotion goal
- enter explicit brace / fall lane
- only resume path work after recovery

This should map onto the existing balance-mode vocabulary instead of inventing a second classification system:

- `supported`
- `braced`
- `falling`
- `free_float`

## Observer and Prospect Integration

Locomotion should not be blind to the observer/prospect system that now exists.

### Observer during movement

When locomotion is active, observer intent should be able to shift into:

- `track_motion`
- `verify_balance`
- `frame_contact`

### Prospect during movement

Prospect should be able to propose useful corroboration moves such as:

- overhead full-body view when projected CoM approaches the support boundary
- local foot/contact framing when a planted foot becomes suspect
- alternate side view during brace or stumble recovery

This is not autonomous camera choreography yet. It is structured next-best-view guidance riding on the current rule-based prospect contract.

## Proposed Data Contract Changes

Minimum clip metadata extension:

```json
{
  "name": "step_left",
  "duration": 1.6,
  "tracks": [],
  "compiled_at": 0,
  "source_timeline_duration": 1.6,
  "source_key_pose_count": 4,
  "displacement_mode": "in_place",
  "contact_phases": [],
  "root_trajectory": null,
  "balance_contract": {
    "support_family": "humanoid_biped",
    "recovery_policy": "none"
  }
}
```

Important rule:

- adding the fields is acceptable before populating them richly
- claiming populated locomotion semantics before the metadata is actually authored is not acceptable

## Recommended Implementation Order

### Phase 1: metadata truth

- extend authored clip metadata
- classify all existing presets as `in_place`
- add empty-but-valid `contact_phases` and `root_trajectory` fields

### Phase 2: contact authoring truth

- define contact-phase annotations for the four current presets
- keep them in-place, but annotate expected planted/swing states honestly
- extend mechanics eval to assert contact-phase presence and validity

### Phase 3: root-motion truth

- add support for authored `root_motion` clips without yet enabling contact-driven gait generation
- ensure runtime displacement can be sourced from explicit trajectory data

### Phase 4: contact-driven bridge

- marry runtime path following to contact-phase and support-frame validation
- allow displacement only when the contact contract remains coherent

### Phase 5: recovery integration

- tie runtime failure states to:
  - corrective step
  - brace
  - fall
- reuse the same balance substrate and observer/prospect surfaces

## Validation Plan

The next planning-to-build transition should add evaluation in this order:

1. Clip metadata eval
   - every authored clip reports `displacement_mode`
   - `in_place` is default for current presets

2. Contact-phase eval
   - annotated clips expose expected contact states
   - time-strip summaries remain coherent with clip annotations

3. Runtime bridge eval
   - moving clip does not advance without valid displacement policy
   - runtime path progress and support truth stay aligned

4. Recovery eval
   - induced instability forces transition out of nominal locomotion
   - reported `balance_mode` matches visible/mechanical truth

5. Observer/prospect eval
   - locomotion updates observer intent to `track_motion` when appropriate
   - prospect emits balance/contact verification suggestions during degraded motion

## Research Questions To Keep Honest

- Should `step_left` remain a pure in-place study forever, or should it become the first true `contact_driven` clip after metadata scaffolding exists?
- Is `root_motion` an intermediate product lane, or only a bridge toward `contact_driven` clips?
- What is the minimum first contact set for recovery beyond feet:
  - feet only
  - feet plus hands
  - feet plus knees and hands
- When recovery interrupts path progress, which system owns resumption:
  - nav controller
  - clip controller
  - balance controller

## Immediate Outcome

This planning pass does not authorize locomotion implementation yet.

It does establish the honest next build sequence:

1. extend clip metadata
2. classify current studies correctly
3. annotate contact phases
4. define root trajectory contract
5. only then bridge runtime movement to support/balance truth

That keeps the system on the same substrate-first trajectory:

- diagnostics first
- visible mechanics first
- observer/prospect first
- locomotion only when contact truth and displacement truth can agree
