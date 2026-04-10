# Reactive Mobility Primitives Trajectory 2026-04-10

Repo: `F:\End-Game\champion_councl`

Purpose:

- consolidate the emerging "passive rebalance" + "reactive ninja / traversal" framing into one coherent architecture
- ground that architecture in current source truth and existing doctrine instead of wishful extrapolation
- define the next honest primitive stack so future sprint, crawl, vault, brace, tumble, climb, and recovery work all ride one substrate

## Core Thesis

What the user is calling "reactive ninja mode" does align with the current direction, but only if it is understood correctly:

- it is **not** a separate physics system
- it is **not** a special animation bank
- it is **not** settle reborn
- it **is** a higher-order runtime controller family built on the same contact/support/balance substrate already returning in source

That means:

- passive rebalance
- sprint stabilization
- stumble recovery
- crawl/rise
- vault / brace / wall use
- controlled descent / tumble / catch

should all be treated as different objective profiles over one common stack of truth.

## Corroborated Current Truth

The current repo already points toward this architecture from multiple directions.

### 1. Source already carries the beginnings of contact-role truth

Current source exports and uses:

- contact manifold clipping from candidate patch against support plane
- `contact_mode` with values like `point`, `edge`, `partial`, `full`, `inverted`
- `support_role` with `plant` vs `brace`
- `support_phase` including `braced_support`
- `balance_mode` including `braced`
- world-space balance exports:
  - `gravity_vector`
  - `support_frame`
  - `support_polygon_world`
  - `projected_com_world`

Relevant source anchors:

- `static/main.js` `_envBuilderContactManifoldForPatch(...)`
- `static/main.js` contact-row classification and `support_role`
- `static/main.js` load-field balance classification
- `static/main.js` `_envBuildTextTheaterSnapshot(...)`

### 2. Existing doctrine already says locomotion must be contact-driven

`docs/LOCOMOTION_BRIDGE_PLANNING_2026-04-08.md` already commits to:

- contact sequencing
- support-frame evaluation
- balance evaluation during movement
- displacement accepted only when contact expectations and support truth remain coherent
- runtime transition from nominal locomotion into brace / fall lanes when support degrades

This is already the seed of a reactive controller. It just is not fully rebuilt yet.

### 3. Existing doctrine already generalizes beyond feet

`docs/BONE_FIRST_PHYSICS_ARCHITECTURE_2026-04-07.md` already commits to:

- `supportingFeet -> supportingContacts`
- patch families beyond the foot:
  - knee
  - palm
  - forearm / elbow
  - hip / side
  - back / scapular
  - chest / sternum
  - head as last resort
- brace contribution
- chain tilt
- leverage / compensation metrics
- crawling / rising as legitimate first-class support behaviors

That is already the right doctrinal bridge from walking into whole-body traversal.

### 4. The blackboard doctrine already supports a richer controller

`docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md` already says:

- the blackboard is structured data first, renderer second
- the blackboard is not a raw shared-state dump; it is curated projection over snapshot truth
- the web theater can consume the same blackboard as a dev overlay
- camera-relative collation promotes diagnostics near what the operator is looking at
- near-field measurements and far-field interpretation should be linked by leader lines / indicators

That is exactly the surface needed to inspect a richer reactive controller without shipping diagnostics in product mode.

Operator rule for this lane:

- after any theater-affecting mechanics command, read the text theater render first
- use `text_theater_snapshot` second for structured detail
- use probe capture third when the rendered pose still needs visual triangulation
- treat `shared_state` as tertiary corroboration, not the first proof surface

### 5. Live staging has already crossed one important threshold

The chosen-contact realization seam that previously made knee staging look fake is closed in the current worktree.

What that means concretely:

- honest two-knee brace staging has already been proven live in text theater
- the stage gate is no longer losing its correction immediately to generic parent mesh support snapping
- support-floor reasoning is no longer hardwired to feet only

That changes the blocker.

The active blocker is now mixed support-topology authoring, not basic knee realization:

- half-kneel
- tripod brace
- forearm-plank
- scramble / low crawl transitions

are still awkward to author with raw single-bone rotations alone

and multi-target staging still reduces requested contacts independently instead of jointly solving the intended support set

