# Dreamer v1 Operationalization Plan 2026-04-12

Repo: `F:\End-Game\champion_councl`

Purpose:

- pin the Dreamer v1 observation/action/reward contract over the existing truthful substrate
- define the first bounded evaluation problem (half_kneel_l)
- keep Dreamer as a scorer/proposer, not a raw pose generator
- avoid speculative rewrites — everything referenced here EXISTS in source today

## Active Execution Rule

This document still describes the full Dreamer v1 contract, including capsule-side limitations for orientation. The active execution track, however, is server/environment/theater only. Any capsule-related section below is explanatory context, not an approved implementation step.

Related docs:

- [ENV_REPORT_SCHEMA_2026-04-11.md](ENV_REPORT_SCHEMA_2026-04-11.md) — env_report contract
- [REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md](REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md) — Pan definition, stage modes
- [PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md](PAN_TINKERBELL_EMBODIED_AUTONOMY_POSITIONING_2026-04-10.md) — autonomy positioning
- [HUMANOID_CONTACT_AND_MOBILITY_PRIORS_2026-04-10.md](HUMANOID_CONTACT_AND_MOBILITY_PRIORS_2026-04-10.md) — biomechanics priors
- [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md) — blackboard as Dreamer observation source

## Bottom Line

Dreamer v1 is a **bounded proposer/scorer** over the existing truthful environment substrate. It does not generate raw poses from scratch. It consumes live structured observations from surfaces that already exist, proposes small corrections from a finite action vocabulary, and is scored by fields that are already computed every frame. Its first evaluation problem is `half_kneel_l` — a single contact topology with a known failing state and a clear success criterion.

## Capsule Status (Verified 2026-04-12)

| Field | Value | Meaning |
|---|---|---|
| `dreamer.active` | `true` | Dreamer subsystem is loaded |
| `dreamer.has_real_rssm` | `true` | Real recurrent state-space model, not a stub |
| `dreamer.training_cycles` | 196 | Has been trained, but lightly |
| `dreamer.reward_count` | 6302 | Reward signals received |
| `dreamer.obs_buffer_size` | 0 | **Not receiving observations from the environment** |
| `generation` | 8 | Capsule generation |
| `slots_plugged` | 0 / 32 | No model slots occupied |

**Critical gap:** Dreamer is baked in and real but starving. `obs_buffer_size = 0` means no environment observation is flowing to it. The entire v1 program is about wiring a bounded observation feed and getting signal from the existing substrate.

## Current Hard Blockers (Verified In Capsule Source)

The current Dreamer loop is real, but three implementation facts constrain the first strike:

1. **Observation starvation**
   - Live `get_status()` still reports `obs_buffer_size = 0`.
   - Dreamer is not currently receiving environment/mechanics observations.

2. **Reward pollution**
   - The live reward stream is still dominated by generic events like `tool_success`, `workflow_success`, and HOLD outcomes.
   - Those rewards teach Dreamer about generic capsule/tool usage, not kneel/contact mechanics.

3. **Action-conditioning seam**
   - The capsule currently stores `(obs_t, action_t, obs_t+1)`-like triples, but the world-model loss in `_train_step()` does not actually consume `action_t` during the next-state prediction pass.
   - This means that simply populating the obs buffer is not enough to teach Dreamer "which correction caused which state transition."

4. **8-action ceiling**
   - The existing Dreamer RSSM is configured with `action_dim = 8`.
   - Dreamer v1 should fit the first correction vocabulary into those 8 actions instead of immediately widening the action space.

These are not reasons to abandon Dreamer. They are the real constraints that the docs should stay honest about.

## Observation Inputs (All Exist Today)

Every observation input below is a field that the runtime already computes and exposes through `shared_state`, `blackboard`, `text_theater`, or `env_report`. Dreamer v1 consumes these read-only — it never writes to them.

### Primary: Route Report

Source: `shared_state.workbench.route_report` — built by `_envBuilderSupportRouteReport` at `static/main.js:3383`.

