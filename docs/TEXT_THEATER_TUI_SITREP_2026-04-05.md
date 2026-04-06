# Text Theater TUI Sitrep 2026-04-05

Repo: `F:\End-Game\champion_councl`

Scope:

- repo-local text-based theater diagnostics and interaction surface
- why this direction emerged from the recent env/balance/settle work
- what the system must show
- what already exists in source that can feed it
- the right implementation trajectory before any broader package extraction

## Core Conclusion

The project now needs a terminal-native theater surface.

Not as a novelty ASCII toy.

As a paired diagnostic and interaction instrument that lets an agent and operator:

- see the current theater view without relying only on JPG captures
- inspect builder/scaffold/batch-pose state in a text-native workspace
- observe motion, settle, and balance state with faster feedback than the current mirror/capture loop
- switch between full-scene theater context and isolated embodiment/part-chain context

The recent balance/settle lane made this need explicit.

The current browser theater is still the visual truth surface.

But the project now has enough structured state that it should also have a text-native scene surface:

- scene
- camera
- focus
- builder skeleton
- scaffold
- motion timeline
- settle preview
- support/load truth
- replay/trajectory state

If done well, this becomes:

- a live diagnostics menu for the project itself
- a better agent-operable observation plane
- a future standalone package candidate for terminal-native scene rendering and semantic visualization

## Why This Emerged Now

This direction did not come out of nowhere.

It is the convergence of several recent lanes:

### 1. Environment Help Was Needed Because Runtime Truth Was Hard To Reconstruct

The repo-local `env_help` subsystem exists because agents kept rediscovering command and browser-surface seams.

That system now captures:

- command truth
- browser-local control truth
- payload gotchas
- verification paths

The text-theater idea is the same kind of move, but for spatial/motion truth instead of command truth.

### 2. Ground Interaction Matured Into A Balance System

The current embodiment lane already computes:

- support polygon
- projected center of mass
- stability margin
- dominant support side
- per-segment load/support scores
- alerts and contact states

So the workbench is no longer only posing a model.

It is already producing enough structured balance state to support a richer observation surface.

### 3. Settle Became A Real Generated Motion Surface

The builder lane now has visible settle preview/commit behavior driven by balance truth.

That means there is now meaningful generated motion that should be inspectable without waiting only on probe/time-strip captures.

### 4. Mirror / Bundle / Timing Seams Exposed The Need For A Better Operator Surface

The recent debugging work proved several practical issues:

- stale browser bundle can make source and runtime diverge
- ingress/live-sync mirror can lag after command dispatch
- shared-state reads can lie for a few seconds
- captures remain authoritative but are not the fastest way to reason

A text-native paired view gives agents a second operational surface:

- faster than waiting for image artifacts every time
- more structured than guessing from logs
- still tied to live runtime truth

## The User Goal

The user goal is stronger than "ASCII charts."

The desired system should let an agent:

- look at a text-native depiction of what the theater is currently showing
- use it from chat/workspace as a readily inspectable surface
- switch between full environment theater and isolated embodiment/part-chain views
- understand animation sequencing, batch pose effects, scaffold motion, and camera orientation

And ideally the same system should let the operator:

- keep a separate terminal/TUI diagnostics surface open
- inspect the same live scene state
- interact with it
- later pan/orbit/select/drag from the TUI and have it stay paired with the live theater

That means the target is not:

- a one-off ASCII dude
- a screenshot-to-ASCII novelty
- a humanoid-only debug toy

The target is:

- terminal-native theater rendering
- interactive when possible
- morphology-aware
- semantically paired with the live browser theater

## What The System Must Show

There are at least two primary render modes that must exist from the beginning.

### 1. Full Theater / Environment View

This is the world/theater scene view.

It should show:

- scene objects / facilities
- camera framing and orientation
- focus target
- theater mode / visual mode
- world surfaces / major stage extents
- replay / trajectory context when active
- live character presence inside the scene

This is the text-native counterpart to the environment theater.

### 2. Embodiment / Isolated Chain View

