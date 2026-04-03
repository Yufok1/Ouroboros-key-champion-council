# Ghost Broadcast Screen Surface Parallel Track

Status: Parallel design track
Date: 2026-04-02
Scope: Environment-scene concept, in-world HTML screen surfaces, bilateral theater handoff, and Opus alignment

## Purpose

Define the parallel scene track we will return to after the current procedural generation and Coquina body-authoring push.

This track has two linked goals:

1. Build the `Ghost Broadcast` environment-scene concept as a first-class environment product.
2. Add a real in-world screen-surface system so environment objects can behave like monitors, TVs, kiosks, billboards, phone screens, wall displays, and storefront panels carrying HTML content.

This is not a replacement for the current environment runtime. It is a planned extension of the existing environment object, HTML panel, owned-surface bridge, workstation, and facility systems.

## Non-Negotiable Truths

### 1. Environment work belongs in the environment theater

World composition, districts, props, signage, display surfaces, kiosks, scenic storytelling, and scene layout belong to the environment theater.

The character workbench is the adjacent forge for:

- rigging
- scaffold work
- pose authoring
- clip authoring
- embodiment inspection

It is not the place to build a reef, a city, a junkyard, or a broadcast district.

### 2. Screen surfaces are environment objects

A screen is not a separate mode and not a hidden debug trick. It is an environment-side object or facility surface.

The canonical substrate already exists:

- scene objects can carry `html`
- objects already open through the HTML panel system
- owned-surface bridging already supports:
  - `open_surface`
  - `surface_action`
  - `surface_click`
  - `surface_input`
  - `surface_submit`
- workstations/control units already define environment-side HTML interfaces

The new work is to make those surfaces spatial and scenic, not just sidebar panels.

### 3. Theater handoff must stay explicit and bilateral

The environment shell should visibly point to the character forge when embodiment work is the right next move.

The character forge should visibly point back to the environment shell when world composition is the right next move.

Planned labels:

- `Descend to Forge`
- `Return to Broadcast`

## Core Scene Concept

### Name

`Ghost Broadcast`

### Thesis

A drowned production city where nothing was deleted, only abandoned.

Every workflow still echoes somewhere.
Every memory is a relic.
Every tool is a dead storefront still glowing.

This is not a Twitch-branded room. It is a larger culture-space where broadcast, memory, workflow, archives, failure, and embodiment all share one visual language.

### Visual Language

- drowned studio district
- reef growth through industrial junk
- old retail/media debris as sacred infrastructure
- CRT glass, oxidized steel, anodized red, algae green, phosphor cyan, hazard amber
- shrine-like consumer relics:
  - soda cans
  - vending machines
  - shopping carts
  - broadcast cameras
  - server racks
  - tires
  - coolers
  - cassette/tape crates

## District Plan

### 1. Ingress Delta

Role:
- live ingress
- chat/current/event flow
- intake routing

Visuals:
- glowing channel markers
- suspended signal buoys
- pipe mouths
- cable runs
- wet concrete and algae-lit gates

### 2. Memory Catacombs

Role:
- archives
- saved runs
- artifacts
- product records
- operator memory relics

Visuals:
- vending-machine reliquaries
- can shrines
- tape shelves
- bottle crates
- coolant lockers

### 3. Replay Aquarium

Role:
- looping traces
- replay branches
- preserved historic states

Visuals:
- glass tanks
- submerged theater tunnels
- looping silhouettes
- phosphor ribbons

### 4. Tool Arcade

Role:
- tool access
- workstation bays
- control units
- plugin or model kiosks

Visuals:
- cracked arcade cabinets
- terminal islands
- lit booth faces
- hanging display boards

### 5. Moderation Breakwater

Role:
- safety
- filters
- gates
- review chokepoints

Visuals:
- sirens
- guard towers
- floodgate doors
- speaker horns

### 6. Failure Sink

Role:
- failed runs
- broken dependencies
- dead lights
- blocked transitions

Visuals:
- oil-dark pools
- dropped signage
- burned monitors
- collapsed walkways

### 7. Forge Below

Role:
- character workbench counterpart
- rigging
- scaffold inspection
- pose/clip authoring

Visuals:
- anatomical lift tables
- scaffold gantries
- cable spines
- hanging lamps
- repair rigs

The default character-side companion for this scene should be a scaffolded caretaker build:

- visible head
- visible hands
- visible feet
- exposed rig/scaffold body between them

That keeps the character product visually tied to the ruin-city without confusing character authorship with environment composition.

## Screen Surface System

### Goal

Any scene object that wants to behave like a display should be able to present HTML content as a first-class world surface.

Examples:

- phone screen
- desk monitor
- CRT television
- vending-machine display
- subway-style info board
- hanging billboard
- drive-thru sign
- storefront window panel
- giant broadcast wall

