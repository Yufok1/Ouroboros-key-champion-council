# Glyph Field Elemental Substrate Spec 2026-04-13

Repo: `F:\End-Game\champion_councl`

Purpose:

- map the user's elemental weather / force-of-nature rendering idea into the repo's existing glyph-box doctrine
- keep the new substrate aligned with text-theater-first rules
- prevent drift into hidden persuasion, decorative mush, or parallel control planes
- define the first honest build order for rain, current, fire, fog, smoke, and later angular multi-page text objects

Related docs:

- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md)
- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [TEXT_THEATER_NEGATIVE_SPACE_MOLD_VIEW_NOTE_2026-04-13.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_NEGATIVE_SPACE_MOLD_VIEW_NOTE_2026-04-13.md)

## Bottom Line

The elemental text renderer is not a new renderer family.

It is:

- one glyph-box substrate
- one buoyant reference surface
- one set of hard readable state bands
- one world-truthful motion field
- many element profiles

The first proof case is rain.

If the substrate is correct, then:

- drizzle
- hail
- sleet
- fog
- smoke
- ash
- snow
- fire
- current
- flood debris

become parameter families over the same engine class.

## Correct Alignment

This spec inherits the current repo rules:

- one truth source
- text theater and web theater are peer consumers
- blackboard remains the text-theater reasoning/worksheet surface
- elemental glyph fields are render consumers over shared truth, not a new authority
- v1 of this lane is text-theater-only until the contract is pinned and reproducible
- no hidden semantic influence
- no covert suggestion
- no social engineering tricks disguised as rendering cleverness

If semantic text is present, authorship and invocation must remain explicit.

Reveal, do not insinuate.

## Core Doctrine

### 1. The glyph equilibrium system is the base

The equilibrium model is already the right one:

- the default fixed-width character box is the common measure
- that box is the readable reference state
- projected size, depth, and medium determine how a glyph appears

This is not:

- dot blob -> random letter

It is:

- one glyph identity
- many valid render states over that identity

### 2. Motion truth and readability truth are separate

Do not force the field to orient toward the camera just to show off the letters.

Instead:

- motion obeys world truth
- readability obeys glyph equilibrium truth

Examples:

- rain falls along gravity or a chosen field vector
- current advects through water volume
- fire rises from a rooted source under buoyancy/turbulence
- fog drifts and obscures

The observer discovers readable glyph identity where conditions allow.

That is stronger than a renderer that is always "trying to tell you" what it is.

### 3. No ghost glyph mush

The system must not rely on vague half-letters or manipulative ambiguity.

The user correction is correct:

- no half-ghost characters
- no fuzzy almost-letter sludge
- no covert persuasion through illegible suggestion

The visual language should feel closer to cel-shaded state changes:

- when a glyph is supposed to pop, it pops
- when it is obscured, it is distinctly obscured
- when it is granular, it is clearly granular

## Hard State Bands

The elemental substrate should use hard readable state bands, not a continuous mush gradient.

For one glyph identity:

### `spec`

- tiny particulate mark
- not pretending to be a readable letter yet
- clear distant particle behavior

### `blob`

- braille/occupancy mass
- visibly particulate
- not ambiguous and not fake-text

### `granular`

- occupancy/stroke-bearing glyph residue
- braille/dot/block support still dominant
- glyph structure begins to read

### `fused`

- softened but definite glyph
- still clearly that glyph
- may be partially obscured by medium, haze, density, or overlap

### `reference`

- crisp canonical default-font glyph
- full readable identity
- the strongest equilibrium state

These are not separate systems.
They are discrete state bands over one glyph-box model.

## Consumer Contract Ownership

The first elemental consumer contract is:

- `snapshot.weather`

Ownership rule:

- environment/world-profile truth remains the authority
- the text-theater snapshot builder is the first consumer-contract assembler
- v1 is text-theater-only

That means:

- no separate weather authority plane
- no standalone renderer-owned effect state
- no web-theater-specific elemental contract in v1

