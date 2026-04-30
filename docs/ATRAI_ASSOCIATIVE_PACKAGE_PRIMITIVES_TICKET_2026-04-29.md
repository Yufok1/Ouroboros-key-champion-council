# Ticket: Atrai Associative Package Primitives - 2026-04-29

## Status

Open.

## Continuity Cue

Operator direction:

- "source HOLD"
- "open surgery"
- "for anything AI can look at"
- "surface all associative package primitives"
- "Atrai primitives"

This ticket begins the continuity lane for making Atrai primitives visible as inspectable, source-bound packages.

## Objective

Surface all Atrai primitives as associative packages that an AI can inspect without confusing visibility for authority.

Each primitive package must state:

- primitive id
- family
- role
- source document or source artifact
- current status
- AI-visible surfaces
- human authority / HOLD condition
- provenance receipt path
- dependencies
- risks
- next validation action

## Organism-Mainframe Boundary

The intended surface is an organism-mainframe display for complex systems componentry.

That means primitives can be rendered as organism-like cards, networks, capsules, or microscope panes so humans can inspect how the system fits together. The display may show dependencies, lineage, risk, health, simulation state, and provenance.

The display must not become a control plane by accident.

Allowed:

- inspect primitives
- compare primitives
- trace source documents
- show causal/provenance links
- simulate hypothetical behavior
- flag Source HOLD requirements
- prepare an operator review packet

Not allowed without explicit human Source HOLD:

- deploy physical infrastructure
- move funds or assets
- issue credentials
- alter production auth state
- publish civic commitments
- claim community consent
- convert simulation output into real-world instruction
- auto-promote an AI recommendation into execution

## Failure Mode To Prevent

The failure mode is not "AI can see the system."

The failure mode is "AI-visible display becomes authority."

Prevent it by keeping four planes separate:

- `display`: what the organism-mainframe shows
- `source`: where the primitive came from
- `proposal`: what an AI or tool recommends
- `authority`: what a human/community explicitly authorizes

No package is allowed to collapse those planes into one.

## Doctrine

Atrai is a human-governed, community-bound mobile fortress for civic continuity.

Atrai is sustained by mobile forces only.

AI systems may inspect, connect, summarize, simulate, and propose over Atrai packages. They do not authorize construction, deployment, movement, security posture, funding decisions, credential use, or civic commitments.

Source HOLD applies to any primitive package that can affect real people, real resources, credentials, civic claims, deployment state, or public commitments.

"Win at all costs" is not an operating rule for Atrai. The people are the point. A win condition that sacrifices human authority, community consent, safety, or continuity is a failed condition.

## Primitive Families

Initial Atrai package families:

1. `mobile_shelter`
2. `mobile_energy`
3. `mobile_water`
4. `mobile_food`
5. `mobile_medical`
6. `mobile_comms`
7. `mobile_compute`
8. `mobile_archive`
9. `mobile_repair`
10. `mobile_fabrication`
11. `mobile_training`
12. `mobile_governance`
13. `mobile_logistics`
14. `mobile_safety`
15. `mobile_evacuate`
16. `provenance_spine`
17. `source_hold`
18. `auth_boundary`
19. `simulation_foresight`
20. `community_consent`

Existing canyon-span and carrier-fortress primitives remain relevant as facility/mechanics primitives, but this ticket reframes them as packages under Atrai's ark faculty rather than as standalone spectacle.

## Package Shape

```json
{
  "id": "mobile_energy.primary_microgrid",
  "family": "mobile_energy",
  "role": "portable energy generation, storage, and distribution",
  "source": {
    "kind": "doc|code|runtime|operator|generated",
    "path": "docs/...",
    "observed_at": "2026-04-29T00:00:00-04:00"
  },
  "status": "proposed|designed|simulated|validated|deployed|blocked",
  "ai_visible_surfaces": [
    "docs",
    "logs",
    "simulation outputs",
    "provenance records"
  ],
  "source_hold": {
    "required": true,
    "condition": "any physical, financial, credential, civic, or public deployment action",
    "human_authority": "operator/community"
  },
  "provenance": {
    "receipt_path": "cascade/rerun/docs",
    "hash": ""
  },
  "dependencies": [],
  "risks": [],
  "next_validation": ""
}
```

## Source Documents To Reconcile

Start from:

- `docs/brotology/SOURCE_HOLD_OPEN_SURGERY_DOCTRINE_2026-04-29.md`
- `docs/brotology/ATRAI_VESSEL_FIELD_BRIEF_2026-04-23.md`
- `docs/brotology/ATRAI_KINETIC_ARCHITECTURE_SESSION_SYNTHESIS_2026-04-27.md`
- `docs/brotology/ATRAI_LATEST_DEVELOPMENTS_REPORT_2026-04-28.md`
- `docs/brotology/CARRIER_FORTRESS_CANYON_SPAN_PLANNING_DOSSIER_2026-04-23.md`
- `docs/brotology/CANYON_SPAN_PRIMITIVE_REGISTRY_SPEC_2026-04-23.md`
- `docs/brotology/HIGH_YIELD_BROSPECULATION_CANYON_SPAN_SIMULATION_PRIMITIVES_REPORT_2026-04-23.md`
- `docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md`
- `docs/STRATIFIED_ROTATIONAL_CONTAINMENT_CONTINUITY_MODEL_2026-04-23.md`

## Work Plan

1. Inventory every Atrai/canyon/mobile-fortress primitive currently named in docs.
2. Normalize duplicate names into canonical primitive ids.
3. Classify each primitive into one Atrai package family.
4. Attach source status and AI-visible surfaces.
5. Add Source HOLD condition for each package.
6. Mark which packages are conceptual, simulated, validated, or deployed.
7. Create a machine-readable registry after the doc inventory is stable.
8. Wire the registry into Champion Council / blackboard only after source status is clear.

## Acceptance Criteria

This ticket is done when:

- every named Atrai primitive has one canonical package row
- every package row identifies its source and current status
- every AI-visible surface has an authority boundary
- every physical/civic/financial/auth action routes through Source HOLD
- no package creates a second authority plane
- registry output can be read by humans and AI without granting AI execution authority

## Next Concrete Action

Build the first `ATRAI_PRIMITIVE_REGISTRY_2026-04-29.md` from the source documents above.