This is the forge/workbench embodiment view.

It should show:

- current builder pose
- selected bones / isolated chains
- scaffold structure
- batch pose changes
- settle preview state
- support/contact/load/balance overlays

This is the text-native counterpart to the character forge / isolated part-chain surfaces.

### 3. Motion / Sequencing View

This does not need to be day-one complete, but the project is already pointing here.

It should eventually show:

- moving miniature body or motion proxy
- root path / trajectory
- ghost checkpoints
- timeline or frame markers
- settle-generated micro-timelines
- support-phase and stability shifts over time

This is the kinetic counterpart to the archive and balance lanes.

## What Already Exists In Source

The project already contains most of the truth sources this system needs.

### Environment / Theater Truth

The environment lane already has:

- theater vision / observer capture system
- scene object semantics
- focus and camera state
- world/grid/stage information

Relevant reference docs:

- [THEATER_VISION_SYSTEM.md](/F:/End-Game/champion_councl/docs/THEATER_VISION_SYSTEM.md)
- [ENVIRONMENT_MEMORY_INDEX.md](/F:/End-Game/champion_councl/docs/ENVIRONMENT_MEMORY_INDEX.md)

### Builder / Embodiment Truth

The builder lane already has:

- live bone records
- scaffold slots and structure
- pose store
- timeline / key poses
- isolated chains
- part-surface views

### Balance / Load / Contact Truth

The balance lane already has:

- `supportingFeet`
- `projected_center_of_mass`
- `support_polygon`
- `stability_margin`
- `inside_support_polygon`
- `dominant_support_side`
- segment load/support scores
- alerts / contact states

This is enough to drive a first text-native balance view now, even before the level widget or voxel substrate exists.

### Motion / Replay / Trajectory Truth

The theater already has:

- replay rail
- trajectory monitor
- branch yard

Those are strong source anchors for later motion-sequencing views.

### Command / Runtime Truth

The `env_help` system now captures the command contracts and gotchas for the exact surfaces the TUI will need to operate:

- pose commands
- settle preview/commit
- capture commands
- workbench timeline commands
- browser-local helper controls

That means the terminal view can stay paired with the live runtime without inventing a second command model.

## What Is Still Missing

Several important supporting surfaces are still not built.

### Carpenter / Level Instrument

This is still planned, not live.

The text-theater should not pretend it already exists.

But the same balance truth that will drive the carpenter-level can already feed textual balance renderings.

### Voxel / Substrate Load Depiction

The inner body-part substrate depiction is still ahead of us.

The text-theater should start from the existing balance/load signals rather than waiting on the final substrate renderer.

### Generic Contact Solver

The solver is still feet-first:

- `supportingFeet`

Not yet generic:

- `supportingContacts`

So the first text-native balance view should be honest about that.

It can show hands/knees/head as contact candidates or observed contacts, but should not overclaim full multi-contact support redistribution yet.

## The Right Shape

This system should be designed in layers.

### 1. Canonical Runtime Snapshot

The TUI should not scrape text from random browser DOM or depend on screenshots.

It should consume structured runtime state:

- scene/camera/focus snapshot
- builder/workbench surface
- bone transforms
- scaffold state
- balance/load/contact snapshot
- replay/trajectory snapshot

This should become the canonical text-theater input model.

### 2. Projection Modes

The renderer should support several projection families:

- world/theater projection
- embodiment projection
- orthographic chain projection
- motion/trajectory projection

The user explicitly wants the system to be able to describe and render not just the character, but the whole theater as well.

### 3. Glyph Rendering

The renderer should not lock itself to plain ASCII only.

It should support:

- ASCII fallback
- block elements
- quadrant blocks
- braille/high-density dot glyphs

The terminal is still a character grid, but Unicode glyph density gives much better usable resolution than plain ASCII sticks alone.

### 4. Semantic Paragraph View

This is one of the strongest ideas in the current direction.

The same scene should be renderable as:

- a glyph scene
- a structured summary
- a compact paragraph

For example:

- "Render your graphing systems and 3D grid depictions into a simple paragraph on a text output."

