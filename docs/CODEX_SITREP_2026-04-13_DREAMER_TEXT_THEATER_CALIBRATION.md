# Codex Sitrep 2026-04-13

Repo: `F:\End-Game\champion_councl`

Purpose:

- hand Opus a grounded state report after the latest Dreamer outer-loop work
- corroborate which user hypotheses are already true in source/runtime
- pin the next trajectory around calibration, text-theater-first query flow, and Dreamer role boundaries

## 1. Core corroborated truths

### 1.1 Text-theater-first shared-state gate is real and active

Verified in `server.py`:

- `_env_shared_state_prereq_payload` at `3850`
- gate error code / sequence at `3878-3898`
- theater reads record the gate at `_env_note_text_theater_read` / `5985-5986`

Current behavior:

- raw `shared_state` access is blocked until the readable lane is used first
- required order is explicitly:
  1. `env_read(query='text_theater_embodiment')`
  2. `env_read(query='text_theater_snapshot')`
  3. `env_report(...)`
  4. `env_read(query='shared_state')` last

This matches the doctrine and is not hypothetical.

### 1.2 env_help already teaches much of this, but can be sharpened

Verified in:

- `server.py` builtin topics:
  - `env_report` topic around `3929+`
  - `dreamer_control_plane` at `3976+`
  - `dreamer_mechanics_obs` at `4050+`
- `static/data/help/environment_command_registry.json`
  - repeated text-theater-first guidance
  - repeated note that env_control results attach paired text-theater observation

Current truth:

- help already strongly teaches text-theater-first
- help already associates Dreamer to environment-native surfaces
- remaining need is not invention, but a more explicit calibration/query playbook

### 1.3 Blackboard is real in doctrine and source contracts, but still not the main operator product surface

Verified in docs:

- `OPUS_REACCLIMATION_SITREP_2026-04-11.md`
- `TEXT_THEATER_CASCADE_DIAGNOSTIC_SURFACES_2026-04-11.md`
- `COMMERCIALIZATION_MAP_2026-04-11.md`

Verified in source:

- `server.py` report/help paths refer to:
  - `shared_state.blackboard`
  - `shared_state.blackboard.rows`
  - `shared_state.blackboard.working_set`
  - `shared_state.text_theater.snapshot`
- `server.py:4207+`, `4313+`, `4338+`, `4649+`

Current truth:

- blackboard exists as a structured collation contract
- it is not yet the fully realized front-and-center operator product
- it remains the intended bridge between mechanics truth, text theater, and future query/oracle surfaces

### 1.4 Dreamer is operational as an outer loop, not yet a finished oracle

Verified live:

- `/api/dreamer/state`
- `/api/dreamer/proposal_preview`
- `/api/dreamer/mechanics_obs`
- `/api/dreamer/episode_step`

Current live facts:

- Dreamer is active and the RSSM is real
- mechanics observation packer is live
- proposal preview is live
- bounded episode step is live
- server-side mechanics reward / episode history is live
- `obs_buffer_size` remains `0`

Meaning:

- Dreamer can currently observe, rank, dispatch bounded corrections, and score outcomes through the outer control plane
- Dreamer is not yet a trustworthy oracle in the stronger sense because the inner buffer path still does not reflect mechanics observations

## 2. Calibration findings from live eval

### 2.1 The baseline changed from the old failing knee-gap state

Current restored `half_kneel_l` baseline from live mechanics observation:

- `lower_leg_l.gap = 0.0`
- `lower_leg_l.supporting = true`
- `foot_r.supporting = true`
- `support_count = 2`
- `stability_margin = -0.6129`
- `stability_risk = 1.0`
- `hips_pitch_deg = 8.0`
- `spine_pitch_deg = -6.0`
- `chest_pitch_deg = -8.0`
- `lower_leg_l_pitch_deg = 120.0`
- `foot_r_yaw_deg = 6.0`
- route status still reports:
  - `active_phase_id = unload`
  - `phase_gate_summary = stability risk 1.00 > 0.96`

