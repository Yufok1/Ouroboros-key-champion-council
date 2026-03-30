# Production Pipeline Map

Status: Active
Date: 2026-03-25
Scope: End-to-end production requirements for Champion Council from empty substrate to sellable product

## Purpose

Map the full production trajectory in concrete terms:

- what must be authored
- what must be implemented
- what must be validated
- what must be exported
- what must be documented for buyers and operators

This document is not a replacement for the roadmap. It is the execution map that sits between doctrine and implementation.

## Current Truth

Champion Council already has:

- canonical identity and product framing
- character-first product contract docs
- a canonical validation habitat
- runtime bundle/export profiles
- utility/workstation design specs
- a corrected architecture direction:
  - environment product
  - character product
  - character runtime facility mounted into environment facilities

Champion Council does not yet have:

- the corrected mounted-character implementation
- buyer-facing HTTP command facade
- engine adapter docs
- full embodiment import/export pipeline
- a fully aligned delivery matrix across every product variation

## Production Classes

### 1. Capsule-Free Products

Deliverable is a baked artifact. No live runtime required by the buyer.

Examples:

- GLB / VRM / FBX character assets
- baked environment scenes
- scenographic kits
- rendered media
- metadata packs

### 2. Capsule-Optional Products

Deliverable works as plain content, but gains behavior when paired with the capsule runtime.

Examples:

- character pack + optional live behavior companion
- environment bundle + optional inhabited mode
- scenographic kit + optional generator/runtime companion

### 3. Capsule-Required Products

Behavior is part of the product.

Examples:

- inhabited character products
- coordinated character packs
- inhabited environments
- agent API/runtime products

## Required Production Lanes

Everything we ship will pass through some combination of the following lanes.

### A. Doctrine and Contracts

Required outputs:

- identity doctrine
- roadmap
- product manifest spec
- manifest schema
- command registry
- template spec per product family

Purpose:

- keep architecture honest
- prevent squad-first drift
- define the buyer contract before adapter work

### B. Runtime Foundation

Required outputs:

- stable theater/runtime seams
- live mirror
- persistence loop
- environment control surface
- workflow execution substrate

Purpose:

- keep the product reconstructable
- keep behavior observable
- keep later export and debugging grounded in one runtime

### C. Validation Habitat

Required outputs:

- one canonical test habitat built from zero
- support surfaces explicitly authored
- blocker classes explicitly represented
- clean sightlines for perception tests
- repeatable spawn, recovery, and camera probes

Purpose:

- provide a trusted environment for Path A
- stop testing new runtime work in polluted showcase scenes

### D. Character Runtime

Required outputs:

- character runtime facility
- mounted-pose/state model
- command surface
- perception state
- memory/runtime identity surface
- mount contract into environment facilities

Purpose:

- turn the character product from document to mounted live runtime

### E. Facility and Workflow Surface

Required outputs:

- workstation bindings
- facility blueprints
- workflow bindings to workstations
- typed surfaces for operator interaction
- artifact/report output rules

Purpose:

- make environments functional, not merely visual
- give mounted character runtimes real environment-side execution targets

### F. Buyer API Surface

Required outputs:

- HTTP JSON command facade
- OpenAPI contract
- command payload schemas
- runtime-to-command binding layer

Purpose:

- expose `character.*` without exposing raw tool internals

### G. Embodiment and Asset Lane

Required outputs:

- rig-family normalization
- attachment-point contract
- animation contract
- asset import policy
- export normalization for GLB-first delivery

Purpose:

- support portable character products instead of one-off demo bodies

### H. Product Packaging

Required outputs:

- bundle profiles
- deployment payload
- previews and thumbnails
- metadata and provenance
- packaging rules for free / optional / required products
- shipping matrix for environment, character, and mounted variants

Purpose:

- move from internal runtime to distributable products

### I. Buyer Integration and Support

Required outputs:

- Unity notes
- Godot notes
- Unreal notes
- sample requests
- operator runbooks

Purpose:

- let a buyer evaluate quickly without learning MCP internals

### J. Desktop Companion Delivery

Required outputs:

- Electron desktop shell (transparent window + Three.js renderer)
- desktop physics engine (window collision, gravity, surface detection)
- desktop perception surface (window awareness, cursor tracking, app classification)
- character renderer adaptation (fixed camera, simplified lighting, transparent shadow catcher)
- system tray + chat popover + speech bubble overlay
- click-through hit-testing
- desktop companion product packaging (`desktop_companion` bundle profile)
- cursor interaction modes (follow, grapple, flee, ride)
- environment summoning system (object placement, scene context, full theater transition)

