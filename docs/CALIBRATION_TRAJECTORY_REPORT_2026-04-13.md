# Calibration Trajectory Report 2026-04-13

Repo: `F:\End-Game\champion_councl` branch `main`
Baseline: `3636db1` plus any uncommitted Codex calibration work
Prepared by: Opus (read-only advisory)
Grounded on: [CODEX_SITREP_2026-04-13_DREAMER_TEXT_THEATER_CALIBRATION.md](CODEX_SITREP_2026-04-13_DREAMER_TEXT_THEATER_CALIBRATION.md)

Constraints honored: no capsule edits, no HD speculation past existing research docs, theater-first gate treated as correct and active, blackboard treated as intended bridge not replacement, Dreamer treated as outer evaluator/proposer not finished oracle.

## Scope of This Report

This trajectory report replaces the earlier tuning-advisory framing. The tuning advisory at [DREAMER_CORRECTION_TABLE_TUNING_ADVISORY_2026-04-12.md](DREAMER_CORRECTION_TABLE_TUNING_ADVISORY_2026-04-12.md) was grounded on an **old failing state** (knee lifting, gap ≈ 0.50). That state no longer exists. The current restored `half_kneel_l` baseline is a two-contact brace with:

- `lower_leg_l.gap = 0.0` (grounded)
- both `lower_leg_l` and `foot_r` supporting
- `stability_margin = −0.6129` (CoM outside polygon)
- `stability_risk = 1.00`
- `route.active_phase_id = unload`, `phase_gate: risk 1.00 > 0.96`
- torso: `hips_pitch 8°, spine_pitch −6°, chest_pitch −8°`
- leaf: `lower_leg_l_pitch 120°, foot_r_yaw 6°`

The active problem is no longer **missing contact**. It is **the CoM projection sits outside the two-foot-plus-knee support polygon, and no single leaf correction walks it back inside**. That reframing changes what Dreamer should be doing, what the ranker should prefer, and what calibration infrastructure needs to exist.

## 1. Ranker Consequences of the New Baseline

The ranker at `server.py:10902–10983` was written against the old open-gap state. Under the current brace state it is **actively misranking**.

### 1.1 Gate-by-gate read under the new state

| Ranker clause | Value now | Firing? | Consequence |
|---|---|---|---|
| `gap > 0.2` | gap=0 | **NO** | drop_hips, tuck_lead_knee, shift_hips_fore, raise_hips all lose their primary score branch |
| `risk >= 0.84 or margin < 0` | risk=1.0, margin=−0.61 | YES | widen_anchor_foot (+2.0), shift_hips_aft (+1.6), counter_rotate_spine (+1.4), counter_rotate_chest (+1.2) still fire |
| `hips_world_y > 5.5 and drop_hips` | unknown; check live | possibly YES | +0.8 bonus to drop_hips even though gap branch is dead |
| `supporting and load_share >= 0.85 and widen_anchor_foot` | depends on foot_r load_share | likely YES | extra +0.8 to widen_anchor_foot |
| `raise_hips and risk < 0.25 and gap < 0.08` | risk=1.0 | NO | dead |

### 1.2 The pathological inversion

Under the new baseline the ranker's default top picks become the **margin-negative set**:

1. widen_anchor_foot — empirically net-negative (lost manifold)
2. shift_hips_aft — currently a dispatching no-op in observed mechanics
3. counter_rotate_spine — empirically net-negative on margin
4. counter_rotate_chest — empirically net-negative on margin

Meanwhile the **only action with a proven positive step** (`tuck_lead_knee`, driven by `margin_gain`) gets **zero score** under the new state because its only trigger is the dead `gap > 0.2` branch. By default, the ranker would never pick the one action that works.

### 1.3 Minimum ranker retune (before empirical sweep drives this)

Two changes scoped to `_dreamer_rank_proposals`:

**Change A — re-gate tuck_lead_knee on margin, not gap:**
```
if margin < -0.4 or risk >= 0.9:
    if action_key == "tuck_lead_knee":
        score += 1.8  # empirical: only proven positive under current state
        reasons.append("knee tuck has shown margin_gain under poor-margin brace states")
```

