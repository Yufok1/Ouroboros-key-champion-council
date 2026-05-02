# Atrai Organism-Mainframe Primitive Grammar - 2026-04-29

## Purpose

Define how Atrai primitives become the literal organism imagery inside the organism-mainframe display.

The primitive is not a label on top of the creature. The primitive is the creature's body part, energy path, constraint, and role.

This document bridges:

- organism/card identity
- AI-visible primitive packages
- canyon-span / rotation-snake mechanical primitives
- Source HOLD open-surgery doctrine
- civic animal depiction for non-robotic recognition

## Core Rule

Every visible organism part must correspond to one source-bound primitive package.

No cosmetic-only part is allowed to imply mechanics, authority, safety, or deployment status.

If a visible part has no package, it is decoration and must be marked as decoration. If it carries meaning, it needs a package row.

## Body Grammar

| Visual body part | Civic animal depiction | Primitive role | Mechanical/system meaning | Required fit checks |
|---|---|---|---|---|
| serpentine coil | serpent / eel / dragon spine | `phase_spine` / `rotation_snake` | main phase carrier, routing spine, peristaltic transport path | named anchors, phase law, charge/catch path, loss budget |
| tensile line | spider silk / tendon whisker | `tension_member` | tendon, cable, load path, sensor carrier | two anchors, tension limit, slack/preload, failure mode |
| cubic paneling | turtle shell / armadillo plates / scale field | `panel_leaf` / `transfer_floor` / `service_cell` | modular shell, wave panel, occupancy cell, repairable surface | edge grid, hinge/lock, clearance envelope, load limit |
| sphere / core | rolling beetle / seed core / pearl | `mass_node` / `charge_packet` | moving load, stored spin, transferable packet | mass, inertia, route state, catch state |
| cage / bay | nest / den / anemone cradle | `swap_bay` / `maintenance_dock` | docking organ, module receiver, quarantine or service bay | capacity, latch state, ingress/egress, release condition |
| charge organ | hive comb / warm organ | `charge_bank` | stored energy or readiness state | source, recharge path, sink, loss accounting |
| brake / damper limb | reflex tail / settling fin | `brake` / `damper` / `catch_path` | reflex, arrest, settling, safe capture | heat/load limit, catch window, recovery path |
| sequencer node | pulse ganglion | `micro_sequencer` | local timing ganglion, trigger router | target, timing, cannot be prime mover |
| sensor eye / whisker | eye / whisker / antenna | `load_probe` / `angle_probe` / `pan_probe` | observation and inspection | target id, sample rate, provenance receipt |
| utility vein | vein / root network / gill path | `utility_bus` | service flow between sources and sinks | source ids, sink ids, duty cycle |
| acoustic no-entry zone | owl ring / quiet reef / listening membrane | `acoustic_no_entry_zone` / `voice_gate` | warning, privacy, attention shaping, and ingress boundary | source speaker/surface, receiver class, safe intensity, duration, fallback cue |
| public laughter pulse | chorus / call-response / banger pulse | `public_laughter_sonar` / `attention_beacon` | public humor sensing for mood, friction, timing, and readiness | public source, receiver class, context, intensity, consent boundary, aggregate-only notes |
| clean/dirty bands | skin boundary / membrane | `clean_band` / `dirty_band` | service circulation and contamination boundary | occupancy class, transfer rule, exclusion condition |
| source hold mark | guardian / keeper / civic hand | `source_hold` | human authorization boundary | human owner, condition, receipt, rollback path |

## Fit Ports

Pieces fit only through compatible ports.

Required port classes:

- `mechanical_load`
- `rotation_phase`
- `tension`
- `panel_edge`
- `energy`
- `fluid`
- `data`
- `provenance`
- `authority`
- `occupancy`
- `service_access`

Every primitive package must list `ports.in` and `ports.out`.

Example:

```json
{
  "id": "rotation_snake.left_phase_coil",
  "visual": {
    "body_part": "serpentine_coil",
    "organism_role": "spine"
  },
  "ports": {
    "in": [
      {"class": "mechanical_load", "unit": "N"},
      {"class": "energy", "unit": "J"}
    ],
    "out": [
      {"class": "rotation_phase", "unit": "deg"},
      {"class": "provenance", "unit": "receipt"}
    ]
  }
}
```

## No-Chance Fit Constraints

The display may be expressive, but fit is strict.

A connection is valid only if:

1. Port classes are compatible.
2. Units match or a named converter exists.
3. Direction is explicit.
4. Source and sink are named.
5. Moving parts name charge, catch, and loss budget.
6. Tension members name both anchors.
7. Panel members name hinge/lock/edge geometry.
8. Occupancy paths name safe/unsafe zones.
9. AI-visible surfaces name source status.
10. Any real-world action routes through Source HOLD.

If any check fails, the UI may show adjacency, curiosity, or speculation, but not fit.

## Organism Identity

The organism card is the readable identity of a primitive package or primitive cluster.

Each organism should expose:

- `name`
- `primitive_id`
- `family`
- `body_plan`
- `source_docs`
- `state`
- `ports`
- `dependencies`
- `risks`
- `HOLD_condition`
- `provenance_receipts`

The creature-like visual form is valid when it helps humans recognize system role quickly:

- spine creatures = routing / phase / continuity
- tendon creatures = tension / force / restraint
- panel creatures = shelter / shell / transfer / modularity
- sensor creatures = observation / telemetry
- acoustic creatures = no-entry, warning, privacy, attention, and sensory safety
- laughter creatures = public mood sonar, not private judgment
- cage creatures = docking / quarantine / recovery
- utility creatures = service flow
- governance creatures = consent / authority / HOLD

Default organism-mainframe depiction should prefer the creature form. Mechanical mode should remain available for audit, ports, units, and fit checks.

Animal form is not evidence. It is an interface lens over evidence.

Acoustic form is not background ambience. It is a boundary primitive. If an organism-mainframe creature emits, blocks, softens, redirects, or gates sound, the card must expose acoustic source, receiver class, safe band, duration, fallback cue, and whether Source HOLD is required.

## Transformer-Like Assembly, But Not Fantasy

Assemblies may look like transforming robots, but the grammar is not "anything can become anything."

An assembly can transform only when the package graph proves:

- which parts change state
- which joints permit motion
- which loads move
- which energy is spent or captured
- which catches prevent runaway
- which Source HOLD condition applies

The serpentine coil is the main component because it carries phase, route, and continuity. Cubic paneling gives repairable modular body. Tensile lines give force closure and sensing. The three together form the first stable Atrai visual grammar:

`coil + tensile line + cubic panel = phase body + force closure + repairable shell`

## Minimum Primitive Creature

A valid primitive creature needs at least:

- one body role
- one source document
- one primitive id
- one port
- one state
- one provenance path
- one Source HOLD statement

For mechanical creatures, add:

- mass/load or tension limit
- energy source or explicit no-energy role
- catch/fault behavior

For civic/ark creatures, add:

- human/community authority owner
- consent condition
- deployment boundary

## Failure Labels

Use these display labels instead of pretending uncertain pieces fit:

- `unanchored`: missing anchor
- `unsourced`: missing source document/artifact
- `unbounded`: missing limit/envelope
- `unreceipted`: missing provenance path
- `uncaught`: moving piece lacks catch path
- `unsunk`: utility claim lacks sink
- `ungated`: needs Source HOLD
- `cosmetic`: visible but non-authoritative decoration

## Next Build Target

Create `ATRAI_PRIMITIVE_REGISTRY_2026-04-29.md` with organism-mainframe rows using this grammar.

First rows should include:

- `rotation_snake.phase_spine`
- `rotation_snake.left_tension_line`
- `rotation_snake.right_tension_line`
- `rotation_snake.taper_panel_chain`
- `rotation_snake.charge_packet_sphere`
- `rotation_snake.catch_cage`
- `rotation_snake.charge_bank`
- `rotation_snake.utility_bus`
- `source_hold.human_authority_gate`
