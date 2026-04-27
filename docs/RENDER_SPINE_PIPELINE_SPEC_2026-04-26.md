# Render Spine Pipeline Spec

Date: 2026-04-26
Status: draft from live continuity + live theater corroboration

## Intent

The authority plane for the web theater and text theater is not either theater.

The authority plane is the sequencing pipeline that:

1. receives activity and route pressure
2. names the current front
3. carries the active pointer
4. merges theater constitutions
5. decides projection
6. captures corroboration
7. feeds equilibrium back into the next frame

The theaters are constitutions.
The pipeline is sovereignty.

## Continuity Read

Continuity was run before this spec.

Live read says:

- the archive restore is useful, but it diverges from the current live objective and subject
- the live query thread is authoritative
- `equilibrium` is `aligned`
- `freshness.mirror_lag` is `false`
- `watch_board.current_front` is live and usable
- `tinkerbell_attention.active_pointer` is live and usable

Current live seam:

- objective: `selection_orientation`
- subject: `bone:character_runtime::mounted_primary:head`
- pivot: `operative_memory_alignment`
- current front focus: `character_runtime:mounted_primary`
- current pointer: `next_read -> env_read:text_theater_view`

This means the render spine should be drawn from live `output_state` and blackboard sequence, not from archive continuity alone.

## Current Concrete Surfaces

The existing system already has the pieces.

Ingress trace:

- server activity broadcast
- activity SSE stream
- browser activity trace derivation
- browser activity rehydration and sequencing

Carried orienting state:

- `shared_state.blackboard.working_set.query_thread`
- `shared_state.output_state`
- `shared_state.output_state.trajectory_correlator`
- `shared_state.output_state.tinkerbell_attention`
- `shared_state.output_state.watch_board`
- `shared_state.output_state.freshness`

Corroboration shutters:

- `env_read(query='text_theater_view', view='render')`
- `env_read(query='text_theater_snapshot')`
- `env_read(query='text_theater_embodiment')`
- `capture_supercam -> env_read(query='supercam')`

Render truth and projection surfaces:

- web theater / habitat 3D
- text theater / consult-render-snapshot lanes

## The Needle In The Haystack

The operator should have one pressure handle that can be found blind:

`spine_id -> current_front -> active_pointer -> freshness -> capture_receipts`

That handle becomes the render-spine locator.

If the operator cannot answer these five questions in one place, the pipeline is still too diffuse:

1. What sequence am I in?
2. What is the current front?
3. What is the system pointing at right now?
4. Is the mirror fresh?
5. What captures confirm the current frame?

## Formal Pipeline

The render authority chain should be:

1. `activity_trace`
2. `render_spine_packet`
3. `text_constitution`
4. `web_constitution`
5. `equilibrium_render_packet`
6. `projection_adapters`
7. `capture_shutters`
8. `corroboration_feedback`

## 1. activity_trace

This is the ingress bus.

It should carry:

- `trace_id`
- `trace_seq`
- `source`
- `tool`
- `route_kind`
- `objective_id`
- `subject_key`
- `focus_key`
- `command_sync_token`
- `timestamp_ms`

Rule:

- every downstream render decision must be attributable to an activity trace or a carried sequence state

## 2. render_spine_packet

This is the constant pressure point.

It should carry:

- `spine_id`
- `sequence_id`
- `segment_id`
- `frame_id`
- `trace_id`
- `trace_seq`
- `objective_id`
- `objective_label`
- `subject_key`
- `pivot_id`
- `focus_key`
- `current_front`
- `active_pointer`
- `equilibrium_band`
- `drift_band`
- `freshness`
- `command_sync_token`
- `capture_receipts`

Rules:

- exactly one `spine_id` per authoritative frame
- exactly one `frame_id` per merged projection decision
- `current_front` comes from `watch_board.current_front`
- `active_pointer` comes from `tinkerbell_attention.active_pointer`
- freshness is carried, not inferred separately by each theater

## 3. text_constitution

Text theater owns:

- wording
- lexeme timing
- semantic emphasis
- arbitration order
- projection approval for text-bearing surfaces

Text theater does not own:

- hair geometry
- body silhouette
- crown topology
- freeform web-side text invention

## 4. web_constitution

Web theater owns:

- geometry
- silhouette
- motion
- material response
- field response
- camera-visible occupancy

Web theater does not own:

- upstream text arbitration
- semantic word formation
- independent hair-word generation
- separate hidden sequence truth

## 5. equilibrium_render_packet

This is the merge seam.

It decides, per frame:

- what is shared across both theaters
- what is text-only
- what is web-only
- what is held
- what is delayed
- what is projected now
- what requires corroboration before promotion

It should carry:

- `spine_id`
- `frame_id`
- `shared_fields`
- `text_projection`
- `web_projection`
- `hold_state`
- `projection_decision`
- `promotion_state`
- `corroboration_requirements`

Rules:

- the equilibrium packet is the only surface allowed to approve cross-theater projection
- no theater may silently promote its own local guess into shared truth

## 6. projection_adapters

After equilibrium decides, adapters translate the merged packet into theater-local instructions.

Text adapter:

- renders approved text timing and emphasis
- exposes approved projected text to web only when authorized

Web adapter:

- renders approved geometry and motion
- consumes approved projected text only as a display artifact, not as a source of truth

## 7. capture_shutters

The old operator instinct around "adrenaline shutter" maps here, not to a second runtime mythology.

Active concrete shutters:

- `live_render_shutter`
- `structured_snapshot_shutter`
- `contact_body_shutter`
- `web_theater_shutter`

They exist to freeze evidence at the projection seam.

They do not become a second authority plane.

## 8. corroboration_feedback

Each frame should feed back:

- rendered text summary
- rendered web summary
- capture ids
- silhouette agreement
- timing agreement
- text projection agreement
- freshness agreement
- bundle agreement

This is where equilibrium learns whether the merged projection actually held together.

## Dentist Order

Fix the surrounding teeth before the broken tooth.

### Tooth 1: trace identity

Normalize one required trace identity across activity, command, and projection.

### Tooth 2: render spine identity

Make `sequence_id`, `frame_id`, `spine_id`, and `command_sync_token` travel together.

### Tooth 3: current front

Promote `watch_board.current_front` into the explicit render-spine locator.

### Tooth 4: active pointer

Promote `tinkerbell_attention.active_pointer` into the same packet instead of leaving it as advisory flavor.

### Tooth 5: capture receipts

Make shutter results land back into the spine packet as real receipts.

### Tooth 6: theater constitutions

Separate text and web authority cleanly.

### Tooth 7: equilibrium render packet

Make one render merge surface, not two cooperating guesses.

### Broken tooth: hair

Only after the above:

- rebuild hair as geometry under gravity
- stop web hair from authoring text
- stop text theater from inferring a separate haircut
- make both theaters consume the same equilibrium-approved projection

## Hair Consequences

For the current saiyan problem, this architecture implies:

- gravity belongs to the shared render spine and field state
- hair topology belongs to the web constitution
- hair messaging belongs to the text constitution first
- hair text projection onto web requires explicit equilibrium approval
- web hair must never self-form words
- text theater must never infer a separate head of hair

## Minimum Packet Set To Build Next

Smallest honest implementation set:

1. `render_spine_packet`
2. `text_constitution_packet`
3. `web_constitution_packet`
4. `equilibrium_render_packet`
5. `capture_receipt_packet`

## First Implementation Slice

Build this first, without solving every visual issue at once:

1. derive `render_spine_packet` from activity + query thread + output state
2. attach `watch_board.current_front`
3. attach `tinkerbell_attention.active_pointer`
4. attach `freshness`
5. attach shutter receipt refs
6. make both theaters read the same `spine_id`

If that lands, the pipeline becomes findable in the dark.

## Authority Rules

Rules that should not bend:

- live query thread outranks archive continuity when they diverge
- archive continuity remains recovery help, not live render truth
- `output_state` stays the carried orienting crane
- theater projections are downstream of equilibrium
- capture shutters verify frames; they do not replace the frame authority
- no new hidden authority plane gets invented in the name of convenience

## Success Condition

The pipeline is correct when:

- the operator can point to one `spine_id`
- both theaters can name the same current frame
- `current_front` and `active_pointer` agree on what matters now
- freshness is visible and trusted
- captures can prove what actually rendered
- hair and text stop diverging into separate realities