This is why chain-aware/grouped posing is now a more immediate operator-facing need than another isolated knee push.

The important authority correction is:

- `workbench_set_pose_batch` already exists as the canonical coordinated mutation lane
- grouped pivots, chain selection, support-transition macros, and future marionette-like handles should produce native batch-pose payloads instead of creating a second pose substrate
- `workbench_stage_contact` remains the deterministic contact gate / verifier after posing, not the authoring engine and not a hidden route solver

## Sequencing Correction

The roadmap should not be interpreted as "later named systems are forbidden until their numbered slice arrives."

That would be too rigid and would misread the current blocker.

Correct rule:

- full systems can stay deferred
- thin enabling contracts can move earlier when they are the minimum honest way to close the current blocker

Current examples:

- a Pan-shaped route report can appear before full Pan
- blackboard-ready corroboration/export fields can appear before full blackboard rendering
- primitive labels can attach to macros and route outcomes before the full runtime primitive controller ships

What must stay deferred:

- full autonomous contact routing
- full blackboard/holographic consumer stack
- full runtime reactive locomotion controller

What may move earlier:

- maneuver descriptor shape
- intended vs realized support reporting
- blocker / next-adjustment reporting
- controller/export fields needed for theater-first parity

This is not a roadmap violation.
It is a dependency correction.

## The Right Architectural Read

There are not two unrelated modes here.

There is one mechanics and control stack:

1. contact candidate surfaces
2. active contact manifolds
3. support/load/balance truth
4. runtime control primitives
5. maneuver / behavior policies
6. dev-only diagnostic consumers

The difference between "passive rebalance" and "reactive ninja mode" is not the substrate.
The difference is the controller objective, aggressiveness, and planning horizon.

## Primitive Stack

This is the clean breakdown that best matches both current source and near-future work.

### Layer 0: Environment Affordance Truth

Question:

- what in the environment can support, brace, redirect, or catch the body?

Required truth:

- support surface normal
- support point / plane / local curvature
- friction/slip proxy later
- semantic affordance tags later:
  - standable
  - braceable
  - vaultable
  - crawlable
  - climbable
  - perchable

Current status:

- partially present
- still too flat-plane biased in the workbench lane
- must become authoritative before advanced traversal is honest

### Layer 1: Body Contact Candidates

Question:

- what body regions can legitimately contact and carry/support mass?

Canonical families:

- foot
- knee
- palm / hand heel
- forearm / elbow
- hip / side
- back / scapular
- chest / sternum
- head (last resort)

Important rule:

These are mechanics surfaces, not visible skin.

The Coquina or body-shell lane must consume them with a clearance contract.
Do not let visible foot bottoms or body shells define support truth directly.

### Layer 2: Active Contact Manifolds

Question:

- which subset of a candidate surface is actually contacting right now?

This is the missing precision layer between "a foot has a sole patch" and "the heel edge is actually taking load."

Examples:

- heel strike = edge manifold
- toe-off = edge / partial manifold
- flat stance = full manifold
- wall brace with palm = partial manifold
- inverted foot on ground = still contact, but brace-like / degraded / special handling

Current source already has the beginning of this through:

- candidate patch clipping
- `contact_mode`
- manifold area / ratio / points

That is the right direction.

### Layer 3: Support / Load / Balance Truth

Question:

- given the active manifolds, what is the current support situation of the whole body?

Core fields:

- active supporting set
- support polygon
- projected CoM
- stability margin / risk
- support loads
- segment loads
- `support_phase`
- `balance_mode`

The recent plant-vs-brace distinction belongs here:

- `plant` = stable, weight-bearing support with good patch engagement
- `brace` = real but degraded/transient/angled support that still matters for truth

This is important for sprinting, stumbling, wall use, crawling, and recovery.
An edge, corner, or sliver contact is not "fake."
It is often brace truth.

### Layer 4: Runtime Control Primitives

Question:

- what are the smallest reusable actions the controller can compose?

Do not start from named maneuvers like "vault" or "wall-run."
Start from control primitives.

Recommended first primitive family:

- `hold_support`
- `shift_load`
- `load_contact`
- `unload_contact`
- `plant_contact`
- `brace_contact`
- `push_off`
- `reach_for_support`
- `catch_fall`
- `control_descent`
- `roll_or_redirect`
- `recover_to_nominal`

