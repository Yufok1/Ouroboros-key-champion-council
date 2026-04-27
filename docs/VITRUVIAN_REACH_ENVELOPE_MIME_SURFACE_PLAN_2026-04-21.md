# Vitruvian Reach Envelope / Mime Surface Plan 2026-04-21

Purpose:

- granulate the Vitruvian / mime-wall / reach-envelope idea into a concrete, queryable contract
- keep it downstream of the existing blackboard / text-theater / `sequence_field` authority spine
- avoid reactivating deprecated continuity-side `adrenaline` or abstract `shutter` language
- give proc-gen a usable grammar for invisible contact surfaces and camera-facing motion

## Core Read

The useful primitive is not "make the humanoid dance."

It is:

```text
body probe -> perceived boundary -> contact intent -> force response -> capture boundary -> phase-wave sequence
```

The Vitruvian body is the calibration subject.

The mime surface is a generated boundary in that subject's perceptive reach:

- camera plane
- hand reach shell
- foot reach shell
- head/crown focus shell
- force-wave edge
- Cage corridor wall
- invisible pressure plane

That surface is allowed to be "empty space" visually, but it must be represented as structured data before any proc-gen movement treats it as real.

## Existing Anchors

Documented anchors:

- `docs/OPUS_CALIBRATION_KNEEL_VITRUVIAN_RESPONSE_2026-04-13.md`
- `docs/OPUS_CORRECTED_TRAJECTORY_REPORT_2026-04-13.md`
- `docs/THE_CAGE_DBZ_SHOWCASE_SEQUENCER_PLAN_2026-04-21.md`
- `docs/CAGE_HAIR_FIELD_TOPOLOGY_PLAN_2026-04-21.md`
- `docs/CONTINUITY_NAMING_DEPRECATION_RECORD_2026-04-20.md`

Live/source anchors:

- `shared_state.text_theater.snapshot`
- `snapshot.blackboard`
- `snapshot.sequence_field`
- `snapshot.sequence_field.force_wave`
- `snapshot.workbench.selected_bone_ids`
- `snapshot.workbench.active_controller`
- `snapshot.balance`
- `snapshot.contacts`
- `snapshot.output_state.tinkerbell_attention`
- `snapshot.output_state.pan_probe`
- `snapshot.output_state.trajectory_correlator`

## Naming

Use concrete names:

- `range_gate`: joint/articulation limit visibility
- `reach_envelope`: body-probe reach boundary visibility
- `mime_surface`: a generated contact-like surface in empty space
- `capture_boundary`: a read/snapshot latch point
- `phase_wave`: in-between sequencing response

Do not use as active runtime names:

- continuity-side `adrenaline`
- abstract continuity-side `shutter`

Those concepts map to:

- `surface_prime`
- `resume_focus`
- `capture_boundary`
- `reset_boundary`

## Blackboard Contract

Add one read-only family beside the already planned `range_gate` family.

### Family: `reach_envelope`

Rows, one per probe point and boundary candidate.

```text
id:              reach_envelope.<probe>.<surface_kind>
family:          reach_envelope
layer:           perception_geometry
source:          workbench + camera + sequence_field
label:           "R hand camera plane" / "head crown force edge"
probe_bone_id:   hand_l | hand_r | foot_l | foot_r | head | chest
surface_kind:    camera_plane | reach_shell | force_edge | cage_wall | pressure_plane
surface_id:      stable id for the generated boundary
intent:          press | slide | recoil | punch_through | hold | trace | catch
distance:        signed distance from probe point to boundary
unit:            "m"
tolerance_state: ok | near | contact | overreach
priority:        selected/leader/anchor weighted
session_weight:  sticky carryover for continuity
anchor:          probe bone id
detail:          compact range/contact bar and force intent
```

### Working Set

```text
reach_envelope_targets:
  - probe_bone_id
  - surface_kind
  - intent
```

Default target population:

- selected bone
- active controller leaders
- active controller anchors
- hands if the sequence phase is punch/guard/catch
- feet if the sequence phase is split/drop/recover
- head/crown if hair topology or camera-facing focus is active

Do not flood the board with every bone.

## Geometry Model

The first implementation should use simple generated planes and shells:

- `camera_plane`: plane through the camera target, normal aligned to camera forward
- `reach_shell`: sphere or ellipsoid centered on the chest/hips neutral center
- `force_edge`: derived from `sequence_field.force_wave.neutral_anchor` and current wave band
- `cage_wall`: corridor boundary from The Cage lane geometry
- `pressure_plane`: operator-authored or sequence-authored temporary plane

No physics authority.

These surfaces are measurement and sequencing aids only.
Support/contact/balance stay authoritative.

## Leg / Balance Read

Legs are the cleanest proof that this system is not just pose styling.

The body is a large suspended mass above negotiated support points.
Every leg placement acts like:

- a pendulum
- a stilt
- a counterlever
- a shock absorber
- a return-path constraint

The useful proc-gen read is:

```text
mass above -> support point -> lever angle -> contact patch -> balance correction -> phase-wave response
```

So the system should not treat leg motion as "move foot to pose."
It should treat leg motion as placement trajectory under load.

For each leg probe, the blackboard should eventually expose:

- support role
- foot/knee contact state
- signed distance to intended support surface
- projected center-of-mass drift
- lever direction
- overreach/underreach band
- safe return path

This is the dangerous-game layer the system has to learn before it earns expressive dance.
Balance is not an after-effect.
Balance is the operating condition that makes the motion believable.

## Proc-Gen Grammar

Every generated motion should choose:

- probe point
- boundary
- intent
- drive gain
- overshoot
- rebound
- settle window
- secondary consumers

Example:

```text
hand_r -> camera_plane -> punch_through -> drive 0.9 -> overshoot 0.18 -> rebound 0.42 -> hair/aura/punch trails inherit
```

Example:

```text
hand_l -> pressure_plane -> slide -> drive 0.45 -> overshoot 0.04 -> rebound 0.7 -> mime-wall contact read
```

Example:

```text
head -> force_edge -> hold -> drive 0.25 -> overshoot 0.02 -> rebound 0.9 -> crown hair topology stabilizes
```

## Tinkerbell / Pan / Dreamer Split

Tinkerbell:

- points at the current probe/boundary seam
- says why that seam matters now
- suggests expected read

Pan:

- measures local truth around the probe
- confirms contact/support/balance constraints
- prevents spectacle from hallucinating mechanics authority

Dreamer:

- can later use `reach_envelope` rows as proposal context
- should not control these surfaces directly at first
- ranker influence belongs after the row family proves stable and readable

## Capture Boundary

The old shutter instinct becomes a concrete capture boundary:

- text render read
- structured snapshot read
- embodiment read
- optional supercam read
- optional probe/camera capture

Capture boundaries can latch:

- selected probe
- surface id
- camera pose
- sequence phase
- force-wave band
- contact/support state
- trajectory return path

They do not freeze the whole runtime.

## Text Theater First

The first visible surface should be text theater / blackboard.

Required text lines:

- `reach_envelope=<probe> <surface_kind> <intent> dist=<m> state=<band>`
- `mime_surface=<surface_id> normal=<camera|force|world> role=<press|slide|hold|break>`
- `capture_boundary=<text|snapshot|embodiment|web> seam=<probe/surface>`

Web theater can get visual effects after the data row is stable:

- translucent plane
- shell/ring
- contact spark
- pressure ripple
- punch-through burst

## Implementation Slice

1. Add a planning-only doctrine now.
2. Add `reach_envelope` builder rows in `static/main.js` after `range_gate` or alongside blackboard construction.
3. Add a compact text-theater blackboard render block for `reach_envelope`.
4. Add on-demand diagnostics for generated surfaces.
5. Only then add web-theater visual consumers.
6. Only after visual/read stability, feed the row family into Dreamer ranking as soft context.

## Guardrails

- no new authority plane
- no new mirror
- no broad Dreamer retune first
- no full-body procedural controller until the row family is readable
- no web-only truth
- no effect lane outranking support/contact/balance
- no deprecated `adrenaline` or abstract `shutter` as active runtime labels

## Bottom Line

This turns "mime around invisible edges" into a concrete procedural generation substrate.

The system can now reason:

```text
what body point is reaching?
what invisible boundary is being treated as real?
what is the intended contact behavior?
what force-wave response should be sequenced?
what capture boundary proves the read?
```

That is the smallest honest shape of the Vitruvian reach system.
