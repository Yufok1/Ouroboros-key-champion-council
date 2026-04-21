# Sunken Treasure Queue 2026-04-19

Purpose: hold the obvious next systems that are already visible through current surfaces, but not yet fully operationalized, so they can be implemented as packetized units instead of as piecemeal improvisations.

This is not a general backlog.

It is only for findings that meet all of these conditions:

- the seam is already visible through owned runtime surfaces
- the idea can be expressed as a bounded packet or contract
- the result composes with existing truth surfaces instead of inventing a second authority plane
- the next slice is concrete enough to build or verify

## Current substrate already owned

These are already real and should be treated as the substrate, not as future fantasy:

- `output_state` in [static/main.js](/D:/End-Game/champion_councl/static/main.js:34779)
- `tinkerbell_attention` in [static/main.js](/D:/End-Game/champion_councl/static/main.js:34411)
- Facility Mirror in [static/main.js](/D:/End-Game/champion_councl/static/main.js:22619)
- camera/screen projection collection in [static/main.js](/D:/End-Game/champion_councl/static/main.js:42887)
- observer composite/supercam projection outputs in [static/main.js](/D:/End-Game/champion_councl/static/main.js:43343)
- layout / HUD / label diagnostics in [static/main.js](/D:/End-Game/champion_councl/static/main.js:40747)
- Dreamer oracle intake in [server.py](/D:/End-Game/champion_councl/server.py:12128)
- env-report normalization in [server.py](/D:/End-Game/champion_councl/server.py:4720)
- text-theater output-state formatting in [scripts/text_theater.py](/D:/End-Game/champion_councl/scripts/text_theater.py:1218)
- load-field disable contract in [static/main.js](/D:/End-Game/champion_councl/static/main.js:4661) and [static/main.js](/D:/End-Game/champion_councl/static/main.js:34955)

## Intake rule

Add a new treasure here only if it can be written in this shape:

- `packet_name`
- `what_it_does`
- `owned_surfaces_used`
- `why_it_is_now_obvious`
- `smallest_honest_next_slice`
- `what_it_must_not_do`

If the seam cannot be expressed that way yet, it is not ready for this queue.

## Packet template

Use this packet skeleton when promoting an item into implementation:

```text
packet_name:
status:
carrier:
inputs:
outputs:
shared_truth:
operator_affordance:
agent_affordance:
next_read:
hold_candidate:
failure_mode:
must_not:
```

## Treasure 1. Shared View Packet

- `packet_name`: `view_packet`
- `status`: surfaced
- `what_it_does`: turns the current camera view into a shared operator/agent communication unit that can drive the next honest query
- `owned_surfaces_used`: camera pose, screen projections, Facility Mirror, `output_state`, `text_theater_snapshot`, `supercam`
- `why_it_is_now_obvious`: the system already carries the current data pool, but it does not yet emit one explicit packet that closes the loop from view to query
- `smallest_honest_next_slice`: derive `view_packet` from current camera pose plus `output_state` and expose it in snapshot + consult
- `what_it_must_not_do`: create a private assistant-only orientation state

Suggested fields:

- `camera_pose`
- `camera_delta`
- `focus_subject`
- `settled_targets`
- `active_pointer`
- `measurement_focus`
- `next_query`
- `confidence`
- `parity_gap`

## Treasure 2. Procedural HUD Settlement Engine

- `packet_name`: `hud_solution_packet`
- `status`: surfaced
- `what_it_does`: composes a camera-relative HUD that re-settles each frame from prior transient state rather than reusing fixed layout presets
- `owned_surfaces_used`: `equilibrium`, `watch_board`, `tinkerbell_attention`, `pan_probe`, camera delta, label/clipping diagnostics, screen projections
- `why_it_is_now_obvious`: the repo already tracks projection, clipping, offscreen state, and mirror content, but still renders a mostly fixed mirrored panel
- `smallest_honest_next_slice`: build candidate labels from `output_state` and solve a small placement set against the current camera and prior frame
- `what_it_must_not_do`: render explicit connection rails between every prior and next view as the primary continuity mechanism

Key rule:

- the layout should be transient and relative
- no two orientations should be identical
- continuity should come from settlement, not from static overlay positions

## Treasure 3. Camera-Mediated Intent Latch

- `packet_name`: `intent_packet`
- `status`: surfaced
- `what_it_does`: lets the operator point with camera/focus and add a tiny gloss so vague intent becomes a measurable next-read request
- `owned_surfaces_used`: camera pose, focus, `tinkerbell_attention`, `pan_probe`, blackboard consult, HOLD
- `why_it_is_now_obvious`: the operator is already using view orientation as a communication channel; the missing seam is the tiny grammar after the point
- `smallest_honest_next_slice`: add one lightweight operator-intent family such as `why`, `fix`, `compare`, `follow`, `hold`, `weird`
- `what_it_must_not_do`: require full natural-language explanation before the system can resolve the seam

Suggested fields:

- `operator_mode`
- `fuzziness`
- `urgency`
- `camera_settled`
- `focus_guess`
- `hold_candidate`
- `next_query`