**Change B — demote the margin-negative set:**
```
# widen_anchor_foot at score +2.0 under margin<0 is pre-empirical.
# Reduce or remove until sweep evidence justifies it for this baseline.
```
Either drop widen_anchor_foot's `margin < 0` branch from +2.0 to +0.4, or gate it behind an additional `foot_r manifold_points >= N` check so it doesn't fire when widening would lose manifold.

Same for counter_rotate_spine and counter_rotate_chest — they should not get positive score under poor margin until sweep evidence says so for this specific carrier-chain alignment.

### 1.4 Longer-term ranker correction (post-sweep)

Once the calibration sweep (§2) lands, the ranker should **read recent empirical results** from a new blackboard family (`calibration` or `sweep_result`) and score each action by its observed reward history at similar states, not by fixed heuristic priors. That turns `_dreamer_rank_proposals` into a hybrid: heuristic priors when no sweep data exists, empirical scoring when it does.

**This is not an ML move.** It is a server-side lookup against a recent-history store. Zero capsule touch. ~40 lines in the ranker.

## 2. Calibration / Positional Relay Program

The calibration program is the **next concrete engineering move**, replacing blind correction tuning. Three layers, stackable, each independently useful.

### 2.1 Layer 1 — Transform relay (primitive)

**What:** A read-only server-side tool that returns the current world and local transforms for a named bone or bone chain, cropped to the bones relevant to the active controller.

**Why:** The compact observation at `_dreamer_compact_observation` (server.py:10986–11031) exposes `hips_world_y`, `hips_world_z`, `lower_leg_l_pitch_deg`, `foot_r_yaw_deg`. That is enough for reward scoring but **not enough for calibration reasoning**. Calibration needs: full local offset + rotation for each bone in the carrier chain, plus derived quantities (CoM world xyz, support polygon vertices, support polygon center, CoM-to-support-center vector).

**Shape suggestion:**

```
GET /api/dreamer/transform_relay?bones=hips,spine,chest,lower_leg_l,foot_r
→ {
    "status": "ok",
    "updated_ms": int,
    "bones": {
        "hips": {
            "local_offset": {"x": ..., "y": ..., "z": ...},
            "local_rotation_deg": {"pitch": ..., "yaw": ..., "roll": ...},
            "world_position": {"x": ..., "y": ..., "z": ...},
            "world_rotation_deg": {"pitch": ..., "yaw": ..., "roll": ...}
        },
        ...
    },
    "derived": {
        "center_of_mass_world": {"x": ..., "y": ..., "z": ...},
        "support_polygon_vertices": [...],
        "support_polygon_center": {...},
        "com_to_support_center_vector": {"x": ..., "y": ..., "z": ...}
    }
}
```

**Integration with the theater-first gate:** the transform relay should be **gated behind the same sequence** as shared_state. Theater first, then transform relay, then sweeps. This keeps doctrine intact.

**Scope:** ~80 lines server.py + a matching `env_help` topic. No frontend. No capsule.

### 2.2 Layer 2 — Bounded single-axis sweep diagnostic

**What:** An endpoint that takes a bone + axis + range + step and returns a ranked list of reward_breakdown results, one per variant, against the current baseline.

**Shape suggestion:**

```
POST /api/dreamer/bounded_sweep
body = {
    "bone": "hips",
    "axis": "offset.z",
    "from": -0.10,
    "to":   +0.10,
    "steps": 5,
    "restore_after": true
}
→ {
    "status": "ok",
    "baseline": <compact observation>,
    "variants": [
        {"value": -0.10, "reward_breakdown": {...}, "after_compact": {...}},
        {"value": -0.05, "reward_breakdown": {...}, "after_compact": {...}},
        {"value":  0.00, "reward_breakdown": {...}, "after_compact": {...}},
        {"value": +0.05, "reward_breakdown": {...}, "after_compact": {...}},
        {"value": +0.10, "reward_breakdown": {...}, "after_compact": {...}}
    ],
    "best": {...},
    "gradient_direction": "negative" | "positive" | "flat"
}
```

