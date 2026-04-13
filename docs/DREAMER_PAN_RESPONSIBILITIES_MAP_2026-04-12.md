# Dreamer / Pan / Substrate Responsibilities Map 2026-04-12

Repo: `F:\End-Game\champion_councl`

Purpose:

- draw clear ownership boundaries between every system in the Dreamer/Pan stack
- prevent responsibility overlaps and authority conflicts
- ground each boundary in verified source locations

Related docs:

- [DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md](DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md)
- [ENV_REPORT_SCHEMA_2026-04-11.md](ENV_REPORT_SCHEMA_2026-04-11.md)
- [PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md](PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md)
- [REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md](REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md)
- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md)

## Authority Rule

**One substrate, many aligned consumers.** The mechanics runtime in `static/main.js` is the single source of body truth. Every other system reads from it. No system writes to it except through `workbench_set_pose_batch` and `workbench_stage_contact`. No system invents a parallel truth.

## Active Execution Rule

For the active track, Dreamer is operationalized through environment-native association surfaces, not capsule edits. The authoritative association path is:

- server endpoints and control plane
- `env_help` and playbooks
- theater HUD and environment controls
- blackboard and text theater mirrors
- env_report and workflow/facility wrappers

The capsule remains fixed background infrastructure for this track.

## System Map

```
                    ┌─────────────┐
                    │  Operator /  │
                    │  User Input  │
                    └──────┬──────┘
                           │ intent
                           ▼
                    ┌─────────────┐
                    │     Pan     │  proposal / router
                    │  (FUTURE)   │
                    └──────┬──────┘
                           │ selects / applies corrections
                           ▼
                    ┌─────────────┐
                    │   Dreamer   │  proposer / scorer
                    │  (v1 NEXT)  │
                    └──────┬──────┘
                           │ reads observations, emits proposals
                           ▼
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │ env_report  │  │  Blackboard │  │ Text Theater │
  │  (broker)   │  │ (row pool)  │  │  (bridge)    │
  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
         │                │                 │
         └────────────────┼─────────────────┘
                          │ all read from
                          ▼
                ┌──────────────────┐
                │ Mechanics Runtime │  single source of truth
                │  (static/main.js) │
                └──────────────────┘
```

## Per-System Responsibilities

---

### 1. Mechanics Runtime (`static/main.js`)

**Role:** Single source of body truth. Computes pose state, contacts, balance, route evaluation, transition phase.

**Owns:**
- Bone transforms and pose state
- Contact manifold computation (`_envBuilderMotionContactTargets` at 2295)
- Balance solver with gravity_vector (`static/main.js:4114-4163`)
- Route report builder (`_envBuilderSupportRouteReport` at 3383)
- Transition template definition and evaluation (`_envBuilderHalfKneelTransitionTemplate` at 1482, `_envBuilderEvaluateTransitionSequence` at 3424)
- Contact stage gate (`_envWorkbenchStageContact` at 30136)
- Controller topology registry (`half_kneel_l_topology` at 5262)
- Pose macro registry (`_envBuilderBodyPlanPoseMacroRegistry` at 5334)
- Blackboard row pool builder (`_envBuildBlackboardState` at 31197)
- Profile registry builder (`_envBuildTextTheaterProfileRegistry` at 31033)

**Does NOT own:**
- Deciding what correction to apply (that is Pan/Dreamer)
- Diagnosing why a route is failing (that is env_report)
- Making observations legible to an operator (that is text theater)
- Proposing next actions (that is Dreamer)

**Write interface:** `workbench_set_pose_batch` (pose mutations), `workbench_stage_contact` (contact staging). These are the ONLY two write paths. Everything else is read.

**Boundary contract:** The runtime never consults Dreamer, Pan, or the broker. It computes truth from pose state and physics. It exposes `shared_state` for consumers.

---

### 2. Text Theater (`scripts/text_theater.py` + `static/main.js` profile/blackboard builders)

**Role:** Bridge medium between raw mechanics truth and operator/agent legibility. Three roles: observation (EXISTS), reasoning (NEXT), control (LATER).

**Owns:**
- Rendering `shared_state` into camera-projected text layouts
- Profile families: body_readout, contact_landscape, support_architecture, balance_state (first wave) + spatial_reasoning, controller_audit, environment_context (second wave)
- Embodiment text: the spatial narrative of current pose
- Snapshot: structured summary of current theater state
- Theater-first gate enforcement: `_env_shared_state_prereq_payload` at `server.py:3817` blocks raw shared_state reads until theater is fresh

