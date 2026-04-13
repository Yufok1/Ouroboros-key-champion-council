# Dreamer Correction Table Tuning Advisory 2026-04-12

Repo: `F:\End-Game\champion_councl` branch `main`
Baseline: `3636db1`
Prepared by: Opus (read-only advisory)
Requested by: Codex, after first live episode step returned negative reward on `drop_hips`

Constraints honored: no capsule discussion, no HD speculation, no Pan speculation, no web search.

Related:
- [DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md](DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md)
- [CODEX_TRAJECTORY_REPORT_2026-04-12.md](CODEX_TRAJECTORY_REPORT_2026-04-12.md)

## Live Evidence (first episode step, drop_hips)

| Field | Before | After | Δ |
|---|---|---|---|
| `lower_leg_l.gap` | 0.4998 | 0.7302 | **+0.2304** (worse) |
| `pose.hips_world_y` | 5.668 | 5.898 | **+0.230** (hips rose) |
| `balance.stability_margin` | −1.9595 | −2.1908 | −0.2313 (worse) |
| `total_reward` | — | — | **−1.0951** |

Hips rose by +0.230 and the knee gap widened by **the same +0.230**. That 1:1 correlation is geometrically clean — the knee didn't move, the hips moved up, and the gap is now larger by exactly the amount the hips rose. The scorer correctly flagged it as worse on gap, stability, and margin.

## Root Cause — NOT sign error. Template semantics mismatch.

Every entry in `_DREAMER_KNEEL_CORRECTIONS` (server.py:10404–10517) carries **two** pose shapes:

```
"pose_delta": {"offset": {"hips": {"y": -0.03}}}          # documentation, not dispatched
"workbench_set_pose_batch_template": {
    "poses": [{"bone": "hips", "offset": {"x": 0.0, "y": -0.15, "z": 0.05}}]
}                                                          # dispatched as absolute
```

The episode step handler at server.py:11365–11386 reads `workbench_set_pose_batch_template` and dispatches it directly through `_dreamer_dispatch_env_control`. It is treated as an **absolute pose override**, not a delta. So `drop_hips` does not "drop hips by some amount"; it **overwrites** hips offset to `(0, -0.15, 0.05)` regardless of current state.

### Why that makes drop_hips raise the hips

The live 9-bone half_kneel_l seed (`static/main.js:5312–5331`, per v1 plan) sets hips at an offset y that is **more negative than −0.15** (the seed is a deeper kneel drop than the correction template). So when `drop_hips` fires from the seed state, the effect is:

```
seed offset_y   ≈  −0.25 (or deeper)
drop_hips sets  =  −0.15
net motion      =  +0.10 local  →  +0.23 world (hips rise)
```

The action name describes what the template WOULD do from a neutral rest pose. From the current failing kneel seed, it effectively does the **opposite of its name**. This is true of all the hip-related absolute templates:

| Action | Template offset.y | Template offset.z |
|---|---|---|
| drop_hips | −0.15 | +0.05 |
| raise_hips | −0.10 | +0.05 |
| shift_hips_fore | −0.12 | +0.07 |
| shift_hips_aft | −0.12 | +0.03 |

All four hip templates collapse toward a "medium-shallow kneel" y. None of them produce a meaningful downward nudge from a seed that is already deeper than all four templates.

Same architectural issue applies to rotation templates:
- `tuck_lead_knee` absolute = `lower_leg_l rotation_deg [125, 0, 0]` — overrides to 125° pitch regardless of current flex
- `widen_anchor_foot` absolute = `foot_r rotation_deg [-25, 9, 0]` — **also changes pitch to −25°** on top of the +9° yaw, which is an unintended off-axis side effect (see sign-mistakes section)
- `counter_rotate_spine` absolute = `spine rotation_deg [-9, 0, 0]`
- `counter_rotate_chest` absolute = `chest rotation_deg [-11, 0, 0]`

## Recommended Fix — Option A (convert to true delta dispatch)

The `pose_delta` field already exists in every entry and documents the intended perturbation. Make it the source of truth.

### Where to fix

In `dreamer_episode_step` at server.py:11365 (just before `workbench_set_pose_batch` dispatch), or in a new helper `_dreamer_build_delta_dispatch(before_payload, selected_action)`:

1. Read the current pose for the targeted bone(s) from `before_payload.features.pose` (or a richer pose read if needed — `hips_world_y`, `hips_world_z`, `lower_leg_l_pitch_deg`, `foot_r_yaw_deg` are already in the compact observation at 10986–11031; if local offset/rotation are needed, extend the packer at `_dreamer_mechanics_observation_payload`).
2. Add `pose_delta` values to current pose values per bone/axis.
3. Emit a new `workbench_set_pose_batch` payload with the computed absolute.

Scope estimate: ~40–60 lines in server.py. Zero capsule touch. Zero frontend touch. Zero schema change — `pose_delta` is already on every entry and the compact observation already exposes current pose for the bones that matter.

### Why this is the right call over Option B (rebuild absolute templates)

- Option B bakes the current seed baseline into templates, which breaks every time the seed changes
- Option A makes each action a true perturbation from whatever state the body is currently in, which is what the action names already imply
- Option A also makes multi-step episodes work correctly (each step is relative to the previous, not a repeated reset)
- Option A makes documentation and runtime agree

## Ranked Retune Recommendations (after Option A lands)

The `pose_delta` values as currently written are **too small for a single-step smoke test to register a visibly positive reward**. The current gap is 0.50; a 0.03 hips drop moves things about 6% of the gap. Reward scorer noise floors may eat that.

### Recommended starter deltas (larger than documented, for first-pass convergence proof)

| Action | Current `pose_delta` | Suggested starter delta | Rationale |
|---|---|---|---|
| drop_hips | offset y: −0.03 | **offset y: −0.12** | Gap is 0.50, world-space nudges under 0.05 won't move reward out of noise |
| tuck_lead_knee | rot y: +5° | **rot y: +20°** | 5° flex on a 0.50 gap is ~3% closure; 20° gives a visible register |
| widen_anchor_foot | rot y: +3° | **rot y: +8°** | Minimum motion that clearly widens polygon without flipping foot plant |
| counter_rotate_spine | rot x: −3° | **rot x: −6°** | Keep small; spine is compensating, not primary |
| counter_rotate_chest | rot x: −3° | **rot x: −6°** | Same |
| raise_hips | offset y: +0.02 | offset y: +0.04 | Low priority — this is a recovery action, not a convergence action |
| shift_hips_fore | offset z: +0.02 | **offset z: +0.05** | Worth testing after knee/foot corrections stabilize |
| shift_hips_aft | offset z: −0.02 | offset z: −0.04 | Recovery action — keep small |

These are tuning starters, not final values. Once one positive step lands, back off to values ~half the starter to match the documented intent, and let the episode loop iterate.

### Test order (the part Codex asked for)

**1. tuck_lead_knee first.** Reasons:
- Directly targets the dominant defect (`lower_leg_l.gap = 0.50`)
- Leaf bone — no cascade through carrier chain
- Doesn't move CoM, so stability can't get worse as a side effect
- Reward scorer's most trustworthy signal (`gap_delta`) is the one this action moves

**2. widen_anchor_foot second.** Reasons:
- Second-most-negative signal is `stability_margin = −1.96`, which is the CoM-to-support-polygon edge distance
- `foot_r` is supporting with high load share, so widening its yaw grows the polygon directly
- Also a leaf bone — no cascade
- Should produce a positive `margin_gain` contribution without disturbing the knee

**3. drop_hips (real delta version) third.** Reasons:
- Higher blast radius — moving hips cascades through spine/chest via the bone hierarchy
- Only worth firing after the leaf corrections have established a positive reward baseline
- When it fires, it should actually drop hips (under delta dispatch) and close the gap the way the name says

**4+. Defer counter_rotate_spine, counter_rotate_chest, shift_hips_*, raise_hips** until one of the first three produces a positive reward. They are secondary/compensation actions, not primary convergence drivers.

## Reward Term Trustworthiness (for current kneel convergence)

Ranked from most to least trustworthy:

| # | Contribution | Trust | Why |
|---|---|---|---|
| 1 | `gap_delta` | **HIGH** | Directly observed, scaled 4× with ±2.0 clamp, matches named success criterion, responds to all three primary action targets |
| 2 | `stability_gain` | **HIGH** | Continuous from `stability_risk` which is primary brace-collapse signal, scaled 2× with ±2.0 clamp |
| 3 | `margin_gain` | MEDIUM-HIGH | Continuous from `stability_margin`, smooth under small CoM moves, but scaled only 0.75× so contributes less than gap/risk |
| 4 | `support_realized` / `support_lost` | MEDIUM | High-value when it fires (+1.5 per joint) but binary — won't fire on most sub-step nudges until the knee actually closes contact |
| 5 | `manifold_gain` | LOW | Scale of 0.2× is too small to register; often zero on small nudges |
| 6 | `phase_advance` / `phase_regression` | LOW | Phase transitions are chunky (6-phase sequence); won't fire on single-step perturbations until later convergence |

Terminal penalties (`support_penetration = −3.0`, `stage_blocked = −1.5`, `falling = −4.0`) are all correctly signed and well-calibrated for their purpose but are edge conditions, not primary guidance.

### Focus for single-step tuning

Watch `contributions` for `gap_delta`, `stability_gain`, `margin_gain`. If those three agree on sign, the step is meaningful. If they disagree, something cascaded — investigate which bone moved unexpectedly.

## Obvious Sign / Axis / Template-Direction Mistakes

The ranker and reward scorer are sound. The bugs are all in `_DREAMER_KNEEL_CORRECTIONS` template values.

### Confirmed issues

1. **Template absoluteness (ROOT CAUSE)** — covered above. All templates act as pose overrides, not deltas. drop_hips from the deep kneel seed raises the hips by ~0.23 world units because the template's −0.15 offset is shallower than the seed's offset.

2. **widen_anchor_foot has an off-axis side effect.** Documented `pose_delta` is `{"rotation_deg": {"foot_r": [0, 3, 0]}}` — yaw only. The absolute template is `[−25, 9, 0]` — which sets **pitch to −25°** as well as yaw to 9°. On Option A conversion to delta dispatch, the pitch component disappears (good). But if Option A is delayed, the current absolute template is simultaneously tilting the foot forward/backward, which can break the foot plant entirely. Fix the template pitch component to match current foot_r pitch state if Option A doesn't land first.

3. **raise_hips vs drop_hips are effectively the same action.** Absolute templates differ only by Δy = 0.05 (drop: −0.15, raise: −0.10), same z. Both raise the hips from the current kneel seed. There is no scenario from the current failing state where these produce meaningfully different outcomes under the current dispatch path. Option A fixes this trivially by making them true opposite deltas.

4. **shift_hips_fore and shift_hips_aft also collapse the y-offset** to −0.12, causing every hip-category action to reset the kneel depth to approximately the same value before modifying z. Option A fix is free.

5. **Documented `pose_delta` magnitudes are too small** for single-step visibility on the current failing state. The gap is 0.50 but drop_hips delta is 0.03 and tuck_lead_knee delta is 5°. Not a correctness bug, but a calibration bug. Use the starter deltas from the retune table above.

### Not a bug

- Reward scorer sign polarities are all correct (gap_delta = prev − curr for decreasing = good; risk_delta = prev − curr for decreasing = good; margin_delta = curr − prev for increasing = good).
- Ranker heuristic picked `drop_hips` correctly per its own logic (gap > 0.2 branch + hips_world_y > 5.5 bonus). The heuristic is not the bug — the template it dispatched was.
- `proposal_source = "outer_control_plane_heuristic_v1"` is honestly labeled — it's the server-side ranker, not capsule `imagine()`. Don't rename until Addition 3 from the trajectory report lands.

## Minimum Codex Sequence To Get One Positive Step

1. Implement Option A: delta-mode dispatch from `pose_delta` computed against live pose state
2. Update `tuck_lead_knee.pose_delta.rotation_deg.lower_leg_l` to `[20, 0, 0]` as a tuning starter
3. `POST /api/dreamer/episode_reset` then `POST /api/dreamer/episode_step` with `{"action_key": "tuck_lead_knee"}`
4. Verify `reward_breakdown.contributions.gap_delta > 0` and `lower_leg_l.gap` decreased
5. If yes, Dreamer v1 has its first positive evidence and convergence testing begins
6. If no, read the text theater to see which bone actually moved, and which axis

Everything else from the trajectory report (Additions 1+2 `observe()` wiring) is still needed for capsule buffer flow but is orthogonal to the tuning problem. The positive-reward proof can happen before or after those additions — recommend after tuning works, to avoid confounding which change fixed what.
