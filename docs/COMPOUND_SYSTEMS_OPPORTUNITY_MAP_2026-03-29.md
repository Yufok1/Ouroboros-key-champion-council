# Compound Systems Opportunity Map

Status: Active synthesis
Date: 2026-03-29
Scope: Name and encapsulate the higher-order systems that emerge when Champion Council specs are read together instead of in isolation

## Purpose

Several strategic systems already exist implicitly across the current doctrine, runtime, and delivery docs.

They are easy to miss because they are distributed across:

- character product doctrine
- delivery matrix tiers
- desktop permission tiers
- utility/workstation specs
- theater observer surfaces
- product manifest and export surfaces

This document names those compound systems so they can be planned and shipped intentionally.

## 1. Trust-Graduated Agency Model

### Why It Is Real

Three independently-written specs already define the ladder:

- manifest modes: capsule-free / capsule-optional / capsule-required
- desktop permission tiers: Level 0-4
- utility/tool grants: access to specific capability bundles

Together they describe the same character product at different trust and agency levels.

### What Already Exists

- shipping modes in `docs/RUNTIME_AND_PRODUCT_DELIVERY_MATRIX_2026-03-25.md`
- buyer-facing manifest in `docs/PRODUCT_MANIFEST_SPEC.md`
- desktop permission tiers in `docs/DESKTOP_COMPANION_ARCHITECTURE_SPEC_2026-03-29.md`
- bundle export in `server.py`

### What Is Missing

A single named schema that maps:

- trust tier
- included capabilities
- required host/runtime shell
- required permissions
- upgrade path between tiers

### Smallest Proof

Add trust-tier language to the manifest and delivery docs showing that the same character product can ship as:

- static asset
- reactive desktop pet
- provider-backed companion
- capsule-backed assistant
- full action-capable agent

### Best Roadmap Slot

Immediately after `v133c`.

This is schema/doc work, not a risky runtime change.

## 2. Facility App Runtime

### Why It Is Real

Control units, utility objects, HTML panels, workflow execution, and workstation/facility tools already describe a spatial application runtime.

The environment is not just scenery. It is an app host.

### What Already Exists

- workstation and utility object doctrine in `docs/CONTROL_UNIT_AND_UTILITY_OBJECT_SPEC_2026-03-25.md`
- role-bearing taxonomy in `docs/OBJECT_TAXONOMY_SPEC_2026-03-25.md`
- HTML panel system in `static/main.js`
- workflow engine and facility/workstation tool surfaces in the runtime shell and capsule

### What Is Missing

- proximity-based tool grant wiring
- workstation template rendering tied to live agent state
- activation / revocation lifecycle
- one proof workstation wired end-to-end

### Smallest Proof

One forge or terminal workstation:

- character walks to it
- proximity grants tools/workflows
- HTML panel exposes the workstation surface
- character uses granted tools
- leaving the station revokes access

### Best Roadmap Slot

`v134-thin`, immediately after `v133c`.

## 3. Observer QA / Audit Pipeline

### Why It Is Real

The theater observer stack, capture surfaces, and Coquina observer logic already imply a self-auditing content pipeline.

This is not just debug tooling. It is a production-quality evaluation surface.

### What Already Exists

- `capture_supercam`
- `capture_probe`
- `probe_compare`
- semantic evidence / confidence in theater vision
- observer-guided procedural generation goals in the Coquina spec

### What Is Missing

- explicit scoring function
- batch evaluation mode
- a manifest attachment point for evaluation metadata

### Smallest Proof

Generate or load one environment, run observer captures, compute one aggregate quality score, and attach an `observer_evaluation` block to the product output.

### Best Roadmap Slot

After the first Coquina vocabulary / atom pass is live enough to score.

## 4. Role Synthesis Layer

### Why It Is Real

The same character product can become different roles by changing:

- utility objects
- workstation templates
- granted tools
- memory namespaces
- perception overrides

No retraining is required for the role change.

### What Already Exists

- character product + mount contract
- utility object capability grants
- workstation/control-unit templates
- bounded memory surface doctrine

### What Is Missing

A named `role_profile` schema that binds facility ecology to a role definition.

### Smallest Proof

Two role profiles for the same character:

- `archivist`
- `operator`

Same embodiment, different facility environment, different tool grants, different memory lanes.

### Best Roadmap Slot

Right after `v134-thin`, because it depends on proving the facility runtime first.

## 5. Catalog / Listing Schema

### Why It Is Real

The product system already has manifests, delivery forms, preview media generation, and packaging outputs.

That is enough for a storefront/listing layer even though no explicit catalog schema exists yet.

### What Already Exists

- product manifest
- delivery matrix
- preview capture surfaces
- bundle export
- gate language for readiness and validation

### What Is Missing

A `catalog_entry` or listing contract that references:

- manifest identity
- preview media
- trust tier
- pricing / commercial tier
- observer evaluation

### Smallest Proof

One static listing for one character product generated from its manifest plus captured preview assets.

### Best Roadmap Slot

After `v136`, because it sits on top of the export/packaging layer.

## 6. Governance Plane

### Why It Is Real

Champion Council already has the pieces of a formal adjudication stack:

- permission tiers
- tool grants
- workstation constraints
- live mirror
- activity history
- observer capture
- HOLD / oversight mechanisms

Together these form a governance layer for agency.

### What Already Exists

- permission/tier doctrine
- tool-grant and workstation doctrine
- activity bus and live mirror
- observer capture/probe
- oversight hooks in the capsule/runtime stack

### What Is Missing

A unifying `governance_policy` schema that binds:

- permission ceiling
- tool whitelist
- audit requirements
- approval triggers
- observation cadence

### Smallest Proof

Define one governance policy for one mounted character and show that the same character under a different policy has different effective abilities and oversight requirements.

### Best Roadmap Slot

After the role synthesis layer, because governance is a constraint system over already-proven roles/facilities.

## Execution Tail

This does not replace the current active sequence.

Near-term order remains:

1. humanoid cohort validation
2. `v133b.2`
3. `v133c`

Then the schema/runtime tail becomes:

4. trust-graduated agency model
5. `v134-thin` one utility object + one workstation
6. role synthesis layer
7. governance plane
8. `v135`
9. `v136`
10. catalog/listing schema
11. observer QA / audit pipeline

## Summary

The overlooked opportunity is not another renderer or a cosmetic flourish.

The real opportunity is that Champion Council already describes:

- permissioned agency
- spatial capability acquisition
- environment-hosted applications
- self-auditing products
- portable multi-tier character offerings

These systems should now be treated as named product/runtime layers, not just implied side effects of separate specs.
