# Shutter / Adrenaline Name Rehabilitation 2026-04-29

Repo: `D:\End-Game\champion_councl`
Status: active doctrine correction

## Why This Exists

The previous prompt and several docs marked continuity-side `adrenaline` and abstract `shutter` as deprecated.

The operator clarified that this deprecation came from frustration, not final intent.

Corrective action:

- keep the names
- remove vague authority from them
- bind them to visible surfaces, receipts, and Source HOLD

## Rehabilitated Definitions

`adrenaline`:

- salience pressure
- urgency
- novelty
- risk
- readiness-to-inspect
- the rising pressure that says "look here next"

`shutter`:

- bounded capture gate
- attention aperture
- freeze-frame over a specific surface
- receipt emitter
- never a whole-runtime freeze

`shuttering_adrenaline`:

- pressure reaches threshold
- shutter closes over the relevant surface
- capture receipt is emitted
- next model invocation receives an activation packet

## Implementation Translation

```text
adrenaline -> salience score and reasons
shutter -> capture refs and receipts
shuttering_adrenaline -> event_activation_packet
```

The model should not run forever.

The surrounding substrate may observe continuously and prepare packets.

## Required Boundaries

This system may:

- observe
- score pressure
- capture evidence
- route attention
- ask for HOLD
- recommend next reads

It may not:

- mutate source silently
- deploy
- publish
- authenticate
- spend
- promote proposal into truth
- bypass Source HOLD

## Relation To Existing Surfaces

The rehabilitated names sit over existing machinery:

- `continuity_cue`
- `resume_focus`
- `surface_prime`
- `reset_boundary`
- `output_state`
- `equilibrium`
- `watch_board`
- `trajectory_correlator`
- `tinkerbell_attention`
- `pan_probe`
- `live_render_shutter`
- `structured_snapshot_shutter`
- `contact_body_shutter`
- `web_theater_shutter`
- HOLD

They do not replace those surfaces.

They name the pressure-and-capture cycle that coordinates them.

## Operating Rule

Do not say "`adrenaline` is deprecated" as the active answer.

Say:

```text
Ungated adrenaline mythology is deprecated.
Bounded adrenaline as salience pressure is active.
Ungated shutter mythology is deprecated.
Bounded shutter as capture aperture is active.
```
