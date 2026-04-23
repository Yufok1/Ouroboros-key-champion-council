# The Cage DBZ Showcase Sequencer Plan

Purpose:

- take `The Cage` from authored key-pose corridor to fluid camera-facing showcase
- keep the existing workbench/timeline/text-theater/web-theater/weather carriers
- stage the plan locally in `docs/` and mirror it into the FelixBag planning surface

## Core Read

The gap is not pose authoring.
The gap is the sequencer between the authored poles.

Current runtime already has the right substrate:

- `The Cage` showcase resource and phase vocabulary
- authored pose batch plus timeline cursor
- pose interpolation between timeline key poses
- weather/rain as a camera-reactive field consumer
- text theater and web theater as peer consumers of shared truth

The next build should not replace those systems.
It should use them to produce fluid in-between motion, force depiction, and camera-facing spectacle without turning the sequence into a horror slideshow.

## Target Showcase

Stream-facing target:

- JCVD split drop
- heel-drive recovery
- camera-facing punch corridors
- DBZ-style force bursts between punch poles
- articulated hair / aura carrier for over-nine-thousand energy reads
- repeated "split-ups" where the body rises and drops through the split with controlled camera-facing intent

The intended feel is not ragdoll.
It is the opposite:

- purposeful reverse-ragdoll
- every move is intentional
- every valve of force sequences into the next valve of force

## Build Split

### 1. Pole Authority

Keep the authored poles authoritative:

- pose batches
- timeline key poses
- phase ids
- contact phases
- support/load truth

The sequencer does not replace authored poles.
It rides between them.

### 2. Fluid Bridge Between Poles

Add a bounded sequencer layer between key poses:

- consume `sequence_field`, phase id, contact phase, route/support state, and camera context
- turn authored poles into motion corridors instead of raw snapshot hops
- bias interpolation by phase intent:
  - `split_drop`
  - `floor_shock`
  - `showboat_hold`
  - `heel_drive`
  - `camera_break`

This is the main anti-slideshow lane.

#### Phase-Wave Contract

Do not treat in-between motion as plain interpolation.
Treat it as a phase-linked wave:

- `drive`
- `overshoot`
- `rebound`
- `settle`
- `handoff`

The target pose is not the end of the motion.
It is the center of a bounded force answer that the next articulation can inherit.

That means:

- hit the pole
- pass through it slightly
- recoil toward support truth
- settle enough to hand force into the next phase

This is the first honest bridge between the authored poles and the elemental/weather-style force read.

#### Vitruvian Dance Mobilization System

Name the neutral-center cycle:

- `Vitruvian Dance Mobilization System`

Use that as the showcase/doctrine label for the center-driven phase-wave loop.
Keep the runtime fields literal and boring.

#### Neutral-Center Loop

Use a truthful neutral center as the axle of the cycle.
For the humanoid showcase lane, this is the Vitruvian-style neutral reset.

The practical loop is:

- `neutral_center`
- `left_pole`
- `neutral_center`
- `right_pole`
- `neutral_center`

This is not a static rest pose.
It is the bicycle axle and Pac-Man wrap gate for the whole showcase:

- every extreme returns through one known-good embodied center
- mirrored phases can trade momentum across that center
- Tinkerbell and Pan get a stable recurring seam to point at and measure
- capture/corroboration consumers get consistent checkpoints at center and poles

#### Overshoot Parameters

The first bounded parameter family should be:

- `drive_gain`
- `overshoot_pct`
- `rebound_damping`
- `settle_window_ms`
- `phase_offset_map`
- `camera_answer_gain`
- `secondary_lag`
- `secondary_gain`

Interpretation:

- `drive_gain` pushes the articulation toward the next pole
- `overshoot_pct` controls how far it passes the pole before recoil
- `rebound_damping` determines how quickly force collapses toward support truth
- `settle_window_ms` defines how long the sequence gets to become legible again
- `phase_offset_map` lets limbs, torso, hair, aura, and punch fields inherit the same wave at different times
- `camera_answer_gain` lets the sequence visibly answer the current lens direction without breaking support truth
- `secondary_lag` and `secondary_gain` make hair/aura/trails read as force consumers rather than detached garnish

#### Shutter / Capture Read

This fits the old adrenaline/shutter intuition, but the live doctrine should stay concrete.

The actual runtime read is:

- neutral center = stable latch point
- poles = force emphasis points
- Tinkerbell = pointer to the current seam
- Pan = local support/contact measurement
- capture shutters = honest snapshot boundaries

