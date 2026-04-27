# Text Theater Profile Families 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- define the base presentation families for the text theater / blackboard / web-theater text consumers
- keep profile work grounded in surface purpose, not just style taste
- separate **base families** from **variants**
- provide a practical implementation contract for future profile-aware consumers

Related docs:

- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)
- [TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_BLACKBOARD_REDO_AUDIT_2026-04-11.md)
- [TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md](/F:/End-Game/champion_councl/docs/TEXT_THEATER_SPATIAL_BRIDGE_TRAJECTORY_2026-04-11.md)

## Bottom Line

Do **not** start with 10 unrelated skins.

The right first cut is:

- **7 base profile families**
- with **4 first-wave implementations**
- and later **many variants** derived from those families

Why:

- the system has multiple real surface jobs
- each job needs a different bias in hierarchy, density, and emphasis
- most visually different ideas are better treated as variants of the same base family

Example:

- `Casino Marquee` and `Train Yard Graffiti` are not separate base families
- they are both variants of a broader **Spectacle / Showcase** family

## Profile Doctrine

A profile is **not** just a font.

A profile controls:

- title/compositor style
- row density
- hierarchy
- separator language
- tolerance color semantics
- icon/glyph vocabulary
- trace rendering bias
- motion/update behavior
- which row families are promoted or suppressed
- what the surface feels like under interaction stress

So a profile is:

**presentation grammar + emphasis policy**

not:

**cosmetic paint**

## Base Families

## 1. Operator Default

Purpose:

- the clean everyday baseline
- general diagnostic reading
- text-theater default and general blackboard consumer

Best for:

- main text theater
- mixed diagnostics
- general session work
- everyday route/contact/controller reading

Presentation grammar:

- restrained chrome
- strong section hierarchy
- readable medium density
- minimal ornament
- explicit labels and units

Bias:

- no strong subsystem favoritism
- keeps the surface honest and broadly useful

Implementation tone:

- this should be the baseline profile if no other profile is chosen

## 2. Mechanics Telemetry

Purpose:

- embodied mechanics truth
- support, contact, stability, load, grounding

Best for:

- invisible-man mode
- balance diagnostics
- contact patch review
- support polygon / CoM / footing systems

Presentation grammar:

- medical-monitor / lab-instrument feeling
- clear tolerance states
- traces, trends, and deltas
- low ambiguity under motion

Bias:

- promote balance, support, load, contact, corroboration
- de-emphasize decorative/session chatter

Implementation tone:

- highest value for current body-ground interaction work

## 3. Drafting / Authoring

Purpose:

- geometry review
- builder/workbench reasoning
- proc-gen/model-construction inspection

Best for:

- scaffold inspection
- part isolation
- dimension-like readouts
- authored clip and pose construction

Presentation grammar:

- blueprint / drafting-sheet feel
- dimension arrows
- measured spacing
- structural labels over emotional labels

Bias:

- promote scaffold, dimensions, part surfaces, controller topology, authored structure
- suppress alarm-heavy visual language unless actually necessary

Implementation tone:

- best family for Coquina-style body authoring and workbench sessions

## 4. Route / Telestrator

Purpose:

- explain motion intent, planned path, phase sequences, and blockers

Best for:

- transition sequencer
- route reports
- maneuver explanation
- contact-phase debugging

Presentation grammar:

- sports-telestrator / plan-board feel
- path lines, numbered callouts, arrows, phase marks
- visible deltas between intended and realized

Bias:

- promote route, controller, phase, corroboration, trace rows
- de-emphasize low-priority static environment rows

Implementation tone:

- this is the most natural family for AI-authored explanation overlays later in web theater

## 5. Archive / Inspection

Purpose:

- calm reading, object review, artifact inspection, summoned depictions

Best for:

- bag/object inspection
- comparative review
- archive-like panels
- later text-backed object depictions

Presentation grammar:

- placard / catalog / specimen-card feel
- spacious
- low motion
- calm typography

Bias:

- promote metadata, provenance, object attributes, stable snapshots
- suppress aggressive warning language unless truly severe

Implementation tone:

- useful when the operator/agent wants reading more than active piloting

## 6. Alert / High Contrast

Purpose:

- failures, blockers, invariants, critical mismatches

Best for:

- phase failure
- support impossibility
- route blocker surfaces
- accessibility-first high-clarity states

Presentation grammar:

- bold, sparse, unmistakable
- strong contrast
- reduced clutter
- explicit alarm wording

Bias:

- promote failures, blockers, invariant rows, mismatch/corroboration deltas
- suppress anything nonessential

Implementation tone:

- this is a utility family, not a default look

## 7. Spectacle / Showcase

