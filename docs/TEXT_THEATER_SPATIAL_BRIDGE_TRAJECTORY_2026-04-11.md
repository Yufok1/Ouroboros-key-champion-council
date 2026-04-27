# Text Theater Spatial Bridge Trajectory 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- capture the architectural implications of the latest user + Opus blackboard / diagnostic-cube / mixed-medium discussion
- ground those ideas in the current repo, not in speculative renderer drift
- define what is immediately buildable, what must wait for the blackboard contract, and what must stay off the live motion hot path

## Bottom Line

The latest direction is valid and stronger than a normal "HUD overlay" read.

The text theater should be treated as:

- a **shared interchange layer**
- a **primary diagnostic consumer**
- a **staging ground for mixed-medium renderers**

The blackboard should be treated as:

- a **stable structured row contract**
- plus **procedural collation**
- plus **multiple consumers**

The diagnostic cube, text-rendered 3D objects, hybrid text skins, and telestrator overlays are all valid **downstream consumers** of that contract.

They are **not** substitutes for the contract, and they are **not** allowed to own the live camera/motion path.

## Corroborated Current Foundation

The repo is already much closer to this than it looks at first glance.

### 1. Web theater already has the rendering substrate

Current source confirms:

- `THREE.EffectComposer` and post-processing pipeline exist in [`static/main.js`](/F:/End-Game/champion_councl/static/main.js)
- `RenderPass` and `UnrealBloomPass` are already wired in [`static/main.js`](/F:/End-Game/champion_councl/static/main.js)
- `CSS2DRenderer` is already instantiated in [`static/main.js`](/F:/End-Game/champion_councl/static/main.js)
- canvas -> texture -> sprite rendering is already used for agent tiles in [`static/main.js`](/F:/End-Game/champion_councl/static/main.js)

This means:

- HTML-in-3D patterns already exist
- scene post-processing already exists
- text-like sprite rendering already exists

Missing pieces are real, but smaller than they sound:

- `CSS3DRenderer`
- a selective ASCII/text-object renderer
- the blackboard row contract

### 2. Text theater already behaves like a cross-surface bus

Current architecture confirms:

- browser builds `shared_state`
- browser builds `shared_state.text_theater.snapshot`
- browser may publish `shared_state.text_theater.theater`
- browser may publish `shared_state.text_theater.embodiment`
- server and standalone text-theater consumers read that structure and render from it

This matches the user's intuition:

The text theater is not merely a terminal mirror. It is already a **bridge medium** between:

- live browser runtime
- terminal consult renderer
- `env_read(...)`
- future blackboard consumers
- future mixed-medium consumers

### 3. Existing doctrine already supports mixed-medium rendering

[`docs/PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md`](/F:/End-Game/champion_councl/docs/PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md)
already states the correct ownership rule:

1. substrate defines truth
2. world/embodiment state carries truth
3. blackboard/theater consumers render and explain truth

That rule applies just as much to:

- fireballs
- diagnostic cubes
- text-rendered objects
- hybrid skins
- telestrator marks

as it does to:

- support polygons
- balance rows
- route reports

## What The New Ideas Actually Mean

## 1. Diagnostic Cube

This is not "another HUD."

It is a **spatial container consumer** for blackboard families.

Correct role:

- use a 3D cube or box near a target body/object
- make each face a transparent perspective-correct panel
- map row families or row groupings onto faces
- allow leader lines / annotations / pinned slates to connect cube content to the enclosed subject

What it is good for:

- structured spatial review
- per-family comparison
- correlation across faces
- AI/operator telestration
- persistent session slates near the thing being reasoned about

What it should not do:

- become the authoritative blackboard itself
- recompute metrics on camera ticks
- replace the text-theater primary consumer

### Composite consumer rule

The diagnostic cube is not one flat consumer profile.

It is a **composite consumer**:

- one geometry
- multiple faces
- each face with its own row-family selection and LOD

That suggests a useful future model:

- geometry defines the spatial layout
- face or panel sub-profiles define content

This generalizes cleanly beyond cubes:

- cube
- prism
- petal cluster
- radial wing layout
- multi-contact panel arrays

So the reusable abstraction is not "cube first."

It is:

- **faceted/composite consumer**

with:

- face geometry
- per-face filters
- per-face LOD
- shared row pool

## 2. Text-Rendered 3D Objects

This is the important conceptual jump.

If a text-theater depiction can inhabit 3D space, then the text theater is not just "describing" the world. It can **emit representations that live inside the world**.

That unlocks:

- text-formed object depictions in web theater
- text windows that visually host rotating ASCII-like object forms
- body-attached text objects for route/contact debugging
- later on-demand object depictions from stored assets or session artifacts

This should still follow the same ownership chain:

- object truth first
- text depiction second

The text depiction is a consumer and a bridge, not the object authority.

## 3. Hybrid Skins

Hybrid skins are a concrete downstream use of the bridge concept.

They are most useful as:

- proc-gen mesh QA
- contact/load visualization
- debug overlays for topology or density
- cross-theater correlation when text and spatial views should obviously match

They should not be the first implementation target.

They depend on:

- a stable object/body contract
- selective object rendering
- clear policy for when the text skin is explanatory versus decorative

## 4. Session-Aware Blackboard Progression

This is the strongest product insight from the discussion.

The blackboard should not merely reflect current state.

It should reflect:

- what the agent is trying to do
- what recently failed
- what is currently pinned or watched
- what the corroboration chain looks like
- what has changed since the last similar view

That means the blackboard is a function of:

- current mechanics truth
- current camera context
- current session/investigation context

Not just:

- whatever metrics happen to exist right now

This is why the blackboard has to be procedural composition, not a fixed template.

## 5. Agent-First Instrumentation

The user is right that the blackboard is primarily for the operating agent.

That changes the bar:

- it must be useful for active reasoning, not just look "diagnostic"
- it must preserve investigative continuity
- it must expose blockers, corroboration, and next-action context
- it must stay legible under live motion and repeated iteration

Operator legibility still matters, but it is secondary to machine utility.

## 6. Telemetry Needs Temporal Traces

Static values are not enough for this system.

The blackboard row contract should allow optional traces:

- short ring-buffer history
- predicted future path
- corroborated actual path

This is useful across multiple consumers:

- text theater:
  - sparkline
  - delta arrows
  - "drifting toward edge" style interpretation
- web theater:
  - fading trails
  - contact/path arcs
  - route previews
- later phase sequencer:
  - planned limb path versus realized limb path

So one row family can support:

- telemetry
- prediction
- corroboration
- telestration

without inventing a separate path object system first.

## 7. Mechanics-Truth "Invisible Man" Mode

The user's "invisible man" instinct is not decorative.

It is a real debugging mode:

- skin hidden or nearly transparent
- scaffold visible
- contact patches visible
- support polygon visible
- CoM marker visible
- balance margin / route slates visible

This should be understood as a formal dev mode:

- product mode
- dev overlay mode
- mechanics-truth mode

The third mode is often the best place for blackboard correlation because it removes visual clutter and leaves only:

- body mechanics truth
- contact truth
- explanatory overlays

## 8. Accessibility Is Already In The Multi-Consumer Architecture

The user asked for handicap-accessible simplicity. That is already implied by the architecture if we take it seriously.

Why:

- text theater is a native accessible consumer
- agent can read the raw row pool directly
- web consumers are progressive visual enhancements, not the only way to access truth
- row text can carry explicit tolerance state, not just hue

So accessibility is not a later separate mode.

It is:

- modality independence
- explicit textual semantics
- non-color-only signaling
- consumer-specific presentation

## Concrete Architectural Read

The clean architecture now looks like this:

```text
mechanics / world / proc-gen truth
  -> shared_state / snapshot truth
    -> shared_state.blackboard (stable row pool)
      -> text theater primary consumer
      -> web theater light consumers
      -> diagnostic cube consumer
      -> CSS2D/CSS3D anchored slates
      -> ASCII/text-object consumers
      -> telestrator overlays
```