| Field | Source path | What it tells Dreamer |
|---|---|---|
| `intended_support_set` | `route_report.intended_support_set` | What contacts SHOULD be supporting |
| `realized_support_set` | `route_report.realized_support_set` | What contacts ARE supporting |
| `missing_support_participants` | `route_report.missing_support_participants` | Gap between intent and reality |
| `blocker_summary` | `route_report.blocker_summary` | Why the route is stuck |
| `next_suggested_adjustment` | `route_report.next_suggested_adjustment` | Substrate's own suggestion |
| `operational_state` | `route_report.operational_state` | Classified route health |
| `stage_blocked` | `route_report.stage_blocked` | Whether contact staging is blocked |
| `stage_reason` | `route_report.stage_reason` | Why staging is blocked |

### Primary: Transition Phase

Source: `shared_state.workbench.route_report` phase fields — derived from `_envBuilderEvaluateTransitionSequence` at `static/main.js:3424`, consuming the 6-phase transition template at `static/main.js:1505-1631`.

| Field | Source path | What it tells Dreamer |
|---|---|---|
| `active_phase_id` | `route_report.active_phase_id` | Current phase in the 6-phase sequence |
| `active_phase_label` | `route_report.active_phase_label` | Human-readable phase name |
| `phase_sequence` | `route_report.phase_sequence` | All phases with pass/fail per criterion |
| `phase_gate_summary` | `route_report.phase_gate_summary` | What criteria are failing for the current phase |

The transition template already defines per-phase: `weight_bias`, `support_role` (plant vs brace), `min_load_share`, `max_stability_risk`, `min_support_contacts`, `stage_not_blocked`, and `require_realized_targets`. Dreamer's reward function can directly reference these thresholds.

### Primary: Contact Realization

Source: `shared_state.workbench.motion_diagnostics.contacts` — per-contact-target rows.

| Field | Per-row | What it tells Dreamer |
|---|---|---|
| `supporting` | bool | Is this contact currently load-bearing |
| `gap` | float | Distance from contact surface to support plane |
| `manifold_points` | int | Number of contact manifold intersections |
| `state` | string | Contact state (planted, lifting, approach, brace, etc.) |
| `load_share` | float | Fraction of body weight on this contact |

### Secondary: Balance Truth

Source: `shared_state.workbench.motion_diagnostics.balance` — computed by the balance solver at `static/main.js:4114-4163` using `gravity_vector`.

| Field | Source path | What it tells Dreamer |
|---|---|---|
| `stability_risk` | `balance.stability_risk` | 0–1, how close to falling |
| `stability_margin` | `balance.stability_margin` | Signed distance from CoM projection to nearest support edge |
| `balance_mode` | `balance.balance_mode` | supported / braced / falling / free_float |
| `nearest_edge_bone_id` | `balance.nearest_edge_bone_id` | Which support boundary is closest to failure |

### Secondary: Controller Topology

Source: `shared_state.workbench.active_controller` — from `half_kneel_l_topology` at `static/main.js:5262-5275`.

| Field | Source path | What it tells Dreamer |
|---|---|---|
| `leader_bone_ids` | `active_controller.leader_bone_ids` | What bone is driving the topology (`lower_leg_l`) |
| `anchor_bone_ids` | `active_controller.anchor_bone_ids` | What is planted (`foot_r`) |
| `carrier_bone_ids` | `active_controller.carrier_bone_ids` | What carries the chain (`hips`) |
| `compensation_bone_ids` | `active_controller.compensation_bone_ids` | What compensates |

### Tertiary: Text Theater + Blackboard

Source: `shared_state.text_theater.embodiment` and `shared_state.blackboard.rows`.

- Embodiment text: provides a spatial narrative of the current pose state — Dreamer can use it for grounding but should not parse it as primary truth.
- Blackboard rows: 8 families (balance, contact, controller, corroboration, load, route, session, support). Dreamer reads the same rows that `env_report` reads. The working_set's `lead_row_ids` and `intended_support_set` are the session-threading anchor.

### Tertiary: env_report Digest

Source: `env_report(report_id='route_stability_diagnosis')` at `server.py:4152-4470`.

When available, this provides a pre-fused digest: `severity`, `designation`, `visual_read`, `expected_vs_observed`, `failure_character`, `embodied_evidence_lines`. Dreamer can use the env_report as a compressed observation rather than reading all raw fields individually.