So the sequence can "dance" with the model by cycling through recurring latch points instead of trying to recover from arbitrary mid-motion drift.

### 3. Elemental Force Carrier

Reuse the existing weather/particle field idea as the visible force carrier:

- render force between punch poles as field streaks, arcs, or bursts
- let hair/aura/steam/energy read as articulated force consumers
- keep text theater and web theater as peer consumers of one shared sequence/effect truth

This means:

- weather-like fields stop being just rain proof-of-concept
- they become the first elemental showcase substrate

### 4. Camera-Facing Control

Use the current orienting stack for spectacle, not just diagnostics:

- Tinkerbell points the current seam that matters
- Pan measures contact/support truth so spectacle stays physically legible
- camera-facing finishers can keep aiming toward the current lens/target without breaking support truth

This is the right place for:

- punch poles aimed at camera
- split-up reps that follow the camera honestly
- finisher corridors that stay readable during live orbit

### 5. Character Infusion

Treat character effects as articulated consumers, not detached cosmetics:

- hair can become an energy direction carrier
- aura can become a phase-pressure readout
- punch trails can show corridor direction and burst timing
- heel-drive can leave wake/readout in the same effect family

The effect lane should color inside the existing body/scaffold/object surfaces rather than floating as unrelated garnish.

#### Shared Wave Inheritance

Secondary systems should not invent their own random motion.
They should inherit the same phase wave with different gain and lag:

- hair = high lag, medium overshoot
- aura = low lag, high amplitude
- punch trails = low lag, pole-aligned burst
- steam/air streaks = medium lag, fast decay
- text/particle weather = field carrier aligned to punch corridor and camera answer

This is the bridge between "weather" and "animation":

- weather stops being isolated proof-of-concept
- sequence force becomes a field
- each consumer renders the same force truth in a different material

### 6. Camera-Velocity Escalation

The Super Saiyan read should not be a fixed costume toggle.
It should be a live escalation response:

- slow camera motion keeps the sequence in lower-energy readable form
- faster camera motion can raise the visible energy state
- very fast orbit/handheld camera can push hair/aura/punch-field expression into a hotter "keeping up" band

This makes the character communicate with the operator's eyes:

- camera speed becomes a bounded expressive input
- the sequence can visibly answer the camera without losing phase truth
- the faster you drive the view, the more the hero can "power up" to stay legible

Important limit:

- camera speed can scale spectacle
- camera speed does not override support/contact/balance truth
- this is an expression escalator, not a mechanics authority

## Runtime Contract

The clean contract is:

```text
authored poles
  -> phase-aware sequencer
    -> corridor / force field packet
      -> text theater consumer
      -> web theater consumer
      -> capture/corroboration consumers
```

Important rule:

- effects do not become authority
- support/contact/balance remain authority
- sequence and force consumers express the motion truth; they do not override it

## Existing Carriers To Reuse

Local/runtime anchors:

- `static/main.js` `The Cage` resource
- `static/main.js` timeline pose interpolation
- `sequence_field.*`
- `text_theater_snapshot`
- `text_theater_embodiment`
- weather/web overlay consumer lane

Planning/doctrine anchors:

- `docs/THE_CAGE_SHOWCASE_RESOURCE_2026-04-17.md`
- `docs/WEATHER_WEB_OVERLAY_SITREP_2026-04-14.md`
- `docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md`
- `docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md`

## Staging Order

1. Expand `The Cage` from resource-only doctrine into a sequencer plan with explicit corridor/effect lanes.
2. Keep key-pose authority and add phase-aware in-between sequencing.
3. Reuse the weather/field substrate for punch/hair/aura force depiction.
4. Make text theater render the sequence/effect truth clearly enough that web theater is not the only readable consumer.
5. Add web-theater effect consumers for stream-facing spectacle.
6. Only after the sequence looks honest should the JCVD split-up and DBZ finisher variants widen.

## Guardrails

- do not create a second authority plane
- do not let spectacle redefine mechanics truth
- do not replace authored poles with pure proc-gen drift
- do not make the web theater the only readable consumer
- do not let the effect lane outrank support/contact/balance truth
- do not let camera-speed escalation become a fake motion substitute

## Immediate Interpretation

For the current hero sequence, the practical read is:

- `The Cage` remains the named showcase resource
- the next implementation target is the fluid sequencer between poles
- weather/field systems become the first elemental expression lane
- the eventual stream hero is a JCVD split-set with DBZ finisher energy riding honest support truth
