# Runtime and Product Delivery Matrix

Status: Draft
Date: 2026-03-25
Scope: Complete shipping and runtime combinations for environment products, character products, mounted live deliveries, utilities, and capsule-backed variants

## Purpose

Answer the practical production questions:

- what a runtime is made of
- what belongs to the character product
- what belongs to the environment product
- what ships in capsule-free, capsule-optional, and capsule-required forms
- when the capsule must ship
- what utilities, workstations, and interactive environment features require

This document is the packaging and delivery matrix that sits between the product manifest spec and the production pipeline map.

## Core Model

Champion Council has two base product classes:

1. environment product
2. character product

The character product carries its own runtime facility.

The live experience comes from mounting:

```text
environment product + character product(with runtime facility)
```

The mount occurs through an integration contract.

The capsule is one way to host the runtime facility and environment facilities. It is not required for every product variation.

## What a Runtime Is Made Of

A runtime may include some or all of the following layers.

### A. Character Runtime Facility

Belongs to the character product.

Potential contents:

- embodiment state
- pose and facing state
- command surface
- perception surface
- memory surface
- capability grant state
- activity history
- speech/interaction bindings
- runtime handlers for verbs like `move_to`, `look_at`, `inspect`, `interact`, `stop`, `speak`

### B. Environment Runtime Facilities

Belong to the environment product or to the host environment.

Potential contents:

- support surfaces
- blockers
- portals
- landmarks
- utility objects
- workstations / control units
- fabrication surfaces
- containers / storage
- transport / traversal objects
- interface objects
- environment mirror/shared state
- environment workflows
- environment facility blueprints

### C. Integration / Mount Layer

The seam between the two products.

Potential contents:

- mount point / spawn policy
- support and grounding policies
- utility/workstation discovery
- interaction reach/proximity rules
- command routing to runtime handlers
- environment-to-character state bridge
- character-to-environment action bridge

### D. Host Runtime Shell

The execution shell that runs the mounted product.

Two host runtime variants exist:

#### D1. Browser Theater Shell (current)

- `server.py`
- `static/`
- launch scripts
- packaging shell
- environment capture loader
- command facade
- OpenAPI and adapter layers

#### D2. Desktop Companion Shell (planned)

- Electron main process
- Three.js renderer (transparent window, alpha channel)
- Desktop physics engine (window collision, gravity, surface detection)
- Desktop perception surface (window awareness, cursor tracking, app classification)
- System tray + chat popover
- Speech bubble / text overlay
- Click-through hit-testing (interactive on character pixels, transparent elsewhere)

Both shells mount the same character product through the same mount contract. The character runtime facility is shell-agnostic.

### E. Capsule Facilities

Optional, but required for richer live products.

Potential contents:

- `capsule/capsule.gz`
- council slots
- FelixBag memory
- workflows
- MCP tools
- provenance and persistence
- activity log
- workflow history
- provider bindings

## Product Classes

### 1. Environment Product

Ships scene/substrate content and environment-side facilities.

Can include:

- scene objects
- support/blocker/portal semantics
- utility and workstation objects
- HTML templates for control units
- workflow bindings
- environment manifest
- standalone viewer or interface shell

### 2. Character Product

Ships embodiment plus its runtime facility.

Can include:

- `.glb`
- optional `.vrm`
- optional `.usd` / `.usdz`
- optional `.fbx`
- textures and material metadata
- embodiment metadata
- clip index
- attachment map
- root/origin/scale policy
- command surface metadata
- perception/runtime metadata
- character manifest

### 3. Mounted Live Product

The result of mounting a character product into an environment product.

Can include:

- mounted pose and runtime state
- command and perception surfaces
- utility/workstation interaction
- live mirror
- environment capture
- hosted service shell

This is a delivery form, not a separate base product class.

## Brain Source Variations

Mounted characters do not all need the same cognition source.

### A. Husk / Uninhabited Character

Includes:

- embodiment package
- runtime metadata if mount-ready
- no live cognition source

Use when:

- the buyer wants a controllable shell
- the host system will drive state directly
- the product is meant for downstream simulation or game integration

Capsule required:

- no

### B. Single-Model Character

Includes:

- character product
- one configured model source
- provider or local-host configuration
- runtime handlers that bind prompts/commands to the character runtime

Use when:

- one model is enough
- the buyer wants a simpler inhabited product
- the product is hosted by a compatible runtime shell without needing full council orchestration

Capsule required:

- not necessarily

Requires:

- a compatible runtime host
- a compliant provider bridge or local model host

### C. Capsule-Backed Character

Includes:

- character product
- runtime shell
- capsule-backed memory, tools, workflows, and orchestration

Use when:

- the product needs tool use
- the product needs workflow execution
- the product needs memory continuity
- the product needs council-slot or multi-surface cognition