These primitives are what sprint, crouch-run, vault, crawl, and climb will compose.

### Layer 5: Maneuver / Policy Families

Question:

- what high-level behavior objective is currently active?

These should be policies over the same primitives, not a new substrate.

## Immediate Operator Blocker

Before a broad "all contact families at once" calibration pass, the authoring surface needs to stop fighting realistic support topologies.

What is currently true:

- two-knee brace contact can be realized honestly
- a realistic half-kneel or tripod brace is still awkward to reach through raw single-bone batch posing
- naive arm/elbow posing can easily produce painful or inverted-looking authoring states even before contact truth is checked

That means the next operator-facing slice should be:

1. grouped multi-bone selection
2. centroid / grouped pivot for selected bones
3. chain selection via the existing isolation-chain substrate
4. authored support-transition macros:
   - `half_kneel_l`
   - `half_kneel_r`
   - `rest_kneel`
   - `tripod_brace_l`
   - `tripod_brace_r`

This does not replace later routing.

It gives the operator an honest way to author the mixed support sets that the routing/controller stack will later consume and automate.

## Controller Interop Read

The batch pose lane should stay canonical.

What needs to improve is the authoring layer over it.

Recommended structure:

1. controller registry per body plan
   - canonical chain/controller definitions
   - root bones
   - translation carriers
   - pivot rules
   - contact-family ownership

2. dynamic grouped-controller allocation
   - single chain
   - mirrored pairs
   - adjacent chains
   - ad hoc selected bones when needed

3. grouped preview session
   - grouped pivot world position
   - grouped mode / space
   - preview-active flag
   - affected controller ids / bone ids

4. native batch-pose commit
   - grouped drag end emits `{ poses:[...] }`
   - support-transition macros are stored as named batch-pose artifacts or short sequences

5. theater / blackboard parity
   - the same grouped-controller export feeds web view, text theater, and later blackboard panels
   - no renderer should guess grouped attachment state independently

This avoids rebuilding a second pose system while still giving the operator a much richer body-part control surface.

Likely policy families:

- nominal locomotion
- aggressive locomotion
- reactive recovery
- obstacle traversal
- crawl / low-clearance traversal
- vertical traversal later
- stunt / acrobatic later

This is where "reactive ninja mode" belongs:

- an aggressive reactive traversal policy
- broader support vocabulary
- faster support transfer
- willingness to use brace contacts opportunistically
- still bounded by real support truth

### Layer 6: Dev-Only Diagnostic Consumers

Question:

- how do we inspect and debug this without polluting the final product?

Consumers:

- text theater
- blackboard
- web theater overlay
- scaffold weight dynamics
- bone carpenter
- support polygon / CoM / drift / contact overlays
- observer / prospect / Tinkerbell later

Product rule:

- product ships motion
- dev mode ships reasoning

## Why This Scales Beyond Humanoids

The right abstraction is not "two feet."
It is "N candidate support families and a controller that reasons over support transfer."

That means the core architecture should remain:

- generic contact ids
- generic patch builders
- generic manifold computation
- generic support-role classification
- generic support/load aggregation

Humanoid left/right feet remain derived convenience views, not the core storage model.

That is the right path for:

- humanoids
- quadrupeds
- centipede-like bodies
- stylized creatures with non-human support patterns

## What This Means For Sprinting

Sprinting is not just "run faster."

A sprint should be understood as:

- shorter stable-support windows
- more transient brace-like contacts
- more aggressive load transfer
- larger corrective demands
- tighter coupling between contact timing and displacement

That means sprinting is an ideal proving ground for the plant/brace distinction:

- flat sole under load = plant
- clipped edge / angled forefoot / sliver support = brace
- rapid transitions among those roles are expected, not anomalous

## What This Means For Vault / Crawl / Wall Use

Vaulting, crawling, and wall use should not be modeled as canned trick clips first.

They should emerge from:

- richer contact families
- object affordance truth
- broader primitive vocabulary
- controller willingness to exploit those supports

Example decompositions:

- vault:
  - reach_for_support
  - brace_contact(hand/forearm)
  - unload_contact(leading foot)
  - shift_load
  - redirect CoM
  - recover_to_nominal

- crawl:
  - lower support height
  - alternate palm / knee plants
  - torso clearance management
  - continuous brace + plant mixtures

- wall brace / recovery:
  - detect lateral loss of support
  - reach_for_support
  - brace_contact(hand/forearm)
  - redirect / control_descent

These are compositions of primitives, not separate mechanical universes.

## Contact Family Progression

The safest progression is not "all body regions at once."
It is a staged rollout from primary support into brace support into passive collapse support.

### Tier 1: Primary support

- foot

This is the mature standing / walking / running support family.
It deserves the densest patch treatment and the richest manifold logic first.

### Tier 2: Brace contacts

- knee
- palm / hand heel
- forearm / elbow

These should become useful before any dexterous hand or special-contact logic exists.

Their job is:

- arrest or redirect failing balance
- provide transitional support
- widen the support vocabulary during recovery and traversal

They do **not** need fine manipulation fidelity yet.
They need coarse but honest patch geometry and clear `brace` role semantics.

Recommended rollout order inside Tier 2:

1. knee
2. palm
3. forearm / elbow

Reason:

- knee extends the already-honest lower-limb chain most directly
- palm is the first high-value whole-body brace surface
- forearm / elbow extends the palm brace lane when wrist orientation is not viable

### Tier 3: Broad passive / collapse surfaces

- hip / side
- back / scapular
- chest / sternum
- stomach / torso

These are not active propulsive contacts.
They are passive load-accepting surfaces for tumbles, failed recoveries, and low-posture traversal truth.

Geometry can stay coarse here.
The key value is honest reporting:

- what surface contacted
- how much load it accepted
- whether it is stable, risky, or purely collapse-state support

### Tier 4: Dexterous or last-resort surfaces

- finger-level hand detail
- head / face / occiput detail

Defer these aggressively.
They are not needed for honest locomotion and reactive support recovery.

## Recommended Near-Term Trajectory

This should stay honest and incremental.

### 1. Finish truthful support generalization

- complete `supportingContacts`
- finish patch families:
  - knee
  - palm
  - forearm / elbow
- keep broad passive surfaces queued after those

### 2. Make terrain/support surfaces authoritative

- remove flat-plane assumptions where still lingering
- expose real support normals and surface records consistently
- prepare for object contacts beyond the floor

### 3. Formalize runtime control primitives

Before writing "ninja" policies, define and expose the primitive vocabulary.

The primitive set should stay small enough to encourage composition, but rich enough to distinguish rigid support from compliant catch behavior.

Recommended minimum runtime vocabulary:

Discrete contact primitives:

- `plant_contact(contact_id, target_pose)`
- `unload_contact(contact_id)`
- `reach_for_support(body_region, target_affordance)`
- `push_off(contact_id, direction)`

Rhythmic locomotion primitive:

- `gait_cycle(gait_id, phase)`

Impedance primitives:

- `hold_support(contact_set, stiffness_profile)`
- `absorb_impact(contact_id, compliance_profile)`
- `stiffen_brace(contact_id)`

Meta primitive:

- `recover_to_nominal()`

Important rule:

- do not prematurely promote compositions into new primitives

Examples:

- `shift_load` is changing support/impedance allocation across an active contact set
- `catch_fall` is `reach_for_support + absorb_impact`
- `control_descent` is a compliant contact sequence under downward displacement intent

The impedance class is critical.
Without it, every contact collapses into "rigid support," which is wrong for catches, braces, impacts, and controlled landings.

## Pan: Deferred Contact Placement Router

Pan is the dev-facing name for the future contact placement router.

Code should stay concrete:

- `contact_router`
- `contact_placement_router`
- `_envBuilderPlanContactRoute(...)`
- `_envBuilderProposeSupportRoute(...)`

The themed surface label can be:

- `Pan`
- `PAN = Posture Affordance Navigator`

Do not build Pan before the substrate below it is honest.

Important sequencing clarification:

- do not build full Pan before the substrate is honest
- do allow Pan-v0 report contracts to appear earlier when the current blocker requires a standardized route/maneuver report
- that thin Pan form should stay proposal-only and should still feed the existing `workbench_set_pose_batch` + `workbench_stage_contact` substrate

