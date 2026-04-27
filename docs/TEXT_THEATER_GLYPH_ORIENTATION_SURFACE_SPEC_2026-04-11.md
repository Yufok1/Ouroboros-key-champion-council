# Text Theater Glyph Orientation Surface Spec 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- capture the user's clarified "buoyant surface" model for text rendering
- define characters as orientation-bearing primitives rather than mere labels
- align terminal text rendering, blackboard readouts, and future state-space text objects under one glyph-box doctrine

Related docs:

- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)
- [TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md)

## Bottom Line

The correct model is not:

- plain terminal text
- or dots pretending to be text
- or giant banner glyphs

The correct model is:

- **one canonical character box**
- **one common buoyant reference surface**
- **multiple focus levels over the same glyph occupancy**

Characters are not only labels.

They are:

- orientation carriers
- corner/edge/surface primitives
- scale references
- and later, state-space material for text-rendered objects

The text theater, blackboard, and future web/state-space text objects should all be different consumers of the same underlying glyph-box model.

## 2026-04-11 Data-First Pivot

The later same-day correction is important and should override any looser reading in this file:

- letters and numbers remain the primary readable data lane
- variables, measurements, labels, and values should stay solid alphanumeric text
- shape, angle, contour, and depth depiction should move to non-alphanumeric symbol lanes
- dot/braille/block fill exists to reinforce those symbol lanes, not to replace the data lane

That means the system should **not** try to embody a whole model or environment out of letters and numbers when doing so would reduce readability or confuse observation.

The right split is:

1. alphanumeric text informs
2. symbolic/ascii geometry depicts
3. granular fill blends and stabilizes the depiction

This preserves the blackboard's real job:

- informative rather than destructive
- robotics-class readable rather than clever
- camera-relative and spatially aware without sacrificing legibility

## Core Doctrine

## 1. The default character cell is the common variable surface

The normal fixed-width character box is the baseline world-measure for:

- scale
- occupancy
- perspective
- distance readability
- state-space text sizing

This is the user's "buoyant surface."

It is the stable calibration plane against which other text renderings are measured.

Examples:

- text on a shirt
- text on a small prop
- text on a newspaper
- text on a distant sign

All of those can be described as:

- a character box size
- a projected distance
- a focus level
- a chosen glyph occupancy mode

## 2. A glyph is a micro-faceted surface, not just a symbol

Keyboard characters already encode shape information:

- verticals
- horizontals
- diagonals
- corners
- bowls
- terminals
- apertures
- interior voids
- heavy and light fills

That means a character can do two jobs at once:

1. represent itself as a readable symbol
2. contribute orientation and surface information to a larger depiction

This is the important leap:

The letter `A` is not only "the letter A."

It is also:

- two diagonals
- a crossbar
- an interior void
- a peaked silhouette

When many such glyphs are tiled, aligned, and perspective-driven, they stop behaving like isolated labels and start behaving like a structured surface field.

## 3. Focus changes are not separate renderers

There should not be one renderer for:

- plain text
- another for dot text
- another for state-space text objects

There should be one glyph-box model with multiple focus levels:

### `reference`

- canonical fixed-cell value
- pure readable symbol
- used as baseline world measure

### `fused`

- readable enlarged operator text
- glyph occupies the box as a stable readable form
- used for menus, blackboard rows, and diagnostics readouts

### `granular`

- occupancy/stroke view of the same glyph
- used when close inspection or state-space articulation matters

### `field`

- groups of glyphs acting as a continuous oriented surface
- used for state-space text objects, hybrid skins, or procedural diagnostic surfaces

These are focus levels of the same variable, not distinct systems.

## 4. Characters should be used directly when they are already the right shape

The user constraint is correct:

- if a keyboard character is already the right or near-right shape, use it directly
- only use granular occupancy support when the glyph alone is insufficient

So the priority order is:

1. direct character use
2. character plus substrate support
3. occupancy-only/granular render

That keeps the surface anchored in real text instead of drifting into unreadable glyph noise.

## Character Surface Taxonomy

The renderer should treat characters as belonging to reusable surface classes.

## 1. Line primitives

Examples:

- `|`
- `-`
- `_`
- `/`
- `\\`

Use:

- edges
- direction
- axis cues
- simple contour runs

## 2. Corner and joint primitives

Examples:

- `+`
- `L`-like forms from box-drawing families
- `┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼`

Use:

- corner emphasis
- junctions
- support edges
- local contour turns

## 3. Surface-fill primitives

Examples:

- `.`
- `:`
- `=`
- `#`
- `@`
- block/quadrant cells

Use:

- tone
- density
- interior surface occupancy
- confidence/load/intensity cues

## 4. Alphanumeric semantic primitives

Examples:

- `A`
- `rpm`
- `8`
- `31.2`
- `yaw`
- `risk=1`

Use:

- readable labels
- measurements and variables
- primary blackboard readouts
- explicit operator-facing state
- semantic identity that must remain immediately legible

Do not use alphanumeric primitives as the main shape-material lane for whole-model or whole-environment depiction.

If the renderer needs shape-bearing material:

- use line/corner/fill/symbol primitives first
- keep letters and digits for the actual data being communicated

## 5. Symbolic diagnostic primitives

Examples:

- arrows
- degrees
- percent
- triangles
- warning marks
- comparison operators

Use:

- blackboard deltas
- route direction
- telemetry emphasis
- invariants / holds / causation links

## Cornice / Angle Doctrine

The user's "cornice" intuition is correct and useful.

What matters visually is not just the existence of a glyph, but the observable edge logic of the glyph:

- its corners
- its flat runs
- its diagonal peaks
- its internal voids

Those edge features can grab attention faster than literal text recognition.