## Action Space (Bounded, Legible, 8-Action First Strike)

Dreamer v1 does NOT emit opaque pose tensors. It proposes **named corrections** from a finite vocabulary. Each correction maps to an existing `workbench_set_pose_batch` operation that the runtime already knows how to execute.

### Correction Vocabulary (Fits Existing `action_dim = 8`)

| Action | Target bones | What it does | When to propose |
|---|---|---|---|
| `drop_hips` | `hips` | Lower hips offset.y by a small delta | CoM too high, knee gap too large |
| `raise_hips` | `hips` | Raise hips offset.y by a small delta | Kneel overshoots or penetrates |
| `shift_hips_fore` | `hips` | Move hips offset.z forward | CoM behind support polygon |
| `shift_hips_aft` | `hips` | Move hips offset.z backward | CoM too far forward |
| `counter_rotate_spine` | `spine` | Pitch spine to compensate for hips tilt | Upper body falling forward/back |
| `counter_rotate_chest` | `chest` | Pitch chest to compensate for spine | Fine-tune upper body balance |
| `tuck_lead_knee` | `lower_leg_{lead}` | Increase lead knee bend slightly | Knee gap too large, approach angle wrong |
| `yaw_planted_foot` | `foot_{anchor}` | Rotate planted foot yaw slightly | Support polygon misaligned / anchor wrong-way |

Each action includes:
- **direction**: positive or negative (e.g., drop vs raise hips)
- **magnitude**: small / medium / large (maps to fixed deltas defined in the correction table)
- **confidence**: Dreamer's own estimate of whether this helps

This is deliberately narrow. It matches the current `action_dim = 8` instead of forcing a larger action vocabulary before the action-conditioning seam is repaired.

### Proposal Format

Dreamer emits an ordered list of 1–10 proposals:

```
{
  "proposals": [
    {
      "action": "drop_hips",
      "direction": "negative_y",
      "magnitude": "medium",
      "confidence": 0.82,
      "expected_effect": "Reduce lower_leg_l gap from 0.14 to ~0.06",
      "evidence": ["route_report.missing_support_participants includes lower_leg_l", "balance.stability_risk = 1.0"],
      "reward_prediction": { "gap_delta": -0.08, "stability_delta": -0.15, "manifold_delta": +2 },
      "truth_gate": "After applying, check: contact[lower_leg_l].gap < 0.08 AND balance.stability_risk < 0.85"
    },
    ...
  ]
}
```

Every proposal names:
1. what it wants to do (action + direction + magnitude)
2. why (evidence from observations)
3. what it expects to happen (reward_prediction)
4. what truth gate will confirm or reject it (truth_gate)

This is legible. An operator or Pan can read, approve, reject, or reorder proposals without understanding Dreamer's internals.

## Reward Function (Derived From Real Fields)

Every reward signal comes from fields that the runtime already computes. Dreamer v1 does not need custom instrumentation — it scores against existing truth.

### Positive Rewards (things getting better)

| Signal | Source | Weight | Formula |
|---|---|---|---|
| Gap decrease | `contact[target].gap` | high | `prev_gap - curr_gap` (positive = good) |
| Support realization | `route_report.realized_support_set` | high | `+1.0` per newly realized intended contact |
| Manifold increase | `contact[target].manifold_points` | medium | `curr_manifold - prev_manifold` (positive = good) |
| Stability improvement | `balance.stability_risk` | high | `prev_risk - curr_risk` (positive = good) |
| Margin improvement | `balance.stability_margin` | medium | `curr_margin - prev_margin` (positive = good) |
| Phase advance | `route_report.active_phase_id` | high | `+2.0` per phase advanced in the transition sequence |
| Contact alignment | `contact[target].state` matching template | medium | `+0.5` when contact state matches phase expectation |

### Negative Rewards (things going wrong)