### Tinkerbell vs Pan

Tinkerbell and Pan share the same spatial substrate, but they answer different questions.

Tinkerbell:

- question: where should attention/projection go next?
- input: focus target, support frame, camera pose, observation intent
- output: observer/prospect target, expected observation delta, view intent
- operates on one spatial point at a time

Pan:

- question: how does the body redistribute mass so a desired contact can reach a target surface?
- input: contact intent, current support set, balance truth, penetration constraints, affordance truth
- output: support route, pose proposal sequence, primitive dispatch order
- operates across the whole active contact set

Short mnemonic:

- Tinkerbell points
- Pan routes

### Why Pan Exists

The new `workbench_stage_contact` command proves the single-contact staging gate, but it does not solve routing.

Example:

- contact intent: `lower_leg_l` knee pad should reach the support plane
- staging gate: can the current posed body be translated so that patch reaches the support plane?
- current observed result: `blocked_by_penetration` when other patches would be buried below the floor

That blocked result is correct. It means the single-contact gate is honest.

Pan consumes that result and plans the surrounding support route:

- which contacts must unload
- which contacts should brace
- which joint batch pose should be proposed
- which contact should be staged and validated next
- whether the plan should be rejected, retried, or committed to a sequence

Without Pan, contact placement is drag-and-hope.
With Pan, contact placement becomes a constrained routing problem.

### Pan Build Position

Pan ships after the primitive vocabulary and affordance contract, not before.

Minimum prerequisites:

- candidate patch families for at least foot, knee, palm, and forearm/elbow
- active manifold computation for those families
- authoritative support/terrain records
- primitive descriptors for contact, gait, and impedance actions
- affordance tags such as `standable`, `braceable`, and `catch_surface`
- eval coverage for staged contact targets and blocked/accepted route outcomes

Initial Pan behavior should be a proposal engine, not an autonomous animator:

- accept a contact intent
- generate one or more `workbench_set_pose_batch` proposals
- run `workbench_stage_contact`
- run balance/manifold checks
- return an explicit route report

Only later should successful route reports become runtime maneuver policies.

## Workflow DAG Leverage

The one-way state flow can be represented as a workflow graph when the system needs inspection, replay, or batch execution.

Important distinction:

- live mechanics stay native JS and must not be dispatched through the MCP workflow engine at frame rate
- workflows are for plans, debug recipes, rig sweeps, replay, and training-data generation after a live-operator-reviewed protocol exists

This gives the existing workflow engine a concrete role without moving it into the hot path.

### Pan Plans As Workflow Artifacts

When Pan ships, it should be able to emit a contact route as an executable workflow-shaped artifact:

- contact intent: place `lower_leg_l` on a support surface
- primitive nodes: unload, brace, pose proposal, stage contact, verify balance, accept or reject
- edges: each node depends on the state output of the previous safety gate
- result: a route report with accepted, blocked, or retry outcome

This keeps Pan inspectable:

- the proposed route can be shown before execution
- a failed route preserves the blocker report and upstream state
- a successful route can become a reusable maneuver template later
- agents can review the graph without reverse-engineering an opaque planner state

Code should still keep the primitive layer concrete.
The workflow graph is the inspection/execution artifact around the plan, not a replacement for contact math.

### Rig And Debug Workflows

The same pattern applies to non-frame-rate diagnostics, but not to blind automated pose sweeps:

- terrain slope sweeps can fan out across angles and merge reports
- gravity turntable runs can capture per-angle snapshots and assert balance-mode transitions
- debug recipes can instrument, perturb, capture, analyze, and report in one replayable sequence
- Dreamer data generation can later run scenario generation, execution, capture, reward, and export nodes

This is useful because it turns one-off scripts into replayable artifacts.
It should not replace live contact verification. Contact-placement scenarios need a live operator because bad automatic pose proposals can produce invalid body states faster than the substrate can explain them.

### DAG Design Questions

For any future blackboard row, route plan, eval workflow, or diagnostic panel, ask:

- what are the inputs?
- what is the output?
- who depends on it downstream?
- what invalidates its cached result?
- can it be tested in isolation with synthetic input?
- does it belong in the live frame path or the workflow/batch path?