Capsule required:

- yes, shipped or hosted-equivalent

### Provider Bridge Rule

Do not hard-code the product architecture to any one retail subscription plan.

Design for provider bridges and model hosts instead:

- local HuggingFace-hosted model
- cloud inference provider
- self-hosted OpenAI-compatible endpoint
- capsule council slot

If a user wants to supply their own external model source, the product should consume it through a provider/config contract rather than assuming one specific vendor plan.

## Shipping Modes

### Capsule-Free

No live runtime required by the buyer.

Typical inclusions:

- models
- scenes
- textures
- materials
- manifests
- metadata sidecars
- previews
- static viewer bundles

What does not ship:

- live council/capsule execution
- live memory
- live workflows
- live agent command handling

Examples:

- standalone character model pack
- standalone environment pack
- static world viewer
- metadata recipe pack

### Capsule-Optional

Content works standalone, but gains behavior when paired with a runtime host.

Typical inclusions:

- everything from capsule-free
- character runtime metadata
- environment utility/workstation descriptors
- command and integration descriptors
- optional adapter/config files for runtime mounting

What may be omitted:

- full runtime shell
- capsule payload

Examples:

- character asset pack with optional live character runtime companion
- environment bundle with optional interactive/control-unit mode
- utility-rich environment that can be inspected statically or hosted live

### Capsule-Required

Behavior is part of the product and must ship with a live host.

Typical inclusions:

- runtime shell
- seed state
- environment capture
- command surface
- live mirror surfaces
- workflow bindings
- optional capsule payload or hosted service dependency

Examples:

- inhabited character product
- mounted character inside an interactive environment
- agent API service
- research capsule

## Delivery Forms

### Character-Only Deliveries

#### A. Asset-Only Character

Includes:

- `.glb`
- optional `.vrm`
- optional `.usd` / `.fbx`
- textures
- embodiment metadata
- clip metadata
- manifest
- previews

Capsule required:

- no

#### B. Character With Runtime Companion

Includes:

- asset package
- runtime facility metadata
- command surface metadata
- integration notes
- optional small host shell or hosted endpoint reference

Capsule required:

- not necessarily

Requires:

- some compatible runtime host

#### C. Fully Inhabited Character Product

Includes:

- asset package
- runtime shell or hosted runtime reference
- command surface
- mirror/perception/state surfaces
- optional memory and workflow bindings

Capsule required:

- yes, either shipped or hosted-equivalent

### Environment-Only Deliveries

#### D. Static Environment Product

Includes:

- scene/environment assets
- semantics/taxonomy metadata
- environment manifest
- previews
- optional static viewer bundle

Capsule required:

- no

#### E. Interactive Environment Product

Includes:

- environment assets
- utility objects
- workstation/control-unit descriptors
- HTML templates
- workflow and interface metadata
- optional interface shell

Capsule required:

- only if the utilities or workstations must execute live behavior

If the environment only exposes static or external-facing interfaces:

- capsule may be omitted

If the environment hosts live tools/workflows:

- capsule or compatible runtime host is required

### Mounted Deliveries

#### F. Character Mounted Into Environment

Includes:

- environment product
- character product
- mount/integration metadata
- command facade or control-unit bindings
- state and perception surfaces

Capsule required:

- only if live behavior is part of the shipped product

#### G. Inhabited Interactive Environment

Includes:

- environment product
- one or more character products
- runtime shell
- control units
- utility objects
- live mirror/state surfaces
- API facade or operator interface

Capsule required:

- yes, or a compatible hosted runtime equivalent

### Desktop Companion Deliveries

#### H. Desktop Pet (Capsule-Free)

Includes:

- Electron desktop shell
- character asset (GLB + manifest + animation contract)
- desktop physics module
- click-to-trigger animation interactions

Capsule required:

- no

This is a static desktop pet. Animated character with no AI brain. Like Desktop Mate but with open character products.

#### I. Desktop Companion (Capsule-Optional)

Includes:

- everything from desktop pet
- provider bridge configuration
- character command surface metadata
- system tray chat interface

Capsule required:

- not necessarily — any compatible provider works

Character comes alive when connected to a cognition source (local model, cloud API, capsule). Without a provider, functions as a desktop pet.

#### J. Desktop Agent (Capsule-Required)

Includes:

- everything from desktop companion
- capsule runtime (memory, tools, workflows, council)
- desktop perception surface (window awareness, app classification, content awareness)
- environment summoning capability
- voice relay (ASR/TTS through character)
- desktop action tools (app launch, file ops, typing — Level 4 permission)

Capsule required:

- yes

Full agent companion. Desktop perception surface tracks user workflow context. Agent physically follows user's focus across windows. Offers contextual assistance based on app context and permission level.

## Environment Utilities and External Agents

