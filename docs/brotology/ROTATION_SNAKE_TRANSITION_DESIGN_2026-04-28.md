# Rotation Snake Transition Design - 2026-04-28

## Purpose

Move the canyon-span / Atrai / Falkor mechanical idea from loose imagination into an in-house transition surface that the Environment scene, blackboard, FelixBag docs lane, Dreamer, and Council can reason about.

This document treats the "rotation snake" as a facility primitive:

- a paired serpentine channel
- built from pivoting tapered panels in V0, or tensioned cable runs in V1
- moving spheres down for charge capture or up through a powered wave
- routed through switching panels into cages, buffers, returns, or utility sinks

This is not a free-energy claim. The facility stores, routes, transforms, and delivers energy. External input is still required.

## Evidence Classification

Confirmed:

- `env_help(topic='docs_planning_refresh')` says the in-house doc update lane is `docs_packet -> blackboard consult -> snapshot -> bag_search_docs -> checkpoint -> file_write/edit -> bag_read_doc`.
- `env_help(topic='docs_packet')` says `docs_packet` is the planning/material face over repo docs and FelixBag docs, not a replacement for live theater or blackboard evidence.
- `env_help(topic='workspace_packet')` says `file_*` tools operate on FelixBag workspace paths unless a separate host bridge exists.
- The live Environment scene is mounted with 14 objects, focused on `tile::central_support_pad`.
- The local docs already name the core primitive: paired serpentine runs, sphere population, switching panels, destination cages, external energy source, and hybrid fixed-point control.
- The canyon-span registry requires every charged motion to name a `charge_bank` and `catch_path`, and every utility claim to name a real sink.
- Public robotics literature supports the generic mechanical families: wave locomotion for motion/object transport, continuous peristaltic robot waves, and cable-driven spherical tensegrity control.

Partly confirmed:

- Dreamer can be useful as a proposer/scorer for phase schedules, but the local `/api/dreamer/state` call timed out during this pass, so Dreamer is not live authority for this document.
- `get_help` / `bag_search_docs` are the correct capsule-side surfaces, but the local gateway returned 503 for those calls in this pass.

Unknown:

- Exact taper law between panel angle, channel gap, normal force, and sphere spin.
- Sphere size/material distribution.
- Whether V1 should use physical cables, hinged tapered panels, or a hybrid cable-backed panel strip.
- Real coefficient-of-friction envelope and loss budget.
- Whether the first demonstrator should be dry mechanical, water-assisted, thermal-assisted, or purely simulated.

Active seam:

- `facility_bind` failed with `MCP session not available`, so the live scene binding is specified below but not yet applied.

## Local Source Receipts

- `docs/brotology/ATRAI_KINETIC_ARCHITECTURE_SESSION_SYNTHESIS_2026-04-27.md`
- `docs/brotology/CANYON_SPAN_PRIMITIVE_REGISTRY_SPEC_2026-04-23.md`
- `docs/brotology/CARRIER_FORTRESS_CANYON_SPAN_PLANNING_DOSSIER_2026-04-23.md`

## External Mechanical Receipts

- Yoshida and Nagaoka, "A mobile robot driven by uniaxial wave locomotion mechanism", ROBOMECH Journal, 2023. The paper shows a single-actuator helical mechanism producing surface waves and notes that wave mechanisms can generate relative motion and support object transport uses. https://link.springer.com/article/10.1186/s40648-023-00254-y
- Boxerbaum et al., "Continuous wave peristaltic motion in a robot", IJRR, 2012. The paper frames continuous peristaltic waves as effective locomotion in constrained spaces and discusses braided-mesh wave construction. https://journals.sagepub.com/doi/10.1177/0278364911432486
- Kim, Agogino, and Agogino, "Rolling Locomotion of Cable-Driven Soft Spherical Tensegrity Robots", Soft Robotics, 2020. The paper supports the idea that controlled cable tension can deform a spherical structure to create rolling locomotion strategies. https://journals.sagepub.com/doi/10.1089/soro.2019.0056

## Primitive

`rotation_snake` is a paired-serpentine route. It is not an animal form; it is a phase-controlled channel.

The sphere is the moving load. The tapered panels are the controllable wave. The serpentine tension is the phase carrier.

The V0 channel is two opposed tapered panel chains:

