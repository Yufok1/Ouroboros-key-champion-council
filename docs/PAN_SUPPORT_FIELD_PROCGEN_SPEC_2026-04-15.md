# Pan Support-Field Procgen Spec 2026-04-15

Repo: `D:\End-Game\champion_councl`

Purpose:

- ground the new Pan-facing proc-gen pivot in current local source and doctrine
- define the first honest support-field slice without inventing a fake terrain authority
- keep the work aligned with existing support/contact/staging truth

## Bottom Line

The new proc-gen direction is not "terrain generation" in the general sense.

It is a support-field generation lane:

- the body still exposes truthful contact and balance demand
- the substrate is allowed to compensate under intended contacts
- Pan later routes over that compensating substrate

The inversion is:

- old assumption: body accommodates fixed ground
- new pivot: support substrate can adapt toward body intent, within explicit limits

## Local Truth Already Present

The repo already computes the primitives this needs.

Current source and docs expose:

- `support_polygon` / `support_polygon_world`
- `inside_support_polygon`
- per-contact `contact_patch`
- support role and support-kind truth
- `support_y`
- route/support reports
- transition templates as contact grammar
- `workbench_stage_contact` as the deterministic staging gate

That means the support-field pivot should build on the current substrate, not beside it.

## Boundary Contract

Pan support-field proc gen must NOT:

- replace body truth
- bypass `workbench_stage_contact`
- silently teleport stability into existence
- create a hidden terrain truth plane that blackboard/theater cannot inspect

Pan support-field proc gen MAY:

- propose temporary support discs, pads, wedges, braces, or compliant catch surfaces
- reshape support topology under projected contact demand
- compensate altitude and contact bias ahead of landing
- emit explicit receipts showing what support was formed, why, and whether it was enough

## System Read

The clean local interpretation is:

- Tinkerbell points to where support opportunity or need exists
- Pan routes the body and support topology together
- the support field is the generated substrate Pan can ask for
- the mechanics runtime still decides whether the result is stable, blocked, penetrating, or outside polygon

So this is still a Pan-adjacent routing problem, not a shader trick.

## First Honest Slice

### 1. Proposal-Only Support Field Contract

Before any runtime autonomy, the system should be able to describe:

- intended contact target
- desired support compensation kind
- projected support patch/disc/wedge shape
- predicted support role
- acceptance or blocker receipt

Suggested internal naming:

- `_envBuilderProposeSupportField(...)`
- `_envBuilderSupportFieldReceipt(...)`
- `_envBuilderSupportFieldSummary(...)`

This stays proposal-only first.

### 2. Reuse Existing Route/Support Rows

The first diagnostics should ride existing lanes:

- route report
- blackboard session/route rows
- text theater support rows
- env_report session thread

Do not create a separate Pan dashboard first.

### 3. Visualize The Support Receipt

If a temporary support patch is proposed, the system should show:

- where it formed
- which contact it answered
- whether it was anticipatory, bracing, catch, or load-transfer support
- whether the body still exceeded what the substrate could save

The substrate has to earn the correction visibly.

### 4. Use Existing Contact Grammar

Transition templates already define phase logic and success criteria.

Support-field proc gen should consume that grammar:

- unload
- brace
- stage contact
- verify balance
- accept / retry / reject

That keeps Pan aligned with the authored curriculum instead of inventing a parallel control language.

## Initial Runtime Sequence

The first real sequence should look like:

1. declare contact intent
2. read current support truth and blocker state
3. propose support compensation under intended contacts
4. emit a support-field receipt
5. run the existing stage/balance verification path
6. keep or reject the support patch based on the same truthful outcome surfaces

## Out Of Scope For This Slice

- full Pan autonomy
- replacing authored transition templates
- freeform terrain synthesis
- hot-path camera/runtime routing through workflows
- hidden corrective cheating

## Why This Pivot Matters

The earlier contact-first work isolated the body's actual demands:

- contact patches
- support roles
- stability margin
- load transfer
- brace vs plant vs slip

Because that truth already exists, the dependency can now be inverted honestly.
The generated ground/support field can answer the body's demand instead of merely exposing where the body failed against a rigid floor.

That is the correct Pan-shaped proc-gen seam.

## Local Sources

- `docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md`
- `docs/PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md`
- `docs/DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md`
- `docs/LOCOMOTION_BRIDGE_PLANNING_2026-04-08.md`
- `static/main.js`