If this lane later becomes peer-consumed by web theater, both consumers must receive the same effective contract.

## Elemental Substrate Model

Every elemental field should be defined by the same contract family:

- `kind`
- `flow_class`
- `source_behavior`
- `direction_field`
- `speed`
- `density`
- `turbulence`
- `persistence`
- `wrap_mode`
- `volume`
- `glyph_set`
- `glyph_profile`
- `lod_bands`
- `obscuration_rules`
- `collision_or_settling_rules` when relevant

This keeps the engine generic while letting the profiles differ honestly.

`glyph_profile` is non-semantic.

It may define:

- occupancy style
- stroke bias
- emphasis rules
- allowed render support primitives

It must not define:

- hidden words
- scene-conditioned semantic suggestions
- context-derived glyph selection

No glyph selection may be a function of scene semantic content.

## Motion Field Ownership

V1 rain is allowed to ride:

- gravity
- explicit direction override already present in environment/world-profile truth

Anything beyond that, including:

- wind
- buoyancy field
- current
- turbulence field

must be introduced as a named truth producer before a profile using it can ship.

No profile may synthesize a new motion authority from renderer-local invention.

## Deterministic Band Selector

Band selection is a pure function.

Inputs:

- projected glyph size
- depth
- medium density
- local orientation
- readability_required
- profile thresholds from `lod_bands`

Output:

- exactly one of:
  - `spec`
  - `blob`
  - `granular`
  - `fused`
  - `reference`

Rules:

- one glyph, one band, per frame
- no blended band states
- no renderer-specific ad hoc interpolation
- if two consumers implement the same inputs and thresholds, they must choose the same band

Obscuration and density may demote readability.
They may not invent intermediate fake glyph states.

## Element Profiles

The first profile is `rain`.

After that, the same substrate should cover:

### `rain`

- precipitation
- gravity-dominant
- coherent downward field

### `drizzle`

- sparse rain
- thinner density
- lower velocity

### `hail`

- dense ballistic particulate
- chunkier collision/readability profile

### `sleet`

- mixed rain/hail profile

### `snow`

- slower descent
- more lateral turbulence
- softer clustering

### `mist`

- drifting low-speed volume
- obscuration more important than individual particle identity

### `fog`

- dense obscuring medium
- glyphs behind it remain explicit but visibly occluded

### `smoke`

- buoyant drift
- high persistence
- strong obscuration role

### `ash`

- drifting ember/ash particulate
- mixed descent and lateral turbulence

### `current`

- submerged or lateral advection field
- direction derived from flow/current rather than downward gravity

### `fire`

- rooted source behavior
- buoyancy-dominant upward motion
- unstable coherence
- emissive emphasis
- often emits smoke as a paired field

### `flood`

- not just particles
- moving front/volume plus carried glyph debris, foam, and spray

## Consumer Roles

The substrate serves three different consumer roles.

### 1. Blackboard

- operator-authored or operator-invoked payloads
- diagnostics
- calculations
- query-work
- corroboration

### 2. Elemental fields

- environmentally-derived payloads
- atmosphere
- perturbation
- flow
- material-state embodiment

### 3. Authored spatial text objects

- operator-authored spatial pages
- books, signs, angular page objects
- future multi-view readable surfaces

Shared engine class:

- camera/view affects what resolves
- same glyph-box reference system
- same projection-aware rendering family
- same shared-truth discipline

Hard boundary:

- shared engine does not mean shared payload shape
- blackboard and elemental fields must not compose into one render payload
- authored spatial text objects are a future consumer, not justification for covert semantics in elemental fields

So the correct statement is:

- blackboard, elemental glyph fields, and authored spatial text objects are different consumers of the same glyph-equilibrium substrate

## Explicit Ownership Guardrail

If the system expresses:

- words
- sentences
- diagrams
- angle-dependent pages
- symbolic messages

then that power must remain:

- obvious
- attributable
- intentionally invoked
- operator-owned

Not:

- covertly insinuated
- secretly persuasive
- socially manipulative

If semantic force is present, authorship must remain explicit.

This substrate is allowed to reveal.
It is not allowed to smuggle.

## Angular Page Multiplexing

This is a future lane, not the first build.

The user direction is valid:

- one object
- one glyph field
- many valid legibility cones
- different view angles yield different readable pages

Practical term:

- `angular page multiplexing`

This is like a volumetric multi-view book:

- same field
- different readable page by view vector

This should be treated as:

- a later consumer of the same substrate
- not a separate architecture
- specifically the future authored-spatial-text-object role, not the elemental-field role

Order matters:

1. stable single-view elemental glyph field
2. hard readable state bands
3. explicit obscuration rules
4. directional gating
5. angular page multiplexing

## Obscuration Rules

Fog, smoke, haze, density, overlap, and medium thickness should not destroy glyph truth.

They should:

- obscure it explicitly
- soften it explicitly
- break it into granular bands explicitly
- reduce the active band or hide occupied cells explicitly

Never:

- imply letters through random mush
- rely on ghosted suggestion

The right rule is:

- glyph identity may be reduced
- glyph identity may be partially hidden
- glyph identity must not be faked

Positive production rule:

- obscuration may lower a glyph from `reference` to `fused`, `granular`, `blob`, or `spec`
- obscuration may hide support cells entirely
- obscuration may not create new stroke structure that was not present in the underlying glyph identity

## Practical Rendering Rule

The renderer should choose state by:

- projected glyph size
- depth
- medium density
- local orientation
- readability requirement
- profile thresholds

Not by:

- arbitrary effect-specific hacks
- one-off special-case glyph renderers
- constant camera-facing cheats

## Recommended Build Order

### Phase 1 — Substrate Truth

- keep text-theater-first
- pin `snapshot.weather` as the first elemental consumer contract
- keep it environment-owned and profile-derived
- declare v1 text-theater-only
- define the deterministic band selector before adding medium complexity

### Phase 2 — Rain

- implement `rain` as the first volumetric glyph field
- use hard state bands:
  - spec
  - blob
- granular
- fused
- reference
- start with gravity/direction only
- no obscuration dependencies yet

### Phase 3 — Medium Modifiers

- add explicit obscuration:
  - fog
  - smoke
  - haze

### Phase 4 — Fire / Current

- fire as buoyant rooted field
- current as lateral/submerged field

### Phase 5 — Angular Multiplexing

- directional page cones
- multi-view glyph objects
- "book around a fire" class surfaces

## Guardrails

- not a second control plane
- not a replacement for blackboard
- not a covert influence engine
- not mushy interpolation art
- not per-effect bespoke renderer sprawl
- not web-first
- not semantic ambiguity disguised as cleverness
- not a blended-state renderer
- not a hidden motion producer

Additional hard rules:

- the band selector returns exactly one band per glyph per frame
- a new profile may not introduce a new renderer path
- elemental field state never flows back into blackboard, route, controller, Dreamer, or any reasoning surface as authority input
- if a future web consumer is added, it must receive the same effective contract as text theater

## Failure Classification

Any elemental-field bug must be classified before a fix is proposed:

- `truth`: the authoritative environment/world-profile producer is wrong or missing
- `contract`: `snapshot.weather` is wrong, narrowed, or underspecified
- `transport`: relay/live-cache delivery is stale or incomplete
- `rendering`: the consumer chose the wrong band or drew the right band incorrectly
- `gating`: a valid field was suppressed by consumer mode or policy

Do not compress these into one story.

## Short Version

Build one text-theater glyph field substrate where:

- world motion is truthful
- glyph identity stays anchored to the default readable character box
- state changes are discrete and legible
- elements become profiles over one engine
- `snapshot.weather` is the first pinned consumer contract
- v1 stays text-theater-only
- blackboard remains the reasoning surface
- authored spatial text objects are a later separate consumer role
- and later angular multi-page objects become another consumer of the same substrate

That is the lane.