Purpose:

- expressive chrome
- high-identity overlays
- promotional/dev/showcase surfaces

Best for:

- banner chrome
- mode switches
- theatrical debug identity
- future hybrid skin showcases

Presentation grammar:

- strongest compositor use
- oversized titles
- expressive separators
- high visual character

Bias:

- promote top-level state and dramatic transitions
- not for dense core diagnostics by itself

Implementation tone:

- this is where marquee, graffiti-inspired, stencil, and other personality-heavy variants belong

## Variants, Not Families

The following should be treated as **variants** of the base families above:

- `CRT Ops` → variant of `Operator Default`
- `Medical Monitor` → variant of `Mechanics Telemetry`
- `Drafting Vellum` → variant of `Drafting / Authoring`
- `Broadcast Telestrator` → variant of `Route / Telestrator`
- `Museum Plate` → variant of `Archive / Inspection`
- `Stencil Protest` → variant of `Alert / High Contrast`
- `Casino Marquee` → variant of `Spectacle / Showcase`
- `Train Yard Graffiti` → variant of `Spectacle / Showcase`

This keeps the system coherent:

- family defines the purpose and behavior
- variant defines the style expression

## First-Wave Implementations

Do not try to implement all 7 first.

Implement these 4 first:

1. `Operator Default`
2. `Mechanics Telemetry`
3. `Route / Telestrator`
4. `Spectacle / Showcase`

Why these 4:

- they cover general use
- current body-ground work needs `Mechanics Telemetry`
- transition sequencer work needs `Route / Telestrator`
- the new compositor/signage system needs a real expressive home in `Spectacle / Showcase`

The remaining 3 can come after the contract is proven:

- `Drafting / Authoring`
- `Archive / Inspection`
- `Alert / High Contrast`

## Profile Contract

Profiles should be described by data, not hardcoded ad hoc styling.

The contract should be staged.

### Core fields (Slice 1)

These are the fields worth registering immediately because they can already influence profile selection, row emphasis, and future consumer behavior:

- `id`
- `family`
- `variant`
- `promoted_families`
- `suppressed_families`
- `density`
- `audience`
- `row_admission`

Suggested Slice 1 contract:

```json
{
  "id": "mechanics_telemetry",
  "family": "mechanics_telemetry",
  "variant": "medical_monitor",
  "density": "medium",
  "promoted_families": ["balance", "support", "contact", "load"],
  "suppressed_families": ["session"],
  "row_admission": {
    "max_visible_rows": 14,
    "max_per_family": 5,
    "sticky_decay_ms": 5000,
    "session_weight_boost": 1.25,
    "blocker_auto_promote": true
  },
  "audience": "mixed"
}
```

### Rendering fields (Slice 2-3)

These belong in the design now, but do not need to be treated as fully-implemented obligations until real consumers read them:

- `chrome_profile`
- `title_mode`
- `separator_mode`
- `tolerance_palette`
- `glyph_set`
- `trace_profile`
- `overlay_profile`
- `motion_behavior`

Suggested full contract once those consumers exist:

```json
{
  "id": "mechanics_telemetry",
  "family": "mechanics_telemetry",
  "variant": "medical_monitor",
  "density": "medium",
  "promoted_families": ["balance", "support", "contact", "load"],
  "suppressed_families": ["session"],
  "row_admission": {
    "max_visible_rows": 14,
    "max_per_family": 5,
    "sticky_decay_ms": 5000,
    "session_weight_boost": 1.25,
    "blocker_auto_promote": true
  },
  "chrome_profile": "monitor",
  "title_mode": "display_banner",
  "separator_mode": "instrument",
  "tolerance_palette": {
    "WITHIN": "green",
    "WATCH": "yellow",
    "DEGRADED": "orange",
    "CRITICAL": "red",
    "INFO": "cyan"
  },
  "glyph_set": "monitor",
  "trace_profile": "waveform",
  "overlay_profile": "minimal",
  "motion_behavior": "stable",
  "audience": "mixed"
}
```

## Required Core Fields

Every profile family definition should eventually specify:

- `id`
- `family`
- `default_variant`
- `promoted_families`
- `suppressed_families`
- `density`
- `audience`
- `row_admission`

## Deferred Rendering Fields

The following belong in the design contract, but do not need full implementation in Slice 1:

- `title_mode`
- `separator_mode`
- `tolerance_palette`
- `glyph_set`
- `trace_profile`
- `motion_behavior`
- `chrome_profile`
- `overlay_profile`

## Row Admission

`promoted_families` and `suppressed_families` are not enough by themselves.

The anti-dump mechanism lives in `row_admission`.

Suggested shape:

```json
{
  "row_admission": {
    "max_visible_rows": 12,
    "max_per_family": 4,
    "sticky_decay_ms": 5000,
    "session_weight_boost": 1.5,
    "blocker_auto_promote": true
  }
}
```

This is what prevents:

- 200-row dumps
- blockers being buried under technically valid but low-importance rows
- session-relevant rows disappearing too fast

Different families should differ here on purpose:

- `Mechanics Telemetry` can be denser
- `Alert / High Contrast` should be sparse
- `Spectacle / Showcase` must stay selective or it becomes empty chrome

## Surface Mapping

Profiles should map to surface jobs explicitly.

### Text theater

- `main` → `Operator Default`
- `mechanics mode` → `Mechanics Telemetry`
- `route review` → `Route / Telestrator`
- `chrome banners` → `Spectacle / Showcase`

### Blackboard

- working set → `Operator Default`
- balance/contact cluster → `Mechanics Telemetry`
- phase/route slate → `Route / Telestrator`
- urgent blocker slate → `Alert / High Contrast`

### Web theater consumers

- CSS2D near-field slates → family chosen by row family / task
- diagnostic cube faces → face-local choice of family
- global mode banners → `Spectacle / Showcase`

### Composite / faceted consumers

Not every consumer is flat.

Diagnostic cubes, petal layouts, and future multi-panel spatial readers are **composite consumers**:

- one geometry
- multiple faces or sub-panels
- each face with its own sub-profile

Suggested future shape:

```json
{
  "id": "diagnostic_cube",
  "composite": true,
  "faces": {
    "front": { "family": "mechanics_telemetry", "promoted_families": ["balance", "route"] },
    "left":  { "family": "mechanics_telemetry", "promoted_families": ["contact"], "filter": { "side": "left" } },
    "right": { "family": "mechanics_telemetry", "promoted_families": ["contact"], "filter": { "side": "right" } },
    "top":   { "family": "operator_default", "promoted_families": ["load"] }
  }
}
```

This does not need Slice 1 implementation.

It does need to be part of the spec now so the registry does not assume every consumer is one flat profile target.

### Builder / authoring surfaces

- workbench and geometry review → `Drafting / Authoring`

### Archive surfaces

- bag/object inspection → `Archive / Inspection`

## Accessibility Rule

Profiles must never rely on color alone.

Every family/variant must retain:

- explicit row labels
- explicit tolerance text
- readable contrast
- interpretable glyph hierarchy without hue

This matches the blackboard doctrine:

- text theater is already the accessible consumer
- visual consumers are enhancements, not the only path

## Implementation Sequence

## Slice 1

Add profile registry in code with the 7 families and 4 first-wave variants.

No per-row styling engine yet.

## Slice 2

Wire profile selection to text-theater chrome:

- header
- pane titles
- status/control ribbons
- blackboard section titles

## Slice 3

Let row formatting respect profile emphasis:

- promoted families
- separator language
- trace style
- glyph vocabulary

## Slice 4

Let web consumers read the same family/variant selections.

This is where:

- CSS2D slates
- diagnostic cube faces
- later text-backed web surfaces

can stay visually coherent with the text theater.

## Guardrails

Do not let profiles:

- rewrite mechanics truth
- replace the blackboard contract
- become one-off hardcoded skins
- push expensive styling onto hot camera paths

Profiles are consumers of the structured row pool and theater snapshot.

They are not allowed to become a second data system.

Additional guardrail for `Spectacle / Showcase`:

- spectacle profiles must still render real promoted row families
- they are not allowed to degrade into pure chrome or placeholder slogans
- expressive treatment is valid only if the content remains real theater/blackboard truth

## Deferred Family Note: Agent Narration

One family is worth naming now even though it should stay deferred:

- `Agent Narration`

Purpose:

- structured machine-to-operator explanation
- why annotations
- phase explanations
- prediction vs actual commentary
- corroboration chain summaries

This overlaps with:

- blackboard interpretation
- prediction / corroboration layers

It may eventually become:

- its own family
- or a formal variant family under `Operator Default`

Do not build it in Slice 1.

Do keep it explicit in the design so explanation surfaces do not get awkwardly forced into `Mechanics Telemetry` or `Alert / High Contrast`.

## Decision

The correct number of base families is **7**.

The correct number of first implementations is **4**.

This gives enough coverage for:

- current mechanics work
- future blackboard work
- future spatial/text bridge consumers
- expressive chrome and showcase modes

without turning the system into an incoherent pile of unrelated terminal skins.

For Slice 1 specifically:

- register the 7 families
- implement the 4 first-wave families
- use core fields only
- defer rendering-field enforcement until consumers actually read them