- each panel has `angle`, `gap`, `phase`, `normal_force`, `friction_band`, and `load_limit`
- the left and right chains are phase-coupled but can be offset to steer spin axis
- a traveling wave pinches behind the sphere and opens ahead of it
- reversing the phase reverses preferred transport direction

The V1 channel can replace or back the panel chain with paired tension cables:

- cables produce local taper geometry through variable tension
- cables can act as structure, actuator, sensor, and acoustic carrier
- the cable version likely reduces bearings but increases control and simulation complexity

## Two Operating Modes

### Descend And Charge

Sphere enters from an upper reservoir and descends under gravity.

The panel/cable wave does not "make" energy. It shapes the descent so the sphere rolls, spins, brakes, and transfers part of gravitational potential into rotational charge or into a mechanical/electrical charge bank.

Required fields:

- `sphere_id`
- `height_drop`
- `entry_velocity`
- `spin_axis`
- `rotational_energy`
- `charge_bank`
- `catch_path`
- `loss_budget`

Failure if:

- energy increases without a named source
- no catch/brake path exists
- load exceeds panel, cable, or cage limit

### Ascend And Pump

Sphere moves upward only when external or stored energy is spent.

The controller creates a moving pocket:

- close panels behind the sphere
- open panels ahead of the sphere
- bias taper to preserve or change spin
- walk the sphere uphill one segment at a time

Required fields:

- `input_energy`
- `actuator_family`
- `phase_velocity`
- `anti_rollback_latch`
- `recovery_brake`
- `utility_or_return_goal`

Failure if:

- upward motion has no energy debit
- anti-rollback is absent
- the controller cannot prove the next catch state

## Weird But Plausible Behaviors

Phase inversion:

- left chain leads right chain, or right chain leads left chain
- this biases spin axis and can route the sphere into different terminal cages

Taper gradient steering:

- narrow-to-wide taper can accelerate or release
- wide-to-narrow taper can brake, grip, or transfer spin

Bidirectional channel:

- same hardware can descend-and-charge or ascend-and-pump
- direction is a phase policy, not a separate machine

Acoustic telemetry:

- tensioned members will sound under load
- the "facility as instrument" layer is mechanically literal, but should be treated as telemetry first and aesthetic second

Sphere/cage continuity:

- a moving sphere and a docked spinning sphere can be the same object in different state
- docking arrests translation while preserving or reorienting rotation

## Council And Dreamer Roles

Council role:

- enforce invariant checks
- keep the scene/docs/FelixBag/blackboard lanes aligned
- reject claims that lack charge, catch, sink, or loss accounting
- decide whether a proposed phase schedule is safe enough to simulate

Dreamer role:

- propose phase schedules over `gap`, `angle`, `phase_offset`, `wave_velocity`, `friction_band`, and `sphere_state`
- score candidate schedules against charge capture, lift cost, catch reliability, and oscillation risk
- never outrank measured runtime state or Council invariants

Dreamer is a proposer/scorer here, not a proof engine.

## Scene Facility Map

Pending facility id:

`rotation_snake_canyon_span_v1`

Intended live bindings:

| Scene object | Role | Primitive |
|---|---|---|
| `tile::central_support_pad` | blackboard console | `observation_packet` |
| `tile::west_support_pad` | west rim anchor | `rim_anchor` |
| `tile::east_support_pad` | east rim anchor | `rim_anchor` |
| `portal::central_arch` | spine pivot / phase origin | `spine_pivot` |
| `panel::route_test_wall_a` | left taper panel wave | `panel_leaf`, `descend_and_charge` |
| `panel::route_test_wall_b` | right taper panel wave | `panel_leaf`, `ascend_and_pump` |
| `panel::west_blocker` | left catch brake | `brake` |
| `panel::east_blocker` | right catch brake | `brake` |
| `tile::north_transition` | return floor | `transfer_floor` |
| `marker::north_landmark` | upper reservoir | `charge_bank` |
| `marker::route_test_goal` | switching panel | `micro_sequencer` |
| `marker::east_landmark` | utility sink | `utility_bus` |

Retry payload:

```json
{
  "facility_id": "rotation_snake_canyon_span_v1",
  "bindings": [
    {"kind": "tile", "id": "central_support_pad", "role": "blackboard_console", "primitive": "observation_packet"},
    {"kind": "tile", "id": "west_support_pad", "role": "west_rim_anchor", "primitive": "rim_anchor"},
    {"kind": "tile", "id": "east_support_pad", "role": "east_rim_anchor", "primitive": "rim_anchor"},
    {"kind": "portal", "id": "central_arch", "role": "spine_pivot", "primitive": "spine_pivot"},
    {"kind": "panel", "id": "route_test_wall_a", "role": "left_taper_panel_wave", "primitive": "panel_leaf", "mode": "descend_and_charge"},
    {"kind": "panel", "id": "route_test_wall_b", "role": "right_taper_panel_wave", "primitive": "panel_leaf", "mode": "ascend_and_pump"},
    {"kind": "panel", "id": "west_blocker", "role": "left_catch_brake", "primitive": "brake"},
    {"kind": "panel", "id": "east_blocker", "role": "right_catch_brake", "primitive": "brake"},
    {"kind": "tile", "id": "north_transition", "role": "return_floor", "primitive": "transfer_floor"},
    {"kind": "marker", "id": "north_landmark", "role": "upper_reservoir", "primitive": "charge_bank"},
    {"kind": "marker", "id": "route_test_goal", "role": "switching_panel", "primitive": "micro_sequencer"},
    {"kind": "marker", "id": "east_landmark", "role": "utility_sink", "primitive": "utility_bus"}
  ]
}
```

## Blackboard Query Contract

Every blackboard read should answer these before it claims operational progress:

- Which mode is active: `descend_and_charge`, `ascend_and_pump`, `dock`, `buffer`, or `fault`?
- Where is the sphere: reservoir, segment, switch, cage, return, or quarantine?
- What is the current phase: `charge`, `hold`, `release`, `crest`, `catch`, `return`, or `recharge`?
- What is the named energy source?
- What is the named `charge_bank`?
- What is the named `catch_path`?
- What is the named utility sink?
- What load, vibration, and oscillation bands are active?
- Did the latest step conserve energy within the declared loss budget?

## V0 Simulation Contract

Minimum state:

```json
{
  "tick": 0,
  "mode": "descend_and_charge",
  "phase": "charge",
  "sphere": {
    "id": "sphere_001",
    "s": 0.0,
    "height": 0.0,
    "velocity": 0.0,
    "omega": 0.0,
    "spin_axis": [0, 1, 0],
    "translational_energy": 0.0,
    "rotational_energy": 0.0
  },
  "segment": {
    "id": "segment_000",
    "left_angle_deg": 0.0,
    "right_angle_deg": 0.0,
    "gap": 1.0,
    "phase_offset_deg": 0.0,
    "wave_velocity": 0.0,
    "friction_band": "unknown",
    "load_band": "quiet"
  },
  "accounting": {
    "input_energy": 0.0,
    "recovered_energy": 0.0,
    "loss_energy": 0.0,
    "charge_bank": "upper_reservoir_or_cage",
    "catch_path": "left_catch_brake/right_catch_brake",
    "utility_sink": "utility_bus"
  }
}
```

Acceptance gates:

- One virtual sphere descends, gains bounded spin, and loses energy through declared losses.
- One virtual sphere ascends only with declared input energy.
- One switching panel routes to `dock`, `recirculate`, or `buffer`.
- One catch/brake path arrests a faulted sphere.
- One blackboard packet exposes mode, phase, sphere state, energy accounting, and gate status.
- No route claims useful work without a named sink.

## Build Order

1. Keep this design doc as the local source-of-truth until FelixBag writes recover.
2. Retry `facility_bind` with the payload above.
3. Add a lightweight simulation packet, not a full physics engine: phase schedule, sphere state, loss accounting.
4. Wire the packet into blackboard rows first.
5. Use Dreamer only after the packet is observable, so proposals can be scored against real state.
6. Mirror the doc into FelixBag after `bag_search_docs` and `file_checkpoint` recover.

## Hard Guardrails

- No perpetual-motion framing.
- No utility claim without `utility_sink`.
- No charged motion without `charge_bank`.
- No sphere route without `catch_path`.
- No upward transport without energy debit.
- No scene deletion as a substitute for facility construction.
- No Dreamer claim without live state corroboration.