### 4. Build the gravity turntable eval rig

This remains the best dynamic proving ground because it stress-tests:

- manifold truth
- support transfer
- balance-mode transitions
- primitive selection under changing gravity

It is not just a demo. It is a controller test instrument.

### 4.5 Separate movement truth from stage presentation

The grid/workbench panel should support multiple presentation modes without forcing multiple locomotion substrates.

Important rule:

- do not let a stage trick redefine mechanics truth
- contact/support/balance should remain the authoritative motion substrate
- treadmill scroll, torus-wrap, and camera-centering should be presentation-space policies over that same substrate

Recommended stage modes:

- `fixed_stage`
  - actor truly traverses the local panel space
- `treadmill_stage`
  - actor stays near a presentation anchor while the grid/support shell scrolls relative to it
  - good for sprint study, long runs, and compact demos
- `torus_wrap_stage`
  - actor crossing one panel edge re-enters from the opposite edge with preserved heading and motion continuity
  - visually Pac-Man-like, but should remain a deterministic coordinate remap rather than a physics discontinuity
- `gravity_rig_stage`
  - grid can stay visually static while `gravity_vector` changes
  - ideal for pure balance/recovery evaluation
- `tilted_support_stage`
  - support surface orientation/shape changes while gravity may remain fixed
  - better for cliff/hill/wall traversal studies

If seam-wrap is used with active support/balance logic, the remap must be atomic across:

- body root
- active contacts
- support-frame references
- support polygon anchors
- diagnostic consumers

That keeps the seam from becoming a fake balance fault.

### 5. Add object-affordance-driven traversal later

Only after the above is honest should the system learn/use:

- vaultable edges
- braceable walls
- crawlable spaces
- climbable holds

That is when the "reactive ninja" lane becomes real instead of aspirational.

## Affordance Contract

The environment layer should expose affordances as surface properties, not as ad hoc object-type exceptions.

The controller should not ask:

- "is this object a wall?"

It should ask:

- "is there a braceable surface within reach?"
- "is there a standable surface within step distance?"
- "is there a vaultable top edge ahead?"

### Surface metrics

These should be computed where possible:

- `surface_normal`
- `support_incline_degrees`
- `surface_area_m2`
- `min_span_m`
- `max_height_from_floor_m`
- `clearance_above_m`
- `friction_coefficient` later
- `deformation_compliance` later

### Surface tags

These can be authored, derived, or hybrid:

- `standable`
- `braceable`
- `vaultable`
- `crawlable`
- `climbable`
- `perchable`
- `catch_surface`
- `collapse_surface`

A single surface may satisfy multiple tags.

### Threshold rule

Do not treat the first numeric thresholds as timeless truth.

Examples like:

- incline less than 30 degrees
- minimum support span
- vaultable height ceilings
- crawlable clearance bands

should begin as tunable heuristics backed by observed behavior, not as universal doctrine.

### Why this matters

This is what lets the controller scale across:

- authored scenes
- generated terrain
- Coquina-produced environments
- future non-humanoid families

without inventing per-object special cases.

## What Opus Should Research Next

If deeper research bandwidth exists, it should go here:

1. whole-body support pose taxonomies for locomotion + manipulation
2. contact-conditioned policy representations for multi-gait and non-gait transitions
3. reactive whole-body control for multi-contact loco-manipulation
4. environment affordance tagging for traversal:
   - standable
   - braceable
   - vaultable
   - climbable
5. how learned controllers can consume a symbolic/structured blackboard without inventing a second state plane

## Bottom Line

The current repo is not drifting away from the "reactive ninja / traversal" idea.

It is approaching it from the correct side:

- first truthful contact
- then truthful support
- then truthful balance
- then reusable control primitives
- then aggressive mobility policies
- then dev-only visualization of the reasoning
- then clean product motion

The strongest version of this future is **not** a special stunt mode.

It is a unified reactive mobility stack where:

- every body part can become support when physically justified
- every maneuver is a composition of shared primitives
- every controller decision is grounded in real support/load truth
- every diagnostic surface reads the same shared contract
- product mode shows only believable motion, not the instrumentation used to build it