## Architectural Rule

Do not invent a separate screen renderer if the existing environment HTML and owned-surface lane can be extended.

The correct ladder is:

1. environment object contract
2. HTML panel / owned surface contract
3. in-world display projection
4. optional interactive bridge routing

Not:

1. invent unrelated webview runtime
2. duplicate object semantics
3. bolt it back on later

## Screen Classes

### 1. Micro

- phone
- pager
- badge
- wrist module

Primary use:
- local props
- character-adjacent screens
- notification/status surfaces

### 2. Personal

- desk monitor
- kiosk screen
- control terminal
- vending display

Primary use:
- workstation/control unit surfaces
- read/write panels
- interaction surfaces

### 3. Architectural

- wall TV
- station board
- storefront panel
- hanging sign

Primary use:
- district identity
- environmental storytelling
- read-only public surfaces

### 4. Monumental

- billboard
- plaza broadcast wall
- aquarium projection panel
- skyline sign

Primary use:
- scene-wide semantic anchor
- district status
- atmosphere and identity

## Content Modes

### A. Owned HTML

Source:
- object `html`
- `srcdoc`
- generated workstation template

Use when:
- content is authored in-project
- interaction needs shell-to-surface bridge
- deterministic behavior matters

### B. Wrapped Surface Template

Source:
- runtime-generated HTML from workstation/facility template

Use when:
- the screen is a real operational console
- content should reflect live state
- operator or agent interaction matters

### C. External URL / iframe

Source:
- explicit URL

Use when:
- the source allows embedding
- licensing and framing permissions are valid
- the surface is primarily scenic or operator-facing

Constraint:

Many third-party sites will not allow iframe embedding due to CSP/X-Frame-Options or product policy. This mode is opportunistic, not guaranteed.

### D. Media Proxy or Curated Capture

Source:
- locally curated HTML page
- captured or reformatted media surface

Use when:
- a public site cannot be directly embedded
- the goal is a themed scenic surface rather than arbitrary full browsing

## Interaction Modes

### 1. Passive Display

Read-only world screen.

Examples:
- animated billboard
- archive label wall
- public departures board

### 2. Click-to-Open Surface

The in-world object acts as a scenic shell, but interaction opens the existing HTML panel system for detailed use.

Examples:
- CRT monitor in the world opens a sidebar terminal
- billboard opens a detailed replay board

### 3. Direct Surface Bridge

The screen itself is a live owned surface target, not just a scenic shell.

Examples:
- workstation screen with tabs/forms
- in-world terminal the agent or operator can actually drive

This is the most powerful mode and should be used sparingly at first.

## Proposed Object Contract Additions

These fields should extend the environment object contract rather than creating a parallel model.

```js
{
  kind: 'panel',
  id: 'replay-wall-01',
  label: 'Replay Wall',
  semantics: {
    role: 'display',
    district: 'replay_aquarium',
    placement_intent: 'broadcast_surface'
  },
  panelMode: 'sidebar',
  html: '<div>...</div>',
  display_surface: {
    screen_class: 'architectural',
    content_mode: 'owned_html',
    interaction_mode: 'click_to_open_surface',
    aspect_ratio: '16:9',
    emissive_strength: 1.2,
    auto_refresh_ms: 1000,
    world_mount: 'wall',
    preview_policy: 'live',
    audio_mode: 'muted',
    bridge_enabled: true
  }
}
```

Suggested normalized fields:

- `display_surface.screen_class`
- `display_surface.content_mode`
- `display_surface.interaction_mode`
- `display_surface.aspect_ratio`
- `display_surface.emissive_strength`
- `display_surface.auto_refresh_ms`
- `display_surface.world_mount`
- `display_surface.preview_policy`
- `display_surface.bridge_enabled`

## Rendering Ladder

### Phase 1

The object exists in-world and opens the existing HTML panel on interaction.

This is already close to current truth and should be the first real ship target.

### Phase 2

The object also shows a live or periodically refreshed world-space preview on its mesh.

This makes monitors, kiosks, and billboards feel spatially real without requiring full arbitrary browsing everywhere.

### Phase 3

Selected screen classes support direct surface bridging from the world object itself.

This is where a terminal, kiosk, or workstation can be treated as a live scene-embedded application surface.

## Ghost Broadcast Object Families

### Relic Displays

- CRT cairns
- tube TVs
- cracked control monitors
- dashboard clusters

### Civic Broadcast Surfaces

- transit boards
- reef warning signs
- moderation siren walls
- replay memorial boards

### Retail/Consumer Surfaces

- vending machine displays
- cooler-door adverts
- abandoned storefront windows
- soda shrine labels

### Industrial Surfaces

- dockside info panels
- crane control monitors
- salvage bay terminals
- breaker-room schematics

## Bilateral Theater Utility