**Key requirements:**
- Each variant restores to the original baseline between steps, so variants are independent (not sequential)
- The existing `dreamer_episode_reset` already restores; reuse that primitive
- `restore_after: true` restores at the end so the sweep is side-effect-free from the operator's point of view
- Results are written to the new `calibration` blackboard family so the ranker and env_report can read them later

**Scope:** ~120 lines server.py, composed from existing primitives (episode_step, episode_reset, reward_breakdown, env_control dispatch). No capsule. No frontend yet.

**First sweep to run (under current brace state):** `hips offset.z` from −0.08 to +0.08 step 0.04. This directly tests the user's carrier-chain-behind-torso hypothesis. If margin improves on a positive z (forward) variant, the carrier alignment theory is confirmed empirically in under 30 seconds.

**Second sweep:** `spine pitch` from −12° to +4° step 4°. Tests whether upper-body tilt is the carrier offset compensator.

**Third sweep:** `foot_r offset.z` (fore/aft foot placement) from −0.06 to +0.06 step 0.03. Tests whether the support polygon can be slid under the CoM instead of moving the CoM over the polygon.

These three sweeps are the minimum calibration pass. Run them in sequence, store results, and the ranker has its first empirical priors.

### 2.3 Layer 3 — Calibration report recipe

**What:** A new `env_report` recipe, `calibration_diagnosis`, that fuses transform relay output with recent sweep results and produces a readable digest matching the existing `route_stability_diagnosis` style.

**Fields to surface:**
- severity / designation (as with existing env_report recipes)
- `current_transforms` — short per-bone table from transform relay
- `com_vs_support` — single line: "CoM is 0.61 behind support center along z" or similar
- `recent_sweeps` — last 3 sweep results per bone/axis with best variant
- `suggested_next_inspection` — which bone/axis has the steepest gradient toward margin improvement
- `recommended_next_read` — pointer to the specific transform_relay query operators should run next

**This is the heart of associative query suggestion.** The report doesn't tell the operator what to do; it tells them **what to look at next**. Dreamer's job is producing the suggested_next_inspection value, which it already does through its ranker and reward history.

**Scope:** ~100 lines in server.py in the env_report pipeline. No capsule. No frontend.

## 3. Dreamer's Role in Calibration and Associative Query Suggestion

The sitrep's framing is correct: Dreamer is a **bounded outer-loop evaluator/proposer**, not a finished oracle. The calibration program refines that role without expanding it.

### 3.1 What Dreamer DOES in calibration (active capacities)

1. **Sweep executor.** When a bounded sweep is requested, Dreamer's existing episode-step + reward-scoring + restore primitives run each variant and score it. Dreamer is the machinery that turns "try this" into "here's the reward breakdown for each variant."

2. **Comparator.** Given N sweep results, Dreamer's reward scoring provides a **continuous comparator** across variants. The scorer already ranks gap_delta, stability_gain, margin_gain, etc. consistently. That consistency is the calibration backbone.

3. **Query suggester.** After a sweep lands, Dreamer's ranker can identify which bone/axis had the steepest gradient and suggest that as the next inspection target. This is **associative query suggestion** — not the query itself, just pointing at where to look.

4. **Scorer for operator-initiated corrections.** When an operator manually sets a pose via `workbench_set_pose_batch`, Dreamer can score the before/after via the existing reward_breakdown path. Calibration is bidirectional: operator proposes, Dreamer scores; or Dreamer proposes, operator approves.

### 3.2 What Dreamer DOES NOT do in calibration (hard limits)

1. **Not the transform authority.** The mechanics runtime in `static/main.js` is the only source of transform truth. Dreamer reads from transform relay; it does not invent or cache transforms.

2. **Not a bypass around the theater-first gate.** Dreamer's calibration queries go through the same sequence: theater read first, then transform relay, then sweep, then result. The theater-first gate stays active and applies to calibration endpoints just as it applies to `shared_state`.

