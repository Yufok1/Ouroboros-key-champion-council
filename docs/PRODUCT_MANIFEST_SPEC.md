# Product Manifest Spec

Status: Draft
Date: 2026-03-25
Scope: Individual character product as the base commercial unit

## Purpose

Define the buyer-facing contract for Champion Council products.

The base sellable unit is an individual embodied character product, not a squad. Group, pack, or faction products are later composition layers built on top of this base contract.

This manifest does not replace the current bundle export payload. It wraps it.

## Design Rules

1. The base product is one character.
2. `deployment` nests the current exporter payload instead of replacing it.
3. `command_surface` defines the buyer-facing verbs.
4. `tool_policy` is internal runtime policy, not the buyer contract.
5. MCP remains canonical internally; buyer integrations target a thin HTTP JSON facade first.
6. The same product may be sold as capsule-free, capsule-optional, or capsule-required depending on which layers are included.

## Top-Level Shape

```json
{
  "manifest_kind": "champion.character_product",
  "schema_version": "1.0.0",
  "identity": {},
  "embodiment": {},
  "assets": {},
  "capabilities": [],
  "command_surface": {},
  "configuration": {},
  "requirements": {},
  "integration": {},
  "deployment": {}
}
```

## Fields

### `manifest_kind`

Canonical discriminator for the product family.

Initial value:

- `champion.character_product`

Future composition examples:

- `champion.character_pack`
- `champion.group_product`
- `champion.environment_product`
- `champion.facility_product`

### `schema_version`

Version of the manifest contract, not the product itself.

Use semantic versioning.

### `identity`

Describes what the product is.

Required intent:

- stable product id
- display name
- product version
- short description

Recommended additions:

- author / studio
- license
- provenance hash
- canonical docs

### `embodiment`

Describes what kind of character this is.

Required intent:

- family
- rig profile
- locomotion profile

Recommended additions:

- attachment points
- expression support
- scale profile
- animation contract

### `assets`

Describes what files ship and how they should be treated.

Required intent:

- primary format
- primary entry file
- shipped file list

Recommended additions:

- preview media
- materials / textures
- optional companion formats
- engine import hints

### `capabilities`

Human-readable and machine-readable description of what the character can do.

Examples:

- locomotion
- look-at
- inspect
- speak
- follow
- idle
- interact

This is not the same thing as commands. Capabilities describe available behavior; commands define callable operations.

For character products, capabilities may include both:

- embodied abilities intrinsic to the character package
- runtime-facility abilities exposed when the product is mounted into an environment

### `command_surface`

Defines how the buyer talks to the product.

Required intent:

- command surface version
- internal transport
- external transport
- stable command list

Each command should declare:

- name
- summary
- side-effect class
- request schema reference
- response schema reference
- implementation binding

Implementation bindings may point to:

- workflow ids
- runtime handlers
- future command-dispatch routes

The buyer should never need to know which raw tools are called internally.

### `configuration`

Defines what the buyer may tune without forking the product.

Examples:

- display name override
- voice/profile selection
- movement speed multiplier
- follow distance
- speech verbosity
- capsule enable/disable flags

### `requirements`

Defines what the product needs to run.

Examples:

- inference mode: none / local / cloud / hybrid
- minimum runtime dependencies
- model family expectations
- resource budget
- optional services
- whether the shipped form is asset-only, mount-ready, or live-runtime-backed

### `integration`

Defines how the buyer connects the product to an external runtime.

Required intent:

- primary external transport
- OpenAPI document or equivalent reference
- engine notes

Recommended additions:

- Unity package path
- Unreal plugin path
- Godot addon path
- example calls
- mount contract reference for environment integration

### `deployment`

Nests the existing exporter payload.

This section is for deployment and reconstruction concerns, not first-contact buyer understanding.

Expected contents today include:

- bundle profile
- launch defaults
- source runtime
- seed state
- environment capture
- development context
- runtime shell
- policies
- warnings

For live-runtime-backed character products, this section may also include:

- character runtime facility metadata
- environment mount defaults
- runtime host expectations

## Composition Rule

Character products are atoms.

Group products may later compose multiple character manifests plus:

- shared memory namespaces
- shared commands
- shared orchestration metadata

Do not pollute the base character contract with group-only fields.

## Product Modes

The same manifest family supports three commercial modes:

1. Capsule-free
2. Capsule-optional
3. Capsule-required

The distinction is expressed through `requirements`, `integration`, and `deployment`, not by inventing a second manifest family.

### Runtime Facility Rule

For character products:

- the actor/runtime layer belongs to the character product
- it is not a separate product by default
- it mounts into environment facilities through the integration contract

So the manifest should describe:

- what the character package intrinsically carries
- what it needs from a host environment
- what extra facilities are required for live behavior

## Non-Goals

- Do not expose the full raw MCP tool surface here.
- Do not encode squad/group assumptions into the base character product.
- Do not replace the current exporter payload.
- Do not hard-lock the manifest to one engine or one transport.