The scene should reinforce the two-product doctrine in the shell itself.

### Environment shell should say

- this is where world composition happens
- this is where screens, props, districts, utilities, and control units belong
- if the operator wants to change embodiment, pose, scaffold, or clip behavior, the shell should offer `Descend to Forge`

### Character shell should say

- this is where embodiment work happens
- this is where rig, scaffold, pose, and clip operations belong
- if the operator wants to build districts, props, screens, or workstation ecology, the shell should offer `Return to Broadcast`

## Implementation Plan

### Phase A — Documentation and Schema Alignment

Deliverables:

- this doc
- environment memory index link
- short memory handoff
- object contract proposal for `display_surface`

Outcome:

The work is named, scoped, and recoverable after compression.

### Phase B — Thin Screen Surface Proof

Goal:

Make environment objects behave as scenic screens using existing HTML/owned-surface infrastructure.

Deliverables:

- one object contract for screens
- one scenic preview path
- one click-to-open detailed panel path

Proof objects:

- `memory-can-wall`
- `tool-arcade-kiosk`
- `replay-wall`

### Phase C — Interactive Screen Surfaces

Goal:

Promote selected world screens into real operational surfaces.

Deliverables:

- direct bridge-capable terminal screens
- kiosk template
- replay board template
- moderation board template

### Phase D — Ghost Broadcast Environment Assembly

Goal:

Compose the first authored Ghost Broadcast scene before full proceduralization.

Deliverables:

- district zones
- anchor props
- screen distribution by district
- forge entrance
- first scenic lighting and palette pass

### Phase E — Coquina / Procedural Integration

Goal:

Make Ghost Broadcast generatable instead of purely hand-authored.

Dependencies:

- Coquina atoms
- district grammar
- affix grammar
- palette resolver
- observer audit loop

Procedural targets:

- tire fields
- cable nests
- monitor cairns
- vending reliquaries
- sign clusters
- dock/breakwater modules

### Phase F — Product and Evaluation Layer

Goal:

Make the scene shippable and measurable.

Deliverables:

- observer capture pass for each district
- screen readability checks
- theater handoff validation
- mounted character fit checks
- scene bundle recipe

## Constraints and Risks

### 1. Arbitrary web embedding is not universally possible

Some sites will refuse embedding. The system should support:

- local HTML
- owned HTML
- template-generated HTML
- embed-allowed URLs
- curated fallback pages

### 2. A live in-world web browser is not the first milestone

The first milestone is meaningful spatial screens, not a general-purpose browser texture system.

### 3. Screen surfaces must not fork the object model

They must remain normal environment objects with extensions.

### 4. Ghost Broadcast must remain theme-neutral at the architecture level

The scene is a content family, not a new engine ontology.

## Validation Plan

When execution resumes on this track:

1. enter environment theater
2. confirm adjacent-theater utility is visible
3. spawn one thin proof screen of each class:
   - kiosk
   - wall monitor
   - billboard
4. verify click opens the correct panel/surface
5. verify one bridge-enabled screen accepts:
   - `surface_click`
   - `surface_input`
   - `surface_submit`
6. build one district fragment
7. descend to forge
8. confirm the character-side scaffolded caretaker reads as the same world
9. return to broadcast
10. observer-capture the result

## Deferred Execution Rule

This track is real and should remain documented, but active implementation is intentionally deferred until the current procedural generation and Coquina lanes are in a better place.

That means:

- keep the plan warm
- do not let it drift into a disconnected fantasy spec
- return once Coquina and procedural world grammar can support it materially

## Opus Handoff Packet

Use this as the standing brief for Opus or any future strategic pass:

### Mission

Advance `Ghost Broadcast` as the next major authored/procedural environment family, with in-world HTML screen surfaces treated as real environment-side facilities rather than mere overlays.

### Architectural requirements

- preserve two-product doctrine:
  - environment world work in environment theater
  - embodiment work in character forge
- extend the existing object contract
- reuse the HTML panel and owned-surface bridge
- make theater handoff explicit and bilateral
- keep Coquina compatibility from the beginning

### Content goals

- drowned broadcast-city
- memory as consumer relic
- workflow as civic infrastructure
- tool ecology as arcade/workstation culture
- forge below as scaffold/embodiment counterpart

### First implementation targets

- thin screen-surface proof
- three district anchors
- one forge entrance
- one scaffolded caretaker character counterpart

### Success condition

An operator can stand in the environment theater, see Ghost Broadcast as a coherent world, interact with real scene-embedded screens, then swap into the character forge without confusion about what each theater is for.

## Bottom Line

This track should become the next strong environment family after the current Coquina/procedural push:

- `Ghost Broadcast` as the world
- screen surfaces as real environment objects
- the forge as the adjacent embodiment space
- one bilateral theater, with the right work happening on the right side