That should be treated as a first-class output mode, not an afterthought.

### 5. Interactive TUI Layer

The longer-term goal is not read-only text.

The desired system should eventually allow:

- focus/select
- inspect
- mode switching
- timeline scrub
- maybe pan/orbit/drag through text-side controls

If the TUI becomes interactive, it must stay paired with the same browser/runtime truth instead of becoming a parallel universe.

## Important Design Doctrine

### It Must Not Become A Second Renderer With Different Truth

The text-theater is a paired observation/control surface.

It must not invent its own scene model or drift away from the live theater.

### It Must Be Morphology-Aware

The user intends future bodies with:

- extra arms
- quadrupeds
- spiders
- snakes
- other non-biped forms

So the textual embodiment layer should derive from bone graph / scaffold topology, not from a hardcoded little humanoid.

### It Must Support Full 3D Orientation, Not Just Forward/Back

Recent settle work reinforced this point.

The user explicitly does not want a sagittal-only fake 3D system.

The text-theater must eventually respect:

- lateral lean
- sagittal lean
- heading / orientation
- camera rotation
- diagonal movement intention

### It Should Separate Archive, Motion, And Truth

The recent design conversation produced a good split:

- archive / fractal quadrant = what the sequence became
- motion quadrant = how it moved
- balance/level truth = why it destabilized

The text-theater should preserve that conceptual separation instead of making one overloaded panel do everything badly.

## Fractal Quadrant Relationship

The new "fractal quadrant" name is useful.

The underlying idea is a synthesis of earlier threads:

- flat rack / reference slots
- replay/trajectory sequencing
- part work-cell
- motion diagnostics

The clean recursion is:

- `1`
- `4`
- `16`
- `64`

Not the awkward rectangular jump.

That archive concept should remain part of the broader text-theater design, but it does not need to be the first implementation slice.

## Recommended Implementation Order

### Phase 1: Static Text-Theater Snapshot

Build a repo-local renderer that can output a paired textual snapshot of:

- full theater view
- embodiment/isolated chain view

from live structured state.

No full interactivity yet.

The first win is:

- the agent can inspect the live scene/workbench in text form
- the operator can see the same thing in a terminal window

### Phase 2: Pose / Balance Diagnostic Render

Add text-native embodiment overlays for:

- selected bones / chains
- support/contact state
- projected CoM
- settle preview summary
- timeline cursor / frame context

This gives the current balance/settle lane the text-native partner it needs.

### Phase 3: Motion / Sequencing Surface

Add:

- motion checkpoint projections
- trajectory ghosts
- timeline/archive links
- early fractal quadrant memory

### Phase 4: Interactive TUI

Add:

- focus/select
- scrub
- mode toggles
- maybe command triggers / links

Do not attempt full drag/orbit parity before the snapshot/render truth is stable.

### Phase 5: Package Extraction Candidate

Only after the repo-local tool proves itself should this be considered for extraction into a broader package.

Potential package framing:

- terminal-native scene rendering
- graph / grid / skeleton / topology depiction
- semantic paragraph rendering of structured scenes
- interactive glyph UI

## What To Tell Opus

The important handoff is:

- this is not a random side quest
- it emerged directly from env-help, balance, settle, and observation pain
- it should be treated as a real diagnostics/instrumentation surface
- repo-local first, package later

Opus should evaluate:

1. Is the layered architecture right?
2. What should the canonical runtime snapshot contract be?
3. What is the smallest honest Phase 1 text-theater output?
4. Which existing surfaces should feed it first?
5. How should archive/motion/truth views be separated?
6. What interaction model belongs in the TUI without overbuilding it?

## Immediate Next Move

The best next implementation step is not broad package design.

It is:

1. define a canonical text-theater snapshot payload from current runtime truth
2. implement a first paired text render for:
   - full theater view
   - embodiment/isolated chain view
3. keep it live, repo-local, and diagnostic-first

That gives the project a usable instrument immediately while leaving room for the larger terminal-native scene engine later.