So the active problem is no longer "knee lifting with large open gap." It is now a braced, two-contact posture with poor stability margin and unresolved route progress.

### 2.2 The first tuning cycle proved one positive action

Using a true baseline restore before each test:

- `tuck_lead_knee` produced positive reward:
  - `total_reward = 0.0725`
  - driven by `margin_gain`
  - moved `stability_margin` from `-0.6129` to `-0.5163`
- repeated knee tuck then degraded:
  - second step reopened gap slightly and became net negative

Interpretation:

- knee tuck is useful as a bounded stabilizer
- it is not a spam action

### 2.3 Several actions are currently dead or counterproductive

Single-step eval from the restored baseline:

- `widen_anchor_foot`:
  - real foot yaw change from `6` to `14`
  - net negative due to manifold loss
- `counter_rotate_spine`:
  - net negative on margin
- `counter_rotate_chest`:
  - net negative on margin
- `drop_hips`, `raise_hips`, `shift_hips_fore`, `shift_hips_aft`:
  - currently no observed mechanics change from the restored baseline

Interpretation:

- the foot action is live but not currently beneficial
- upper-body compensation actions are measurable but presently harmful
- root/carrier offset actions are dispatching but are effectively no-ops in observed mechanics from this baseline

### 2.4 The user's "carrier / knee behind the torso line" hypothesis is plausible

This is supported by the live pattern:

- the knee is already grounded
- margin is still poor
- further knee tuck helps once, then starts reopening gap
- foot widening does not solve the body-line problem
- upper-body counter-rotation worsens margin

This points toward a carrier-chain / support-line alignment issue rather than a simple missing-contact issue.

## 3. Dreamer role corroboration

The user’s intended role for Dreamer is mostly aligned with the actual stack:

- good immediate role:
  - evaluator
  - proposer
  - scorer
  - calibration assistant
  - query/orientation assistant after text-theater-first intake
- not yet justified:
  - strong oracle for automatic repositioning
  - direct truth authority
  - replacement for Pan

So the best current description is:

Dreamer is a bounded outer-loop evaluator/proposer over the truthful environment/mechanics substrate, and can be used to assist calibration and associative query routing, but it is not yet a finished embodiment oracle.

## 4. Associative query flow corroboration

The user’s idea is directionally correct:

- text theater first
- then structured corroboration
- then deeper queries
- Dreamer can help suggest what to inspect next

This already has the beginnings of support in source:

- text-theater-first gate in `server.py`
- env_help builtin Dreamer topics
- env_report as scoped reasoning layer
- blackboard contract as collation layer

Recommended next clarification for Opus:

- formalize Dreamer as a post-text-theater query assistant
- not a bypass around the gate
- not a replacement for blackboard

## 5. What needs to happen next

### 5.1 Immediate technical next step

Build a calibration/relay pass, not more blind correction guessing.

Priority:

1. exact transform relay for targeted bones/chains
2. bounded joint/chain sweep diagnostics
3. calibration report/playbook surfaces through env_help / env_report / Dreamer tab
4. ranker retune based on empirical sweep results, not only heuristic theory

### 5.2 Immediate product/doctrine next step

Update the active trajectory so it says:

- Dreamer participates in calibration as a scorer/comparer/query suggester
- text-theater-first gate remains correct
- blackboard remains the intended structured bridge
- calibration playbooks need to be added to env_help
- later text-theater robustness work should be marked, but not speculated past the existing research docs

## 6. Suggested ask for Opus

Opus should now produce the next trajectory around:

1. calibration / positional relay program
2. exact role of Dreamer in calibration and associative query suggestion
3. env_help / env_report / blackboard updates needed to support that flow
4. ranker consequences of the new restored kneel baseline

Specifically, Opus should not treat the active problem as the old "open knee gap" state anymore. The trajectory should be grounded on the new live brace state described above.
