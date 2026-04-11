# Text Theater Seven-Form Data-First System 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- lock the corrected goal for the text-theater render system
- preserve the 7-form ambition without sacrificing readability
- separate the semantic data lane from the depictive shape lane

Related docs:

- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)

## Bottom Line

The project is no longer pursuing "embody the whole model out of letters and numbers."

The corrected rule is:

- letters and numbers are for readable state, variables, units, and measurements
- non-alphanumeric symbols are for contour, angle, direction, and shape scaffolding
- dot/braille/block fill is for blending and continuity between those symbol structures

This keeps the text theater useful as a robotics-class instrument:

- informative first
- camera-relative
- spatially aware
- but not observationally confusing

## Live Corroboration

At the time of this pivot, live `env_read(query='shared_state')` confirms:

- `shared_state.text_theater_control` exists with `surface_mode` and `surface_density`
- `shared_state.text_theater_profiles` exists with the 7-family registry
- `shared_state.blackboard` exists with live row families and camera-relative working-set state

Current source also confirms:

- `scripts/text_theater.py` now exposes programmable operator surfaces with `legacy`, `sharp`, and `granular` modes
- the scene/model depiction path is still the existing scene lane, not a new letter-body renderer
- the current acceptable operator default is readable solid text over a controlled substrate, not letter-shaped scene embodiment

## The Seven Forms

The 7-form system should now be read like this.

### 1. Reference Data

Default fixed-cell alphanumeric text.

Use:

- variables
- measurements
- ids
- units
- exact values

This is the canonical truth lane.

### 2. Fused Operator

Readable enlarged operator text on a controlled substrate.

Use:

- menus
- blackboard sections
- status lanes
- consult surfaces

This is still semantic text, not depictive geometry.

### 3. Priority Value

Selective emphasis of the most important variables and numbers.

Use:

- lead blackboard rows
- current risk, margin, route, load, contact, and corroboration values
- values the operator or agent must notice first

This is the "terminator view" requirement: the important data must win the screen.

### 4. Symbolic Orientation

Non-alphanumeric geometry primitives:

- `|`
- `-`
- `/`
- `\`
- box-drawing
- arrows
- brackets
- comparison marks

Use:

- angle cues
- route direction
- leader lines
- contour hints
- edge/corner logic

### 5. Granular Fill

Dot, braille, block, and texture-like fill.

Use:

- surface continuity
- intensity or density support
- confidence/load shading
- blending between symbolic orientation elements

This never replaces the primary data lane.

### 6. Symbolic Field

A coherent field composed from Forms 4 and 5.

Use:

- diagnostic hulls
- orientation patches
- angle-bearing overlays
- future blackboard spatial slates

This is the depictive lane, but it should stay non-alphanumeric by default.

### 7. Spatial Consumer

A web/cube/state-space consumer that reuses the same rules.

Use:

- CSS2D slates
- diagnostic cubes
- future text-backed spatial overlays

The split remains the same:

- alphanumeric text informs
- symbolic geometry depicts

## Hard Rules

1. Do not build whole-body or whole-environment depiction primarily out of letters and digits.
2. Keep the current solid alphanumeric data lane readable at all times.
3. If a shape/angle lane is needed, build it from non-alphanumeric symbol vocabularies first.
4. Use granular fill only to support orientation continuity, not to disguise unreadable text.
5. Blackboard row ranking should prioritize the most operationally important variables and values before any depictive flourish.

## What This Means For The Blackboard

The blackboard remains:

- structured data first
- rendered surface second
- camera-relative in layout and row promotion

But the render policy is now explicit:

- values and labels stay in the alphanumeric lane
- directional or contour assistance may appear around them in symbolic lanes
- the screen should read like a classic robotics instrumentation surface, not like stylized alphabet camouflage

## What Is No Longer The Goal

Do not pursue:

- a letter-made full scene
- a number-made body shell
- a tiled alphabet legionnaire as the default depiction model
- clever glyph embodiment that competes with readable telemetry

Those ideas may remain as distant experiments, but they are not the mainline trajectory.

## The Productive Mainline

The mainline now is:

1. make blackboard values rank and read correctly
2. make operator surfaces stable and low-lag
3. make symbolic geometry assist the data without obscuring it
4. later reuse that split in spatial/web consumers