Important constraint:

Camera motion may:

- reproject
- rerank
- relayout
- restyle

Camera motion may not:

- rebuild the row pool
- recompute expensive reasoning
- inject heavyweight payloads into the motion path

That is the exact line the reverted blackboard attempt crossed.

## What Is Immediately Buildable

These can be built now without violating the current architecture:

### Slice A: Blackboard Row Contract

Build:

- `shared_state.blackboard`
- `text_theater_snapshot.blackboard`

As stable, cold-path row pools only.

First row families:

- balance
- support / polygon
- contacts
- load distribution
- controller roles
- route report
- session working set

### Slice B: Text-Theater-First Blackboard Consumer

Build a real text-theater blackboard mode/section with:

- Working Set
- Pinned Slate
- Route / Corroboration
- Session Thread
- Tolerance / trend / confidence styling

This should be the first meaningful blackboard consumer.

### Slice C: CSS2D Near-Field Mini-Slates

Use existing `CSS2DRenderer` to attach small blackboard slates to:

- contacts
- active controller
- selected body region
- support polygon / CoM markers

This is cheaper and safer than jumping straight to a full diagnostic cube.

### Slice D: Mechanics-truth mode

Add a clean debugging mode that privileges:

- scaffold
- contact patches
- support polygon
- CoM / balance markers
- blackboard mini-slates

This is a high-value consumer mode even before any cube or ASCII object work.

## What Should Wait

These are valid, but should not happen before the contract and text-theater consumer exist:

- vendoring `CSS3DRenderer`
- full diagnostic cube
- ASCII shader pass
- selective render-to-texture text objects
- hybrid skins
- telestrator overlays
- webcam text rendering

They are consumers. The contract comes first.

## Recommended Build Order

1. Preserve the current parity/freeze fixes and keep them off the hot path
2. Build blackboard Slice A:
   - stable row contract only
3. Build blackboard Slice B:
   - text-theater-first consumer
4. Add CSS2D mini-slates for near-field articulation
5. Add mechanics-truth mode
6. Vendor `CSS3DRenderer`
7. Build a first diagnostic-cube prototype fed from the same row pool
8. Later add selective ASCII/text-object consumers
9. Add a fuller profile/composite-consumer engine only when there are enough consumers to justify it

### Build-order correction

Do not overbuild the profile engine in Slice A.

The stable row contract is necessary immediately.

The full generalized profile engine is not.

For early slices:

- text theater can read the row pool directly
- CSS2D slates can use hardcoded filters
- mechanics mode can use hardcoded family selection

Generalized profile composition becomes worth it when there are multiple competing consumers:

- text theater
- CSS2D slates
- diagnostic cube faces
- ASCII/text-object consumers
- telestrator overlays

That is the point where abstraction starts paying for itself.

## Risks To Avoid

Do not repeat these mistakes:

### 1. Hot-path blackboard generation

No blackboard regeneration on turntable/manual camera pulses.

### 2. Consumer becoming authority

No diagnostic cube, ASCII object, or text skin becomes the source of truth.

### 3. Static dump masquerading as intelligence

More rows is not more utility. Session-aware curation matters more than volume.

### 4. Per-feature bespoke renderers

Do not make every new metric invent its own renderer. Add rows to the contract and let consumers render them.

### 5. Premature consumer-engine abstraction

Do not spend Slice A building a maximal profile engine.

The contract and the first consumers matter more than the perfect orchestration layer.

## Final Read

Opus's synthesis is directionally correct and corroborated by the repo:

- the diagnostic cube is valid
- text-rendered 3D objects are valid
- hybrid skins are valid
- the text theater really is a bridge medium
- the system is much closer to supporting this than it seemed

But the build discipline matters:

- contract first
- text-theater consumer first
- light web consumers second
- mechanics-truth mode early
- heavier mixed-medium experiments after that
- profile engine only when consumer count justifies it

If that order is respected, the diagnostic cube and text-formed spatial objects become natural extensions of the current architecture instead of another detour into parity breakage and renderer drift.