**Does NOT own:**
- The underlying data (that is the mechanics runtime)
- Diagnosing route problems (that is env_report)
- Proposing corrections (that is Dreamer)
- Routing contact intents (that is Pan)

**Read interface:** consumes `shared_state.blackboard`, `shared_state.workbench`, `shared_state.text_theater`
**Write interface:** writes `shared_state.text_theater.snapshot` and `shared_state.text_theater.embodiment`

**Boundary contract:** Text theater is a consumer and renderer, never an authority. If theater text says one thing and `shared_state` says another, `shared_state` wins. The theater-first gate exists to force operators to LOOK before diving into raw state — it does not make theater authoritative.

---

### 3. Blackboard (`shared_state.blackboard`)

**Role:** Structured row pool for all diagnostic consumers. Same data, polymorphic rendering.

**Owns:**
- Row pool: 8 families (balance, contact, controller, corroboration, load, route, session, support) built by `_envBuildBlackboardState` at `static/main.js:31197`
- Working set: `lead_row_ids`, `intended_support_set`, `missing_support_set`, `supporting_joint_ids`, `active_controller_id`, `active_route_id`, `pinned_row_ids` at `static/main.js:31564`
- Session threading: the working_set anchors all consumers to the same session context
- Row traces: per-row `{t, value, label}` trend data

**Does NOT own:**
- How rows are rendered (that is text theater, env_report, or dev overlay)
- What to do about the values (that is Dreamer/Pan)
- Which rows matter most (that is working_set.lead_row_ids, set by the runtime)

**Consumers:**
- Text theater (primary visual consumer)
- env_report (primary diagnostic consumer)
- Dreamer (observation source)
- env_read (raw JSON for agents)

**Boundary contract:** Blackboard is a structured cache of live truth. It is rebuilt every frame from the mechanics runtime. It never persists across sessions (that is the bag/cascade layer). It never computes — it reflects.

---

### 4. env_report Broker (`server.py:4152+`)

**Role:** Read-side diagnosis. Stateless materializer that joins blackboard, route report, text theater, and corroboration into small, auditable, session-threaded reports.

**Owns:**
- Recipe dispatch table (`_ENV_REPORT_IDS` at `server.py:3890`)
- Report materialization: reading live `shared_state`, joining evidence paths, computing severity/designation/visual_read
- Size discipline: 8KB default, 24KB hard cap
- Error contract: stale, gate_blocked, missing, unavailable, recipe_error, unknown_report
- Session thread inclusion: every report echoes `session_thread` from `blackboard.working_set`
- `route_stability_diagnosis` recipe at `server.py:4152-4470`: severity (ok/watch/degraded/critical), designation (8 states), expected_vs_observed, failure_character, embodied_evidence_lines

**Does NOT own:**
- The underlying data (that is the mechanics runtime)
- The rendering of reports (that is text theater or agent UI)
- Proposing corrections (that is Dreamer)
- Executing corrections (that is Pan)
- Persisting reports (future slice: saved-report archive)

**Read interface:** reads `shared_state.blackboard`, `shared_state.workbench`, `shared_state.text_theater`
**Write interface:** NONE. The broker is strictly read-side.

**Boundary contract:** env_report is a stateless join, not a second truth plane. It never runs on the camera hot path. It never writes. It is a read-side companion to `env_read`.

---

### 5. env_help (`server.py:4823+`)

**Role:** Discoverability layer. Teaches operators and agents how to use the environment, what tools exist, what order to use them, what failure modes to expect.

**Owns:**
- Help registry: topic → help content mapping
- Playbooks: ordered sequences for common operations (e.g., "diagnose a stuck kneel")
- Working rules: behavioral guidance for agents (e.g., "theater first, then snapshot, then env_report, then shared_state")
- Tool discoverability: what env_read queries, env_report recipe ids, env_control commands, and env_mutate operations exist

**Does NOT own:**
- The tools themselves (those are in the MCP/server dispatch)
- The data (that is shared_state/blackboard)
- The diagnosis (that is env_report)
- The proposals (that is Dreamer)

**Boundary contract:** env_help is a reference layer. It describes what exists and how to use it. It does not execute, compute, or decide. When the help is wrong about what exists (stale), the help is wrong — the runtime is right. Help should be updated to match reality, not the reverse.

**Known drift (2026-04-12):** env_help does not yet teach `env_report` as a tool. Help still teaches `shared_state` reads as a routine verification step instead of gating them behind theater-first. See mismatch note.

---

