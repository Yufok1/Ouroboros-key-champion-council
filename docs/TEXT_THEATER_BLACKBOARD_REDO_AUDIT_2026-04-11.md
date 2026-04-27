# Text Theater Blackboard Redo Audit 2026-04-11

Repo: `F:\End-Game\champion_councl`

Purpose:

- explain why the recent thin blackboard attempt failed even before the freeze regression
- ground the next blackboard slice in the current live architecture, not in the reverted experiment
- define a blackboard design that is useful to the agent first, legible to the operator second, and safe for the live motion path

## Bottom Line

The last blackboard attempt failed for two different reasons:

1. **Performance failure**
   - blackboard work was pushed into camera/live motion paths
   - that was architecturally wrong and helped reintroduce the 15-second freeze loop

2. **Product failure**
   - even where it did exist, it did not read as a real blackboard
   - it read like a thin HUD/diagnostics sidecar rather than a spatial, session-aware reasoning surface

The next blackboard slice should therefore be built as:

- a **stable row pool**
- plus a **procedural collation/layout system**
- plus **separate consumers** for text theater and web theater

Not:

- a static metrics panel
- a second truth plane
- a camera-tick data rebuild

## Corroborated Current Architecture

### 1. The web theater is still the live render authority

The browser renders directly from live scene/runtime objects in `static/main.js`.

Important consequence:

- the browser already has the fastest truth for camera motion
- the blackboard must not fight that or duplicate it expensively

### 2. The text theater already behaves like a shared bus / staging ground

Current structure:

- `window.envopsGetSharedState()` builds authoritative browser-side shared state
- `shared_state.text_theater.snapshot` holds a structured text-theater snapshot
- `shared_state.text_theater.theater` and `shared_state.text_theater.embodiment` hold render strings
- `scripts/text_theater.py` consumes that snapshot, merges live camera state, and renders locally

That means the text theater is already not just "terminal fluff."

It is already a **cross-surface interchange format** between:

- live browser scene/runtime
- terminal consult renderer
- `env_read(...)`
- future blackboard consumers

This supports the user's intuition that text theater is a common bus or staging ground.

### 3. The blackboard doctrine already says "structured data first"

`docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md` is still correct about the fundamentals:

- structured data first
- render surface second
- camera-relative spatial collation
- dynamic population
- tolerance/trend/confidence
- dev-mode only
- not a flat 2D HUD

### 4. The current text theater consumer model is still panel-based

Today the text theater primarily exposes:

- theater text
- embodiment text
- diagnostics sections
- consult panels

This is useful, but it is not yet a real blackboard consumer.

It is still closer to:

- renderer
- inspector
- consult panel

than to:

- session-aware reasoning surface
- procedural diagnostic slate system

## Why The Last Blackboard Attempt Failed

## Failure 1: Wrong Placement In The Hot Path

The reverted attempt pushed blackboard work into the live camera path.

That was wrong because the docs already say:

- camera motion should only reproject / rerank / relayout
- state change should trigger heavy row recomputation

Instead, the implementation drifted toward:

- camera pulses carrying extra blackboard payload
- live consumers refreshing blackboard in the same cadence as turntable/manual motion

That violated the architecture directly.

## Failure 2: It Was Functionally Invisible In Text Theater

The user complaint was accurate:

- "the text theater does not have any sort of black board system on it"

Even ignoring the performance regression, the slice did not land as a meaningful text-theater feature.

Why:

1. It was too secondary.
   - It existed as an extra pane / HUD-like addition.
   - It did not become a first-class articulation of the text theater.

2. It was not body-adjacent in spirit.
   - The current text theater gives whole-body read first.
   - The attempted blackboard did not clearly extend that; it looked like more data, not better reasoning.

3. It had no meaningful session continuity.
   - Rows reflected current metrics, but not what the user/agent had been doing.
   - It did not tell a story of progression, blocked maneuvers, repeated failures, or current investigative thread.

4. It did not feel curated.
   - A row set can be technically correct and still feel like noise.
   - The attempt did not yet have enough admission, grouping, persistence, or hierarchy to read as usable instrumentation.

## Failure 3: It Treated "More Data" As Equivalent To "More Utility"

That assumption is false for this system.

What the user is actually asking for is not:

- more values
- more panels
- more alarms

It is:

- more **usable progression**
- more **correlation**
- more **context continuity**
- more **coordination across theaters**

This means the blackboard cannot just be a measurement dump.

It must be a **procedural utility surface**.

## The Correct Read: Blackboard Is A Procedural Composition System

The user's instinct here is right:

- the blackboard should behave like a form of procedural generation
- or a sequencing/composition system

That does not mean "randomly generate UI."

It means:

- take a stable row pool
- apply camera context
- apply session context
- apply current operator/agent task
- apply continuity rules
- produce a readable reasoning surface

So the blackboard is best understood as:

**a procedural collation and articulation system over stable mechanics truth**

Not:

**a static diagnostics template**

## What The Blackboard Should Actually Be

## 1. Stable Row Pool

Produced only on meaningful state changes:

- pose change
- contact/support change
- controller change
- route report update
- load/balance change
- prediction/corroboration update
- explicit session pin/unpin

Each row should have stable identity:

- `id`
- `family`
- `anchor`
- `layer`
- `source`
- `label`
- `value`
- `unit`
- `tolerance_state`
- `confidence`
- `trend`
- `priority`
- `group_key`
- `sticky_ms`
- `session_weight`

## 2. Procedural Collation Layer

Runs on camera/view changes and session-context changes.

It should:

- promote rows near the current focus
- promote rows relevant to the active maneuver/controller
- preserve recently important rows long enough to stay understandable
- demote irrelevant rows without deleting them immediately
- avoid row-jump chaos

This is where the "same view on second rotation should not be identical if the session changed" idea belongs.

The view should be affected by:

- camera
- current state
- recent interactions
- current active investigation

Not by raw chaos.

## 3. Session-Aware Progression

This is the missing ingredient.

The blackboard should know something about what the agent/operator has been doing recently.

Minimum session-aware inputs:

- last command/tool that changed mechanics
- current active controller / route / macro
- recent route blockers
- recent corroboration mismatches
- pinned rows or pinned families
- repeated failure counts
- currently watched joint/contact/manifold

That gives the board continuity.

Without this, it becomes a stateless meter wall.

## 4. Consumer-Specific Articulation

Same rows, different consumer behavior.

### Text theater consumer

Should be:

- the primary blackboard consumer
- compact, grouped, and sequenced
- clearly separated from current theater/embodiment views
- capable of showing:
  - current working set
  - pinned slate
  - route/corroboration chain
  - active anomaly family

### Web theater consumer

Should be:

- lighter
- body-adjacent
- leader-line/slate based
- camera-facing
- not a giant HUD pasted over everything

This is where later mixed-medium ideas fit:

- text slates
- floating row groups
- camera-facing text windows
- text-rendered procedural objects

But those are consumers, not the blackboard authority.

## 5. The Text Theater As Bridge Medium

The user intuition here is worth preserving explicitly:

- text theater is not only a terminal representation
- it can act as a bridge between chat, 3D, graphing, and future mixed-media rendering

That means later features like:

- camera-facing text windows in the 3D view
- text-rendered procedural entities
- graph/slate overlays
- even webcam-derived text abstractions

can all sit on top of the same textual/spatial contract

if the contract remains authoritative and composable.

So yes:

**the text theater is a bridge medium**

But only if its data model stays canonical and reusable.

## Why The Data Must Be Tailored

The user's warning is correct:

> if we let the recalculation own everything, just without any tailoring, its going to be chaos and confusion only

That is exactly right.

The blackboard needs:

- admission rules
- grouping rules
- persistence rules
- hysteresis
- session weighting
- progression memory

Otherwise it will technically work and still be useless.

## Recommended Redo Architecture

## Slice A: Row Contract Only

Build `shared_state.blackboard` and `text_theater_snapshot.blackboard` as stable structured row pools.

Do this:

- only in full shared-state / full snapshot builds
- never in continuous camera pulse payloads

Do not do this:

- any web HUD
- any camera pulse recompute
- any browser hot-path blackboard regeneration

## Slice B: Text Theater First-Class Blackboard Mode

Add a real text-theater blackboard consumer.

Not a side pane only.

It should have:

- `Working Set`
- `Pinned Slate`
- `Route / Corroboration`
- `Mechanics`
- `Session Thread`

This gives the board procedural continuity and makes it feel like a real instrument.

## Slice C: Web Theater Light Slate Consumer

After text mode is useful:

- a very light body-adjacent slate consumer in the web theater
- only on full shared-state refreshes
- camera motion may reposition existing slates locally, but should not regenerate the row pool

## Slice D: Session Threading

Add explicit session memory inputs to blackboard collation:

- current investigative thread
- recent blockers
- recent predictions/corroborations
- pinned rows
- repeated issues

This is what turns it from diagnostics into utility.

## Slice E: Mixed-Medium Text Slates Later

Only after the row pool and text consumer are solid:

- camera-facing text windows/slates in 3D
- text-rendered procedural objects
- graph overlays derived from blackboard rows

Those are downstream visual experiments, not the first step.

## Color / Tone Guidance

Color should not do one job. It should encode multiple related meanings cleanly.

Recommended mapping:

- hue = tolerance state
  - green = within
  - yellow = watch
  - orange = degraded
  - red = critical
  - blue/gray = informational/contextual
- saturation = confidence / certainty
- brightness = importance / current prominence

Source/layer should be encoded separately, not by hue alone:

- `MEAS`
- `DERV`
- `INTP`
- `PRED`
- `CORB`

This avoids turning the board into an alarm Christmas tree.

## Why This Fits The Current Repo

This design is compatible with current code because:

1. The shared contract already exists.
2. The text-theater snapshot already carries most of the relevant truth.
3. The text theater already renders locally from snapshot.
4. The performance doctrine already distinguishes state recompute from camera reproject.
5. The workbench/mechanics stack already exports route, balance, contact, and controller truth in blackboard-shaped form.

So the redo is not a new invention.

It is a stricter application of the architecture that the repo already documents.

## Final Recommendation

Do not redo blackboard as:

- another metrics HUD
- another camera-hot-path feature
- another diagnostics dump

Redo it as:

- stable row pool
- procedural collation system
- session-aware utility surface
- text-theater-first consumer
- web-slate-second consumer

That is the version most likely to be:

- useful to the agent
- readable to the operator
- extensible to mixed media later
- safe for parity/performance
