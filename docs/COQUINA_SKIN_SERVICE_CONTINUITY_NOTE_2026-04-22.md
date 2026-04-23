# Coquina Skin Service Continuity Note

Date: 2026-04-22
Status: active continuity seam

## Purpose

Carry the current calibration lane across resets without depending on transcript archaeology.

This note records the current seam where:

- `The Cage` sequence field
- hair reactivity
- body orientation
- punch dynamics
- elemental/weather skin projection

are being tightened into one explicit `skin_service` face.

## Current Read

The correct abstraction is:

```text
truth surfaces
  -> sequence_field.force_wave
    -> skin_service
      -> web material consumer
      -> text braille consumer
      -> hair field consumer
      -> trail/aura consumers
```

This is not a new authority plane.

It is a consumer/service face over the existing truth spine:

- support / balance / Pan truth remain authoritative
- sequence poles remain authoritative
- `skin_service` translates that truth into visible embodiment

## What Is Landed

### Runtime packet

`static/main.js` now emits a first-class:

- `sequence_field.force_wave.skin_service`

with:

- `profile`
- `medium_kind`
- `flow_class`
- `routing_mode`
- `wrap_mode`
- `support_phase`
- `slot_classes`
- `consumers`

Current routing doctrine:

- `routing_mode = pacman_wrap`
- `wrap_mode = neutral_center_return`

### Web consumer lane

The scaffold visual pass now reads the `skin_service` medium/flow lane when projecting elemental body and punch skins.

Current split:

- hair slots remain text-surface anchor consumers
- body/leg/torso slots remain geometry consumers
- punch slots remain geometry consumers
- body and leg geometry motion are now gated behind an explicit `pose_drive_enabled` flag

This is deliberate.
Do not collapse the full body into text-only anchors unless that is the explicit task.

### Text/blackboard lane

`scripts/text_theater.py` now exposes `skin_service` in:

- sequence field text lines
- sequence field blackboard lines

`static/main.js` now exposes `skin_service` in:

- theater readouts
- semantic triplets
- verbose theater summaries

## Practical Interpretation

The intended read is:

- hair = first text-native skin surface
- body = hybrid elemental skin
- punch = burst-focused elemental skin
- future Coquina skins = additional consumers, not a second truth source

This is the beginning of the broader Coquina skin/service lane:

- composable substratum
- don-able elemental armor
- parameterized profile ranges
- multiple render consumers over one truth spine

Related permanent doctrine:

- `docs/COORDINATED_ACCELERATION_SOLUBLE_SURFACES_REVELATION_2026-04-22.md`
- UUID: `a6314276-e50d-480f-a28a-a59556c8bda2`

## Known Guardrails

1. `skin_service` must not outrank live support/contact/balance truth.
2. Do not let elemental spectacle write back into blackboard, Dreamer, or controller authority.
3. The body lane should remain pose-readable; elemental skin should amplify it, not hide it.
4. Hair is still the hottest consumer. Body motion leaks should be fixed in the body/split carrier, not by muting hair.
5. Until there is a real authored split clip or an explicit pose-drive flag, `split_loop_dynamics` and `body_orientation` may describe posture but must not procedurally invent chassis motion.

## Return Recipe

If context resets:

1. Re-open this note.
2. Re-check:
   - `static/main.js`
   - `scripts/text_theater.py`
3. Resume from:
   - `sequence_field.force_wave.skin_service`
   - then verify web/text parity
   - then continue into Coquina full-body skin service

## Next Honest Moves

1. Promote `skin_service` from Cage-specific packet into a reusable force/embodiment service contract.
2. Add profile families:
   - `saiyan_fire`
   - `rain_sheet`
   - `charged_field`
   - `neutral_support`
3. Let Coquina body slots opt into skin-service consumers by `surface_classes` and `region_class`, not by one-off hacks.
4. Keep `Pac-Man` wrap / neutral-center-return as routing policy, not controller truth.