### 6. Dreamer (Capsule Dreamer subsystem + outer control plane)

**Role:** Proposer/scorer. Consumes structured observations from the truthful substrate, proposes bounded corrections, and is scored by existing fields. In the active track, this means a fixed capsule Dreamer plus an outer server/environment control plane that configures, invokes, visualizes, and records Dreamer-related operations.

**Owns (v1):**
- Observation encoding: translating shared_state fields into a bounded observation vector
- Proposal generation: ranked corrections from a finite vocabulary
- Reward computation: scoring observation deltas against existing truth fields
- Confidence/evidence: self-reporting why it proposes what it proposes
- World model: RSSM that predicts observation deltas from proposed corrections

**Current implementation caveats (verified 2026-04-12):**
- Live `obs_buffer_size` is still `0`, so Dreamer is not yet consuming environment/mechanics observations.
- The current reward stream is still mostly generic tool/workflow/HOLD telemetry, not mechanics episodes.
- The current capsule world-model update stores an action slot in the obs buffer, but the phase-1 prediction loss does not yet consume `action_t`.
- The current Dreamer core is configured for `action_dim = 8`, so the first correction vocabulary should fit 8 actions.

**Does NOT own:**
- Body truth (that is the mechanics runtime)
- Diagnosis (that is env_report)
- Routing/approval (that is Pan)
- Execution (that is workbench_set_pose_batch, mediated by Pan)
- Observation surfaces (those are blackboard/route report/balance solver)
- Transition templates (those are the mechanics runtime)

**Boundary contract:** Dreamer reads truth and proposes corrections. It never writes to shared_state. It never bypasses Pan. It never replaces the truthful substrate. If Dreamer proposes something and the substrate says it made things worse, the substrate wins. The active extension surface for Dreamer is outside the capsule: help, theater, reports, workflows, and control-plane endpoints.

**Practical v1 reading:** Dreamer should begin as a bounded proposer/scorer over kneel/contact episodes, not as a freeform controller over the full environment.

---

### 7. Pan (FUTURE — not yet built)

**Role:** Proposal router / operator layer. Accepts contact intents, consults Dreamer for corrections, applies corrections through the workbench, evaluates results via route report.

**Will own:**
- Contact intent acceptance: parsing "achieve half_kneel_l" into a bounded routing problem
- Proposal selection: choosing which Dreamer proposal to apply (or rejecting all)
- Execution mediation: calling `workbench_set_pose_batch` and `workbench_stage_contact`
- Episode management: reset, step, evaluate, terminate
- Route planning: using the transition template as curriculum, advancing through phases
- Retry/abandon logic: when to retry a correction, when to abandon a route

**Will NOT own:**
- Body truth (mechanics runtime)
- Proposal generation (Dreamer)
- Diagnosis (env_report)
- Observation surfaces (blackboard/theater)
- Transition template definition (mechanics runtime)

**Boundary contract:** Pan is the outermost decision layer. It receives intent from operator or agent, delegates to Dreamer for proposals, executes through the workbench, and evaluates through the route report. Pan never invents truth. Pan never bypasses the staging gate. Pan never runs on the camera hot path.

**Prerequisite for Pan (from REACTIVE_MOBILITY_PRIMITIVES at line 700-710):**
- Candidate patch families for foot, knee, palm, forearm/elbow
- Active manifold computation
- Authoritative support/terrain records
- Primitive descriptors for contact, gait, impedance
- Affordance tags (standable, braceable, catch_surface)
- Eval coverage for staged contact targets

---

### 8. Transition Template System (`static/main.js:1482-1631`)

**Role:** Contact grammar. Defines phase sequences for topology transitions with per-phase contact plans, success criteria, and weight distribution.

**Owns:**
- Phase definitions: id, label, summary, time, support_phase, contacts, criteria
- Per-phase contact plans: which contacts should be in which state with which weight_bias
- Per-phase criteria: min_support_contacts, max_stability_risk, min_load_share, stage_not_blocked, require_realized_targets, support_role
- Template-to-macro linkage: `_envBuilderTransitionTemplateForMacro` connects macros to templates

**Consumed by:**
- Route report builder (via `_envBuilderEvaluateTransitionSequence` at 3424)
- env_report broker (reads phase evaluation from route report)
- Dreamer (as curriculum — phase criteria are reward targets)
- Pan (as routing plan — phase sequence defines execution order)

**Boundary contract:** The transition template is authored content, not computed. It defines WHAT the phases are and WHEN they succeed. It does not execute corrections — that is Dreamer/Pan. It does not diagnose failures — that is env_report. It is the syllabus, not the student or the teacher.