Environments can absolutely ship with utilities and interactive surfaces.

An environment product may include:

- workstation objects
- utility objects
- interface objects
- HTML control panels
- API-binding metadata

However:

- a theater chat overlay should only appear when bound to an agent-bearing runtime target
- in the current model, that means a mounted character runtime
- static environment interfaces may ship without a chat overlay

That means an external agent can interface with an environment in at least three ways:

1. through a shipped control-unit HTML surface
2. through the command/API facade
3. through the mount contract when a character runtime is present

So environments are not passive backdrops only.

They can be:

- static
- operator-interactive
- externally interfaceable
- character-inhabited

## Bundle Profiles and Their Meaning

Current implemented bundle profiles in `server.py`:

- `environment_product`
- `interface_product`
- `agent_api_service`
- `research_capsule`

Planned bundle profile:

- `desktop_companion` — Electron shell + character product + desktop physics + optional capsule

### `environment_product`

Includes:

- runtime shell
- seed state
- environment capture
- live mirror
- visual evidence

Best for:

- interactive environment delivery

### `interface_product`

Includes:

- runtime shell
- seed state
- environment surfaces
- panel/interface shell

Best for:

- interface-first product delivery

### `agent_api_service`

Includes:

- runtime shell
- workflows
- service state
- workflow history

Best for:

- API-first hosted products

### `research_capsule`

Includes:

- runtime shell
- seed state
- environment capture
- live mirror
- visual evidence
- activity log
- workflow history
- development context

Best for:

- reconstruction, audit, research-grade delivery

## What Forces the Capsule to Ship

The capsule or equivalent hosted runtime is required when the product needs:

- live command execution
- live perception state
- live memory state
- workflow execution
- tool grants via utility objects
- workstation/control-unit actions with real backend effects
- council/provider-backed cognition

The capsule is not required when the product is only:

- geometry
- materials
- textures
- clips
- manifests
- metadata
- static viewers
- static scene bundles

## Character Runtime Use of Environment Facilities

A mounted character runtime uses environment facilities through the mount contract.

Typical flow:

1. environment exposes support, blockers, portals, utility objects, workstations
2. mounted character runtime reads those facilities
3. perception resolves what is visible/reachable/interactable
4. command surface issues actions
5. utility and workstation interactions extend or shape what the runtime can do

The environment provides the world.

The character product provides the embodied runtime.

The mount contract lets them work together.

## Minimum Inclusion Matrix

### To ship a portable character asset

Include:

- model asset(s)
- embodiment sidecar
- clip metadata
- manifest
- preview(s)

### To ship a character that can be mounted later

Include:

- portable character asset package
- character runtime metadata
- command surface metadata
- mount/integration metadata

### To ship a fully live character product

Include:

- portable character asset package
- runtime shell or hosted runtime target
- command surface
- perception/memory/runtime state surfaces
- workflow/tool integration if behavior depends on them

### To ship a static environment

Include:

- environment assets
- environment semantics/taxonomy
- manifest
- previews or viewer

### To ship an interactive environment

Include:

- environment assets
- utility/workstation/interface descriptors
- HTML templates where needed
- command/API integration metadata
- runtime shell only if live behavior is required

### To ship a total live product

Include:

- environment product
- character product
- mount/integration metadata
- runtime shell
- live command/perception/memory facilities
- utility/workstation bindings
- API or control-unit surfaces

## Desktop Companion as Delivery Form

The desktop companion is a delivery form, not a new product class. It uses the same two base product classes (environment product + character product) with a different host runtime shell.

The desktop IS an environment in this model:

| Desktop Element | Environment Analog | Physics Role |
|---|---|---|
| Taskbar | Ground plane / support surface | Primary walkable surface |
| Window title bars | Platforms | Secondary walkable surfaces |
| Window edges | Ledges | Grabbable/hangable |
| Screen edges | Walls | Boundary blockers |
| Cursor | Interactive entity | Grappable target, follow target |
| App icons (taskbar) | Landmarks | Navigation references |

The desktop perception surface is the analog to the environment perception surface (FOV/LOS/visible/occluded) but for the desktop context instead of the 3D environment.

Full architecture spec: `docs/DESKTOP_COMPANION_ARCHITECTURE_SPEC_2026-03-29.md`

## Non-Goals

- This document does not define specific game mechanics.
- This document does not require one engine-specific runtime.
- This document does not say every product must ship with the capsule.
- This document does not demote environments to passive scenery.

## Summary

The shipping question is not:

- capsule or no capsule?

The real question is:

- which facilities are required for the product being delivered?

If the product is static content:

- ship the assets and sidecars only

If the product is mount-ready:

- ship assets plus runtime metadata

If the product is live and interactive:

- ship or host the runtime shell and the facilities needed to operate it