3. **Not a blackboard replacement.** Sweep results land in a new blackboard row family (`calibration` or `sweep_result`); they do not live in a Dreamer-private store. The blackboard remains the intended bridge.

4. **Not an automatic repositioning oracle.** Dreamer can suggest "hips forward by 0.04 produced +0.15 margin_gain." It does NOT automatically apply that. The operator (or, later, Pan) decides whether to commit. This stays in advisory mode.

5. **Not a query author.** Dreamer suggests **what to inspect**, not what to ask. The operator composes the actual env_read / env_report / transform_relay query. Dreamer provides the "look at hips offset.z next" hint; the operator runs the query.

### 3.3 The post-theater query flow

```
theater_first_gate
    ↓
env_read(text_theater_embodiment)          ← operator reads the visible narrative
    ↓
env_read(text_theater_snapshot)            ← operator reads structured scene summary
    ↓
env_report(route_stability_diagnosis)      ← operator gets fused diagnostic
    ↓
[NEW] transform_relay(bones=carrier_chain) ← operator gets exact transforms
    ↓
[NEW] env_report(calibration_diagnosis)    ← operator gets suggested_next_inspection
    ↓
[NEW] bounded_sweep(bone, axis, range)     ← operator confirms gradient empirically
    ↓
workbench_set_pose_batch(best variant)     ← operator commits the winning pose
    ↓
env_read(text_theater_embodiment) again   ← verify
```

Dreamer participates at steps 6, 7, and indirectly at step 8 (scoring the commit). It does not participate at steps 1, 2, or 3 — those stay in operator hands.

## 4. env_help / env_report / Blackboard Updates Needed

### 4.1 env_help

Four new topics, all in the environment-specific registry at `static/data/help/environment_command_registry.json` and matching builtin help in `server.py`:

1. **`transform_relay`** — teaches the new tool, its gate behavior, field shapes, and example queries
2. **`bounded_sweep`** — teaches sweep semantics, restore behavior, step count limits, and how to read variants
3. **`calibration_diagnosis`** — teaches the new env_report recipe and its `suggested_next_inspection` output
4. **`calibration_playbook`** — narrative walk-through of the post-theater query flow in §3.3, pinning the sequence as doctrine

Existing `env_help` topics to edit:
- `env_report` topic should add a forward-pointer to `calibration_diagnosis`
- `dreamer_control_plane` topic should add calibration role text from §3
- `environment` top-level topic should add "calibration" as a named phase alongside "observation" and "correction"

### 4.2 env_report

Two recipe additions:

1. **`calibration_diagnosis`** — the new recipe described in §2.3
2. **`route_stability_diagnosis`** (existing) — add a `calibration_hint` row that points at the most recent sweep result if any, and at `transform_relay(bones=carrier_chain)` if none

### 4.3 Blackboard

One new row family: **`calibration`**. Rows:

- `calibration.transform.<bone>` — latest transform snapshot per tracked bone (hips, spine, chest, lower_leg_l, foot_r); source = transform_relay; sticky for ~5s; tolerance based on drift from last snapshot
- `calibration.sweep.<bone>.<axis>` — latest sweep result per bone/axis; source = bounded_sweep; sticky for ~60s; label = "best variant + reward delta"
- `calibration.suggestion` — single row holding the current `suggested_next_inspection` target; source = calibration_diagnosis; priority high when stability_risk ≥ 0.9
- `calibration.gradient` — per-bone gradient hint from most recent sweep; used by the ranker to read empirical priors

Working_set additions:
- `calibration_targets` — list of bones with unexplored axes
- `calibration_confirmed` — list of bones with confirmed gradient direction

These additions go in `_envBuildBlackboardState` in `static/main.js` (the builder at ~30720 per the 04-11 memory). No changes to the contract shape — just new family admission.

## 5. Carrier-Chain Hypothesis — How Calibration Validates It

The user's hypothesis is: *the CoM sits behind the support polygon because the torso is pitched forward while the carrier (hips) has not projected forward over the feet*. The live data is consistent with this:

- knee grounded, gap = 0 → leaf contact is correct
- margin = −0.61 → CoM is significantly outside polygon
- spine pitched −6°, chest pitched −8° → upper body is already leaned back to compensate, which is **why counter_rotate_spine and counter_rotate_chest hurt margin**: they're un-leaning the compensation and tipping the torso mass further out
- widening the foot doesn't help because the polygon is sliding away from the CoM, not the other way around
- knee tuck helps once because it pitches the carrier chain slightly forward via the kinematic coupling, but repeating it over-flexes

**Calibration test:** sweep `hips offset.z` forward. If `stability_margin` improves monotonically with positive z up to some peak, the hypothesis is confirmed and the real fix is `shift_hips_fore` with the correct delta, not a leaf correction.

**Secondary test:** sweep `hips pitch` forward (positive rotation). If margin improves with less hip pitch, the carrier rotation is as much of the problem as the translation.

These two sweeps — 12 episode variants total, under 30 seconds of runtime — are the empirical discriminator. No more guessing. No more heuristic priors.

## 6. Suggested Codex Implementation Sequence

This replaces the earlier advisory's "fix drop_hips and try tuck_lead_knee" sequence.

1. **Transform relay endpoint** (Layer 1, §2.1). ~80 lines server.py. Read-only. Gated behind theater-first.
2. **Bounded sweep endpoint** (Layer 2, §2.2). ~120 lines server.py, composed from existing episode primitives.
3. **First sweep: `hips offset.z` from −0.08 to +0.08 step 0.04** — validates or refutes the carrier-chain hypothesis empirically
4. **Second sweep: `hips pitch` from −4° to +8° step 4°** — validates or refutes the carrier-rotation component
5. **Third sweep: `spine pitch` from −12° to +4° step 4°** — quantifies upper-body compensation
6. **Calibration report recipe** (Layer 3, §2.3). Consumes sweep results from blackboard.
7. **Ranker retune** — Changes A and B from §1.3. Short-term fix until empirical priors from sweep results replace heuristics.
8. **Blackboard `calibration` family** (§4.3) in `_envBuildBlackboardState`.
9. **env_help topics + env_report calibration_hint** (§4.1, §4.2).
10. **Trajectory report Additions 1+2** (the `observe(signal_type='mechanics_v1')` and `observe(signal_type='mechanics_reward')` wiring from `CODEX_TRAJECTORY_REPORT_2026-04-12.md`) can be deferred until after calibration is proven. They are still needed for capsule buffer flow but orthogonal to the calibration program, and keeping them separate avoids confounding which change produced which improvement.

Steps 1–5 are the arterial flow for this pass. Steps 6–9 are the product/doctrine wrap. Step 10 stays deferred.

## 7. What This Report Explicitly Does NOT Cover

- **Capsule edits.** Out of scope per the active execution rule. The observation/reward buffer questions stay archived.
- **Text theater HD direction.** The user has separate research. This report does not speculate on rendering changes.
- **Pan implementation.** Pan remains a future router; calibration prepares for Pan but does not require it.
- **Tinkerbell, Coquina, multi-topology generalization.** All deferred.
- **New reward functions.** The existing `_dreamer_reward_breakdown` is sound. Calibration reuses it as-is.
- **Automatic repositioning.** Dreamer stays advisory. The operator commits the winning pose.

## 8. Finish Line For The Calibration Pass

Five items, all verifiable via existing MCP probes or new endpoints:

1. `transform_relay` returns well-formed per-bone transforms for the carrier chain, gated behind theater-first
2. `bounded_sweep` runs N variants, restores baseline, returns reward breakdowns per variant
3. First carrier-chain sweep produces an empirical gradient direction (positive, negative, or flat) on `hips offset.z`
4. `calibration_diagnosis` env_report recipe produces a `suggested_next_inspection` field populated from sweep history
5. Ranker retune lands and `tuck_lead_knee` is no longer scored zero under the current brace state

When these five land, calibration moves from "blind action tuning" to "empirical carrier-chain diagnosis" and the kneel convergence problem either resolves (if the carrier hypothesis is correct) or the evidence forces a new hypothesis grounded in actual sweep data.