This is the **key architectural insight**: the transition template system already implements most of the proposed "contact grammar" from the contact-first authoring discussions. Both Dreamer and Pan should build on top of it, not reinvent it.

---

### 9. Tinkerbell (FUTURE — not yet built)

**Role:** Spatial awareness / prospect / attention layer. Points at things. Determines where to look, what to attend to, what is relevant in the spatial field.

**Will own:**
- Spatial prospect evaluation: what surfaces, contacts, affordances are available
- Attention routing: directing Pan's focus to the most relevant contact opportunity or stability problem
- Observer anchoring: maintaining a stable viewpoint/attention frame during maneuvers

**Will NOT own:**
- Route planning (that is Pan)
- Correction proposals (that is Dreamer)
- Body truth (that is the mechanics runtime)
- Diagnosis (that is env_report)

**Boundary contract:** Tinkerbell points. Pan routes. They are a perception-versus-embodiment control decomposition. Tinkerbell does not move the body — it identifies where the body should move. Pan consumes Tinkerbell's spatial reads and translates them into contact intents.

**Mnemonic:** Tinkerbell points. Pan routes. Dreamer scores.

---

### 10. Workflow Engine (capsule-side, `champion_gen8.py:14283+`)

**Role:** DAG-based automation executor. Chains any MCP tool as a workflow node. Used for plans, debug recipes, rig sweeps, replay, and training-data generation — never on the camera hot path.

**Owns:**
- Workflow definition storage (in FelixBag as `workflow:{id}`)
- DAG execution with 10 node types: tool, agent, input, output, fan_out, http, if, set, merge, web_search
- Execution history and reproducibility
- Agent nodes with granted tools, bounded iterations, ecosystem context

**Does NOT own:**
- Live mechanics computation (that is the mechanics runtime)
- Real-time contact evaluation (that is workbench_stage_contact)
- Diagnosis (that is env_report)
- Correction proposals (that is Dreamer)

**Relation to Dreamer:** Workflows can orchestrate Dreamer episodes for batch evaluation — e.g., a workflow that runs 50 correction episodes against half_kneel_l, captures results, and reports. But the workflow does not replace the episode loop; it wraps it. Dreamer data generation (training scenario replay, rig sweeps) should use workflow nodes, not ad-hoc scripts.

**Boundary contract:** Workflows are for orchestration, inspection, replay, and batch execution. They must not replace the live correction loop. They must not move onto the camera hot path. A workflow that calls `workbench_set_pose_batch` is fine for offline evaluation but must not pretend to be a real-time controller.

---

### 11. Facility System (capsule-side, `champion_gen8.py`)

**Role:** Named production/reasoning environment blueprints. A facility is an activated context with bound resources, tools, and purpose. Both a production substrate AND an AI reasoning facility.

**Owns:**
- Facility definition: blueprint with bound workstations, tools, constraints
- Facility activation: loading the context into an operational state
- Facility binding: connecting resources (models, data, tools) to the facility
- Named purposes: a facility for "kneel correction evaluation" vs "gravity rig balance testing" vs "Coquina body authoring"

**Does NOT own:**
- The tools themselves (those are MCP tools)
- The data (that is shared_state, bag, CASCADE)
- The diagnosis (that is env_report)
- The corrections (that is Dreamer/Pan)

**Relation to Dreamer:** When Dreamer evaluates a specific task (half_kneel_l), the episode should run inside a named facility with bound constraints. The facility defines the evaluation context: which corrections are allowed, which reward thresholds apply, what safety gates exist. Dreamer proposes within the facility's bounds.

**Boundary contract:** Facilities are containers, not actors. They define context, they do not execute. A facility activated for kneel evaluation says "you may use these 8 corrections, this reward function, these safety gates." It does not run the evaluation itself.

---

### 12. CASCADE System (capsule-side, `champion_gen8.py:12279+`)

**Role:** Merkle-linked provenance, event logging, and accountability chain. Every tool call, observation, and state change can be recorded with a content-addressed receipt.

**Owns:**
- Event recording: timestamped, hashed observations via `observe()`
- Event feed: recent event retrieval via `feed()`
- Provenance chains: `cascade_chain` for merkle-authenticated sequences
- Provenance graph: `cascade_graph` for causal relationship tracking
- Instrumentation: `cascade_instrument` for monitoring setup