That means the renderer can use glyph cornice information in two ways:

1. `readable identity`
   - preserve enough structure that the glyph still reads as itself
2. `surface affordance`
   - use the glyph's edge/corner structure to reinforce direction, depth, contour, and orientation

This is very close in spirit to:

- cel shading
- line-and-block NPR
- orientation-driven hatch fields
- glyph-based visualization

but constrained by a character-box substrate.

## State-Space Implication

This doctrine scales directly into the future web/state-space renderer.

If a character box is treated as a world-space unit, then:

- a shirt letter
- a sign letter
- a newspaper letter
- a diagnostic surface glyph

can all be the same thing at different scales and distances.

That means future state-space text objects should be driven by:

- canonical glyph box size
- projected size on screen
- local surface orientation
- fit score against candidate glyph families
- profile-specific style constraints

Not by:

- ad hoc text sprite decisions
- separate bespoke "ASCII object" logic for each feature

## Practical Rendering Model

The renderer should eventually work like this.

## Step 1: canonical glyph box

For every character:

- define a canonical occupancy box
- preserve edge/corner semantics
- preserve readable identity threshold

## Step 2: direct glyph fit

If the target surface/row/object can be truthfully represented by a direct character, do that first.

Examples:

- `|`
- `/`
- `#`
- `>`

## Step 3: substrate support

If direct glyph fit is insufficient:

- add occupancy support
- add plate/background support
- add edge emphasis
- add density fill

But keep the glyph identity intact when operator readability matters.

## Step 4: orientation-field composition

When many glyph boxes are arranged together:

- fit them against local direction/normal/tone fields
- keep the whole field coherent with the current camera orientation
- allow them to act as a quasi-continuous surface

This is the path toward:

- text-rendered 3D objects
- hybrid skins
- diagnostic panel fields
- later procedural objectification in the web theater

## Obvious Wins

These are the most useful next wins for total design quality.

## 1. Glyph vocabulary registry

Add a registry for characters grouped by:

- line
- corner
- fill
- alphanumeric semantic
- symbolic diagnostic

This gives the system a controlled vocabulary instead of random glyph selection.

## 2. Glyph occupancy atlas

Precompute per-glyph:

- occupancy mask
- edge/corner descriptors
- readable-identity threshold
- orientation descriptors

This becomes the shared primitive set for terminal and state-space consumers.

## 3. Fit scorer

For any target cell or object patch, score candidate glyphs by:

- orientation match
- density match
- semantic appropriateness
- readability requirement
- profile family constraints

## 4. Profile-aware glyph grammars

Profiles should not just pick colors and chrome.

They should also choose glyph bias:

- `Mechanics Telemetry`
  - precise line/corner/indicator glyphs
- `Route / Telestrator`
  - arrows, trails, high-directionality glyphs
- `Spectacle / Showcase`
  - bolder silhouettes and high-presence fills
- `Archive / Inspection`
  - restrained, readable identity-first glyphs

## 5. Shared world-scale contract

The same glyph-box sizing rules should drive:

- terminal blackboard text
- future CSS2D/CSS3D labels
- future text-rendered web objects
- future hybrid skins

That is what keeps parity honest.

## What To Avoid

Do not let the system drift into:

- unreadable braille noise
- arbitrary dot blobs
- profile skins that break glyph identity
- decorative density without directional meaning
- one-off per-feature text renderers

The whole point is:

- one substrate
- one reference surface
- multiple focus levels
- multiple consumers

## Research Alignment

This direction is not random. It is consistent with several known graphics/visualization ideas:

- glyph-based visualization emphasizes that spatially distributed glyphs can encode multivariate structure more effectively than undifferentiated marks
- non-photorealistic rendering literature repeatedly uses direction, density, and stroke fields to communicate shape
- minimal line-and-block rendering shows that shape can be preserved with a reduced primitive vocabulary when line/block choice is controlled
- orientation-aware ASCII synthesis explicitly uses local pixel orientation when choosing characters
- Three.js/Troika-style text pipelines support crisp dynamic glyph rendering in 3D, which is relevant for later state-space consumers

## Recommended Build Sequence

1. formalize glyph vocabulary classes
2. formalize canonical glyph-box / occupancy descriptors
3. make the terminal operator surfaces use fused readable glyph LOD
4. preserve granular occupancy mode as a close-focus/state-space mode
5. later, expose the same glyph-box metrics to web/state-space text consumers

## Final Doctrine

The character cell is not a limitation to fight.

It is the common measured surface.

The glyph is not only a symbol to print.

It is a shaped orientation primitive.

The granular substrate is not a replacement for text.

It is the continuity layer that lets text become surface.

That is the right foundation for:

- text theater readability
- blackboard coherence
- future diagnostic slates
- future state-space text objects
- and later hybrid glyph surfaces in the web theater

## Sources

- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_PROFILE_FAMILIES_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)
- [PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md](/F:/End-Game/champion_councl/docs/PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md)
- [Glyph-based Visualization: Foundations, Design Guidelines, Techniques and Applications](https://www.researchgate.net/publication/235928194_Glyph-based_Visualization_Foundations_Design_Guidelines_Techniques_and_Applications)
- [Artistic minimal rendering with lines and blocks](https://www.sciencedirect.com/science/article/abs/pii/S1524070313000143)
- [Fast Text Placement Scheme for ASCII Art Synthesis](https://www.researchgate.net/publication/359968108_Fast_Text_Placement_Scheme_for_ASCII_Art_Synthesis)
- [Three.js Manual: Creating Text](https://threejs.org/manual/en/creating-text.html)
- [Troika Three Text](https://protectwise.github.io/troika/troika-three-text/)