| Signal | Source | Weight | Formula |
|---|---|---|---|
| Penetration | `stage_report.blocked_by_penetration` | critical | `-3.0` per penetrating patch |
| Inversion | bone orientation checks | critical | `-2.0` per inverted joint |
| Stage blocked | `route_report.stage_blocked` | high | `-1.5` when staging becomes blocked |
| Brace collapse | `balance.balance_mode == 'falling'` | critical | `-4.0` when balance mode degrades to falling |
| Regression | any positive signal going backward | medium | `-1.0 * magnitude_of_regression` |

### Terminal Conditions

| Condition | Signal | Outcome |
|---|---|---|
| Route realized | `route_report.operational_state == 'route_realized'` + `balance.stability_risk < 0.72` | **SUCCESS** — episode ends, large positive reward |
| Brace collapse | `balance.balance_mode == 'falling'` for 3+ consecutive steps | **FAILURE** — episode ends, large negative reward |
| Max steps | 50 corrections without terminal | **TIMEOUT** — episode ends, small negative reward |

## First Evaluation Problem: half_kneel_l

### Why This Problem

1. **Known failing state**: `lower_leg_l` remains lifting while `foot_r` is the only support. The runtime already diagnoses this via the route report.
2. **Bounded scope**: 2 contact targets, 1 topology, 6-phase transition sequence. Small enough for v1.
3. **Existing transition template**: `_envBuilderHalfKneelTransitionTemplate('left')` at `static/main.js:1482-1631` already defines all 6 phases with explicit criteria. Dreamer can score against these criteria directly.
4. **Known fix direction**: The newer 9-bone seed at `static/main.js:5312-5331` includes hips drop (-0.12y), spine (-6°), chest (-8°) compensation. Dreamer should be able to discover similar corrections.
5. **env_report recipe exists**: `route_stability_diagnosis` at `server.py:4152-4470` already fuses the relevant observations into a digest.

### Episode Structure

1. **Reset**: Load the `half_kneel_l` macro with the current (possibly failing) pose seed
2. **Observe**: Read route report, contact state, balance state, phase evaluation
3. **Propose**: Dreamer emits 1–10 bounded corrections
4. **Execute**: Apply top-ranked correction via `workbench_set_pose_batch`
5. **Re-evaluate**: Read updated route report, compute reward deltas
6. **Repeat** until terminal condition

### Success Criteria (From Transition Template Phase 6: Stabilize)

- `foot_r` supporting with `support_role = 'plant'`
- `lower_leg_l` supporting with `support_role = 'brace'`, `min_load_share = 0.12`
- `min_support_contacts = 2`
- `support_phase = 'braced_support'`
- `require_realized_targets = true`
- `stage_not_blocked = true`
- `max_stability_risk = 0.72`

These are already defined in the transition template at `static/main.js:1619-1628`. Dreamer does not need to invent success criteria — it reads them from existing source.

## Implementation Sequence

### Phase A: Observation Wiring (prerequisite)

Wire a bounded observation schema from existing surfaces into the capsule's Dreamer obs buffer. This is the minimum work needed to get `obs_buffer_size > 0`.

Required observations:
1. Route report summary (intended/realized/missing support, operational_state, phase_id, phase_gate)
2. Per-contact-target state (gap, manifold_points, supporting, state, load_share) for the 2 targets in the half_kneel_l topology
3. Balance summary (stability_risk, stability_margin, balance_mode)
4. Controller topology roles (leader, anchor, carrier, compensation bone ids)

Encoding: flat numeric vector with named slots. Not a raw JSON dump.

### Phase B: Correction Table

Define the correction-to-pose-batch mapping. Each of the 8 actions above maps to a concrete `workbench_set_pose_batch` payload.

Do **not** start by expanding to 18+ discrete actions. The current Dreamer core is configured for 8 actions, and the first strike should fit that constraint.

### Phase C: Reward Wiring

Wire the reward function over the observation delta between consecutive steps. Use the weights and formulas from the reward table above. No custom instrumentation — everything is already computed.

Important constraint:

- mechanics rewards should not simply disappear into an undifferentiated generic reward stream
- either filter training to mechanics-tagged reward events during kneel eval episodes, or add a scoped evaluation mode so generic tool/workflow rewards do not dominate the signal

### Phase D: Evaluation Loop