**Does NOT own:**
- The events themselves (events come from tool calls, Dreamer episodes, etc.)
- Dreamer's `_obs_buffer` — CASCADE's `_observations` list is separate from Dreamer's training buffer
- Diagnosis (that is env_report)
- The truthful substrate (that is the mechanics runtime)

**Critical distinction:** CASCADE's `observe()` writes to `agent._observations` (event log). Dreamer's `_obs_buffer` is fed during `_full_brain_inference()` at `champion_gen8.py:7234`. These are **separate systems**. Calling `observe()` does NOT feed Dreamer's world model. This matters for the Dreamer wiring plan.

**Relation to Dreamer:** CASCADE provides the audit trail for Dreamer episodes. Every correction proposed, applied, scored, and its resulting state change should be logged to CASCADE for provenance. But CASCADE does not train Dreamer — only `_obs_buffer` does that. CASCADE is the journal; Dreamer's obs_buffer is the training set.

**Boundary contract:** CASCADE records. It does not compute, propose, or decide. It provides provenance so that any Dreamer episode can be traced, replayed, and audited after the fact.

## Data Flow Summary

```
Operator intent
    │
    ▼
Pan (routes, selects corrections)         ◄── FUTURE
    │
    ├── asks Dreamer for proposals
    │       │
    │       ▼
    │   Dreamer (reads obs, proposes)     ◄── v1 NEXT
    │       │
    │       ├── reads route_report        ◄── EXISTS (main.js:3383)
    │       ├── reads contacts            ◄── EXISTS (main.js:2295)
    │       ├── reads balance             ◄── EXISTS (main.js:4114)
    │       ├── reads transition phase    ◄── EXISTS (main.js:3424)
    │       ├── reads blackboard rows     ◄── EXISTS (main.js:31197)
    │       ├── reads env_report digest   ◄── EXISTS (server.py:4152)
    │       └── reads embodiment text     ◄── EXISTS (text_theater.py)
    │
    ├── applies correction via workbench_set_pose_batch
    │       │
    │       ▼
    │   Mechanics Runtime (recomputes)    ◄── EXISTS (main.js)
    │       │
    │       ├── updates contacts
    │       ├── updates balance
    │       ├── updates route report
    │       ├── updates blackboard
    │       └── updates text theater
    │
    └── re-reads route report → decides continue / retry / abandon
```

## Overlap Prevention Rules

1. **Only one write path:** `workbench_set_pose_batch` and `workbench_stage_contact`. No system invents alternative mutation lanes.
2. **Only one truth source:** the mechanics runtime. Blackboard, theater, env_report, Dreamer observations, and CASCADE logs are all derived from it.
3. **Only one diagnosis authority:** env_report. Text theater renders, blackboard stores rows, but env_report is where fused diagnosis lives.
4. **Only one proposal authority:** Dreamer. Pan routes and selects, but Dreamer generates the scored proposals.
5. **Only one routing authority:** Pan. Operators and agents talk to Pan, not directly to Dreamer or the workbench (once Pan exists).
6. **Only one discoverability authority:** env_help. Not scattered across docs, not embedded in error messages.
7. **Only one contact grammar:** the transition template system. Not reinvented in Dreamer, not duplicated in Pan.
8. **Only one attention authority:** Tinkerbell. Pan routes where Tinkerbell points — Pan does not also scan the spatial field.
9. **Only one provenance authority:** CASCADE. Dreamer episodes, workflow runs, and facility activations all log through CASCADE — they do not maintain separate audit trails.
10. **Only one orchestration authority:** Workflow engine. Batch evaluation, rig sweeps, and training-data generation use workflow DAGs — they do not use ad-hoc scripts or direct loop code in the server.
11. **Only one evaluation context authority:** Facility system. A Dreamer episode's constraints (allowed corrections, reward thresholds, safety gates) are defined by the active facility — not hard-coded in the episode loop.
12. **Two separate observation stores:** CASCADE `_observations` (event journal, audit) vs Dreamer `_obs_buffer` (world model training). Do not confuse them. Calling `observe()` does NOT feed Dreamer. Only the brain inference path feeds `_obs_buffer`.

## Summary

Twelve systems, clear boundaries, twelve overlap prevention rules. The mechanics runtime owns truth. Text theater renders it. Blackboard structures it. env_report diagnoses it. Dreamer proposes corrections. Pan routes them. Tinkerbell points attention. env_help teaches navigation. Transition templates define the contact grammar. Workflows orchestrate batch evaluation. Facilities define evaluation contexts. CASCADE provides provenance. One substrate, many aligned consumers.