Purpose:

- ship character products as desktop-native companions
- same character product mounts into browser theater OR desktop shell
- desktop perception surface enables reactive context-following

Design reference:

- `docs/DESKTOP_COMPANION_ARCHITECTURE_SPEC_2026-03-29.md`

## What Must Be Produced

At minimum, the production pipeline must eventually emit all of the following categories.

### Specs and Schemas

- product manifest spec
- manifest JSON schema
- command registry
- runtime specs
- habitat specs
- facility specs
- adapter specs
- trust-tier schema / capability ladder
- role-profile schema
- governance-policy schema
- catalog/listing schema
- observer-evaluation attachment block

### Runtime Code

- theater/runtime seams
- inhabitant control and state
- perception and grounding
- facility/workflow execution glue
- command facade

### Scene and Habitat Assets

- validation habitat
- showcase/demo habitats
- product-ready environments
- captured visual references

### Product Artifacts

- character manifests
- environment manifests
- mounted-product integration manifests
- bundle exports
- preview media
- metadata packs

### Verification Surfaces

- live mirror fields
- capture/probe workflows
- validation checklists
- gate criteria

### Buyer-Facing Materials

- OpenAPI docs
- engine integration notes
- packaging/install guidance
- licensing/provenance statements
- runtime and product delivery matrix

### Gate 8: Desktop Companion Ready

Pass when:

- Electron shell renders a character on a transparent window
- desktop physics places character on window surfaces
- click-through works (transparent pixels pass through, character pixels interactive)
- system tray chat connects to capsule
- character command surface works through desktop shell

## Compound-System Tail

After the current animation lane is validated and the next embodiment milestones land, the production pipeline should explicitly capture these schema/runtime follow-ons:

- Trust-Graduated Agency Model — document the capability ladder across shipping modes and permission levels
- `v134-thin` Facility App Runtime proof — one utility object + one workstation + one granted workflow
- Role Synthesis Layer — role profiles that package facility ecology around one character product
- Governance Plane — named policy contract for permission ceilings, audit requirements, and approval triggers
- Catalog / Listing Schema — manifest-backed storefront/discovery layer
- Observer QA / Audit Pipeline — score and attach evaluation metadata to product outputs

Reference:

- `docs/COMPOUND_SYSTEMS_OPPORTUNITY_MAP_2026-03-29.md`

## Production Gates

Every lane should have a gate, not just a vague milestone.

### Gate 1: Contract Ready

Pass when:

- the product contract is documented
- schema validates
- command vocabulary is stable enough to target

### Gate 2: Runtime Presence Ready

Pass when:

- one inhabitant exists in the theater
- it can be spawned, focused, and removed
- mirror state is complete enough for debugging

### Gate 3: Validation Habitat Ready

Pass when:

- the habitat is built from zero
- support/blocker/perception cases are deliberate
- the scene is clean enough for repeated runtime testing

### Gate 4: Grounding/Perception Ready

Pass when:

- inhabitant does not spawn under scenery
- support surface is reported correctly
- visible/occluded object state is exposed

### Gate 5: Buyer API Ready

Pass when:

- HTTP facade exists
- OpenAPI exists
- character commands round-trip cleanly

### Gate 6: Portable Character Ready

Pass when:

- embodiment import/export rules are stable
- animation/rig/attachment contracts are explicit

### Gate 7: Product Export Ready

Pass when:

- a product bundle can be generated deterministically
- required metadata and preview assets exist

## Recommended Execution Order

This is the current honest build order.

1. Finish Path A in runtime code.
2. Build the canonical validation habitat from zero.
3. Validate grounding/perception in that habitat until stable.
4. Commit the current grounding follow-up.
5. Add the buyer-facing HTTP command facade.
6. Write engine adapter docs.
7. Move into embodiment import/export and product packaging.

## Environment Authoring Pattern

Use the environment tools in their canonical order:

- `env_spawn -> env_mutate -> env_persist`
- `env_spawn -> workstation_bind -> env_persist`
- `env_read -> env_control`

This matters because the validation habitat should be intentionally authored and reconstructable, not improvised from transient mutations.

## Immediate Deliverables

The next deliverables should be:

- one canonical validation habitat spec
- one canonical validation habitat scene built from zero
- completed grounding/perception follow-up commit
- a short validation checklist for inhabitant tests

## Non-Goals Right Now

Do not mix these into the immediate foundation pass:

- multi-inhabitant orchestration
- combat
- equipment
- procgen rebuild
- cinematic polish
- rich showcase world building

The next useful environment is a test habitat, not a content scene.