## Treasure 4. Bell / Tink Split

- `packet_name`: `bell_packet` and `tink_packet`
- `status`: doctrinally surfaced
- `what_it_does`: splits salience/ringing from measurement/probe planning so one facility says what matters and the other says how to inspect it
- `owned_surfaces_used`: `equilibrium`, `watch_board`, `tinkerbell_attention`, projection/probe surfaces, `pan_probe`
- `why_it_is_now_obvious`: overloading one facility with both urgency and probe logic makes the design muddy
- `smallest_honest_next_slice`: alias the current pointer layer as the Bell-side output and define a separate probe-planning packet for Tink
- `what_it_must_not_do`: become a second controller or a second truth plane

Bell should answer:

- `why_now`
- `urgency`
- `what seam`

Tink should answer:

- `what angle`
- `what capture`
- `what measure`

## Treasure 5. HOLD Row Family And Shutter Packet

- `packet_name`: `hold_latch_packet` and `shutter_packet`
- `status`: partially surfaced
- `what_it_does`: turns HOLD into a visible carried family and gives the system a compact segment-capture packet at intervention boundaries
- `owned_surfaces_used`: HOLD tool/UI seam, `output_state`, blackboard, snapshot, continuity packet doctrine
- `why_it_is_now_obvious`: HOLD is real, snapshot surfaces are real, but the generic segment packet is still absent
- `smallest_honest_next_slice`: promote HOLD to a visible row family, then add `latched_hold_id`, `resume_mode`, and surface refs in a compact shutter packet
- `what_it_must_not_do`: freeze the whole runtime or invent a hidden second memory plane

## Treasure 6. Facility Mirror To Spatial Calculator Skin

- `packet_name`: `mirror_projection_packet`
- `status`: surfaced
- `what_it_does`: projects measured state back into the space around the model so the web theater becomes a real calculator surface rather than only a mirrored panel
- `owned_surfaces_used`: Facility Mirror, text-theater bundle, screen/world projections, label diagnostics, `supercam`
- `why_it_is_now_obvious`: the mirror already carries the right facts, and the world/screen projection machinery already exists
- `smallest_honest_next_slice`: promote a small set of settled targets into world-anchored or screen-anchored labels around the current subject
- `what_it_must_not_do`: replace text theater or mirror with decorative 3D noise

## Treasure 7. Weather / Field Glyph Consumer

- `packet_name`: `field_glyph_packet`
- `status`: surfaced
- `what_it_does`: expresses weather/support/gravity-style field state through a web-theater glyph consumer instead of only through text rows
- `owned_surfaces_used`: text-theater weather bundle, `field_disposition`, web overlay defaults, existing overlay/CSS2D surfaces
- `why_it_is_now_obvious`: the weather/web overlay lane already exists doctrinally and technically, but its browser-side field consumer is still incomplete
- `smallest_honest_next_slice`: render one truthful field layer from `field_disposition` and weather state, not fake ambient effects
- `what_it_must_not_do`: show placeholder rain blobs or ambient effects that do not match owned weather truth

## Treasure 8. Technolit Sequencing Bridge

- `packet_name`: `technolit_measure_packet`
- `status`: partially surfaced
- `what_it_does`: operationalizes Technolit as a measured sequencing bridge inside `equilibrium`, not just a decorative coin readout
- `owned_surfaces_used`: `equilibrium.technolit_measure`, watch board, text-theater output, reactor seed
- `why_it_is_now_obvious`: the measurement is already live, but its downstream use in query and intervention sequencing is still shallow
- `smallest_honest_next_slice`: let the Technolit band influence intercept/read ordering only through visible `watch_board` and `next_reads`
- `what_it_must_not_do`: silently dominate unrelated embodiment or theater logic

## Treasure 9. Reactive Substrate Response

- `packet_name`: `substrate_response_packet`
- `status`: surfaced
- `what_it_does`: lets Coquina/Pan support-field logic answer support or route problems through reactive generation, repair, brace, or compensation
- `owned_surfaces_used`: `pan_probe`, support-field doctrine, Coquina substrate/procgen doctrine, HOLD/shutter seams
- `why_it_is_now_obvious`: the system is already measuring support truth and already has a reactive procgen direction; the missing seam is the bounded response packet
- `smallest_honest_next_slice`: define one support response packet that can propose a brace/pad/wedge/catch surface without changing authority order
- `what_it_must_not_do`: mutate the environment directly without passing through visible route/support truth

## Sequencing rule

Do not attack every treasure at once.

The clean sequence right now is:

1. `view_packet`
2. `intent_packet`
3. `hud_solution_packet`
4. `mirror_projection_packet`
5. `hold_latch_packet`
6. `shutter_packet`

Reason:

- that closes the operator/agent orientation loop first
- then it gives HOLD and shutter a better carrier
- then later field glyphs and substrate responses can dock into a working parity surface

## Promotion rule

When one treasure becomes concrete enough to build, spin it out into its own spec/checkpoint doc and leave only this behind:

- packet name
- carrier
- status
- link to the dedicated doc

That keeps this file a surfacing queue, not another giant architecture blob.
