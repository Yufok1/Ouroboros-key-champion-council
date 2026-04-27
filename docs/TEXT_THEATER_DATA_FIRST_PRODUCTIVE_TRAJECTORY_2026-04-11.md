# Text Theater Data-First Productive Trajectory 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- return the project to an immediately productive trajectory
- keep the 7-form render ambition while aligning it to the corrected data-first goal
- define what should be built next versus what should stay deferred

Related docs:

- [TEXT_THEATER_SEVEN_FORM_DATA_FIRST_SYSTEM_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SEVEN_FORM_DATA_FIRST_SYSTEM_2026-04-11.md)
- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md](/F:/End-Game/champion_councl/docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md)

## Bottom Line

The mainline is no longer "invent a new letter-body depiction system."

The mainline is:

1. make the blackboard rank and present the right variables
2. make those values easy to read under camera and session changes
3. let symbolic/ascii geometry support spatial interpretation without corrupting the semantic data lane

That is the shortest path back to usefulness.

## Current Starting Point

Already live or partially live:

- `shared_state.blackboard`
- `shared_state.text_theater_profiles`
- `shared_state.text_theater_control`
- camera-relative scene and blackboard context in live shared state
- programmable operator surfaces in text theater

Not yet live:

- blackboard-first value hierarchy in the text renderer
- non-alphanumeric symbolic geometry vocabulary/registry
- camera-driven symbolic field composition
- spatial/web consumers of the corrected split

## Phase 1: Freeze The Readable Lane

Goal:

- protect the readable operator and blackboard surfaces from future drift

Build:

- keep alphanumeric values as solid text
- keep menu/status/blackboard rows readable at stress-time sizes
- keep the default substrate low-cost and visually controlled
- preserve `legacy` only as a fallback pole, not the doctrine

Success:

- operator can read the key values immediately
- agent can parse the values without ambiguity
- no lag-heavy decorative substrate returns by accident

## Phase 2: Blackboard Value Priority

Goal:

- make the most important state dominate the surface

Build:

- explicit lead-row rendering for top blackboard values
- profile-aware weighting of row families
- visual distinction for:
  - measurement
  - derived
  - interpretation
  - corroboration
  - invariant/failure
- stronger presentation for current risk, margin, route, controller, contact, and load rows

Success:

- the blackboard reads like a robotics instrument, not a flat dump
- the key variables win the screen before any decorative detail

## Phase 3: Symbolic Orientation Lane

Goal:

- give the system a depictive lane that does not sacrifice the semantic lane

Build:

- a controlled non-alphanumeric symbol registry:
  - lines
  - corners
  - arrows
  - brackets
  - box-drawing
  - dots/braille/blocks
- row-family policies for when symbolic support is allowed
- leader lines, direction marks, and contour hints around blackboard slates

Success:

- the surface gains spatial/angle cues
- values remain readable and semantically primary

## Phase 4: Seven-Form Consolidation

Goal:

- make the 7-form system real as one coherent render policy

Build:

1. reference data
2. fused operator
3. priority value
4. symbolic orientation
5. granular fill
6. symbolic field
7. spatial consumer contract

Success:

- every future render decision can be placed into one of those forms
- no future session needs to reinvent the doctrine

## Phase 5: Spatial Consumers Later

Goal:

- reuse the split in web/cube/state-space consumers only after the blackboard is already useful

Build later:

- diagnostic cubes
- CSS2D mini-slates
- symbolic field overlays
- spatial blackboard consumers

Do not build first:

- whole-model text skins
- alphanumeric objectification
- artistic glyph fields without a blackboard need

## Immediate Implementation Queue

1. Add a blackboard/value-emphasis render pass in `scripts/text_theater.py` so lead rows are visibly stronger than secondary rows.
2. Thread profile family weighting into the text-theater blackboard consumer so `mechanics_telemetry` and `route_telestrator` produce visibly different row admission/emphasis.
3. Formalize a non-alphanumeric symbol vocabulary registry in docs and source, separate from alphanumeric text.
4. Add symbolic leader-line and indicator primitives around blackboard rows before any spatial consumer work.

## Definition Of Productive Mode

The project is back in productive mode when:

- the blackboard tells the operator what matters first
- the data lane stays legible at all times
- symbolic geometry improves orientation without obscuring values
- future sessions stop reopening the abandoned letter-body path