Run episodes against the `half_kneel_l` problem:
1. Reset pose to failing seed
2. Dreamer observes, proposes, correction applied, re-observe, score
3. Log proposals, rewards, terminal outcomes
4. Evaluate: does Dreamer converge to route_realized within 50 steps?

### Phase E: Action-Conditioning Repair

The current world-model training path stores an action slot but does not use `action_t` when computing the world-model prediction loss.

That means the first strike can begin as:

- bounded observation feed
- bounded reward feed
- episode-step endpoint
- ranked proposals

But a stronger Dreamer v1 will eventually need a small capsule repair so the world model actually learns action-conditioned mechanics transitions rather than pure observation transitions.

### Phase F: Legibility Pass

After Dreamer produces proposals that work, verify:
- Every proposal cites real evidence from the observation
- Every truth_gate can be checked by re-reading the same observation fields
- The operator can read the top-3 proposals and understand why they were ranked
- env_report can render Dreamer's top proposal as part of its `recommended_next_reads`

## What Dreamer v1 Is NOT

- **Not a raw pose generator.** It proposes named corrections, not arbitrary joint angles.
- **Not autonomous.** Proposals must be approved (by Pan, operator, or auto-accept policy).
- **Not a replacement for the truthful substrate.** It reads truth, does not create it.
- **Not a general-purpose planner.** v1 solves one problem (half_kneel_l). Generalization is v2+.
- **Not magic.** If the correction vocabulary is too narrow, it will fail. Expand vocabulary based on failure analysis, not speculation.

## Relation To Pan

Pan is the **router/operator** layer. Dreamer is the **proposer/scorer** layer. They compose:

1. Pan receives a contact intent (e.g., "achieve half_kneel_l")
2. Pan reads the current route report and transition phase
3. Pan asks Dreamer for ranked corrections given current observations
4. Pan applies the top correction (or rejects and asks for alternatives)
5. Pan re-reads the route report and decides whether to continue, retry, or abandon

Dreamer never bypasses Pan. Pan never bypasses the truthful substrate. The substrate never lies.

## First-Strike Interpretation

The first strike does **not** require a perfect final Dreamer architecture.

It requires:

1. real mechanics observations in the obs path
2. real mechanics rewards in the reward path
3. a bounded 8-action correction vocabulary
4. a server-side episode step that lets Pan/operator evaluate the resulting proposals

That is enough to get a meaningful first result. The later action-conditioned world-model repair improves the quality ceiling; it does not invalidate the first bounded operational pass.

## Relation To Existing Transition Template

The transition template at `static/main.js:1482-1631` is the existing **contact grammar**. It already defines:
- 6 phases with ordered progression (unload → swing_clear → approach → contact → load_transfer → stabilize)
- Per-phase contact plans with plant/brace roles and weight_bias
- Per-phase success criteria with numeric thresholds

Dreamer v1 should treat the transition template as **curriculum** — the phase sequence tells it what to solve next, the criteria tell it when it has solved it. Dreamer does not need to invent the phase sequence. It needs to propose corrections that advance the current phase toward its criteria.

This is the key architectural insight: the transition template is the syllabus, Dreamer is the student, Pan is the teacher who decides when to advance or retry.

## Open Questions (Deferred)

1. **Observation encoding format** — flat vector vs structured dict. Defer to Phase A implementation.
2. **Training data generation** — workflow DAG for batch episode generation. Defer to after Phase D eval.
3. **Multi-topology generalization** — half_kneel_r, double_kneel, crouch, sit_rest. Defer to v2.
4. **Dreamer-to-Pan proposal format** — exact JSON schema. Defer to Pan implementation.
5. **RSSM architecture updates** — whether the existing 196-cycle RSSM needs retraining from scratch or can be fine-tuned. Defer to Phase A findings.

## Summary

Dreamer v1 is a bounded proposer that consumes existing truthful observations, proposes named corrections from a finite vocabulary, and is scored by fields that are already computed. Its first problem is `half_kneel_l`. It reads the transition template as curriculum, the route report as observation, the balance solver as ground truth, and the env_report as compressed digest. It does not replace the substrate. It does not bypass Pan. It does not generate magic. It proposes, and the substrate verifies.
