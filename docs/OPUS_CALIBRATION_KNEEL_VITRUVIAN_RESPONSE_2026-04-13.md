# Opus Calibration / Kneel / Vitruvian Response 2026-04-13

Repo: `F:\End-Game\champion_councl` branch `main`
Baseline: `3636db1` plus uncommitted Codex calibration work
Prepared by: Opus (read-only advisory)
Responds to: [OPUS_CORRECTED_TRAJECTORY_REPORT_2026-04-13.md](OPUS_CORRECTED_TRAJECTORY_REPORT_2026-04-13.md)

Constraints honored:
- no capsule edits
- no duplicate/parallel authority systems
- blackboard stays text-theater-only
- web-theater text stays selective special-purpose
- repair existing systems before new surfaces

All source references verified by direct read.

## Q1 — Smallest truthful repair to the neutral-anchor calibration path

### The corrected layer split (verified)

Two different reset tools exist in `static/main.js`, on two different layers, behind two different mode gates:

| Tool | File:line | Mode gate | What it resets | Layer |
|---|---|---|---|---|
| `_envWorkbenchResetAngles` | main.js:20363 | **`editing_mode === 'structure'`** (20373) | `_envBuilderSubject.bones[].orientation` + `.roll` via `_envBuilderDefaultAnglePresetForBone` | **structure-mode builder bone defaults** (scaffold) |
| `_envWorkbenchClearPose` | main.js:19699 | **`editing_mode === 'pose'`** (19709) | `_envBuilderSubject.pose.transforms` (all or one bone) via `_envNormalizeBuilderPoseState` | **embodied pose layer** |

If the sweep baseline reset was calling `workbench_reset_angles` while the workbench was in **pose mode**, it was rejected at the mode gate (20373–20380), logged as `MODE MISMATCH`, and returned `false`. A rejected call does no mutation and emits no fresh frame — **which is exactly the signature of "all variants stale, cache_advanced_after_command=false, matched_command_sync=false"** from Codex's sweep debug. This is the single most probable root cause of the observability gap he flagged before the framing correction.

### The minimum repair

One commit-sized change in `_dreamer_dispatch_env_control` (or whatever helper the bounded_sweep endpoint uses to build its baseline-restore payload):

1. **Baseline restore path must use `workbench_clear_pose { "all": true }` (pose-mode, line 19709–19763)**, not `workbench_reset_angles`. Confirmed: `spec.clear_all = true` empties `poseState.transforms` (19749), calls `_env3DApplyBuilderPoseState(mesh)` (19755), increments scene.dirty, schedules live sync, and saves theater session. That is the real embodied neutral reset.

2. **Ensure editing_mode is `pose` before the call.** If the sweep harness does not already switch modes, the very first call will be rejected at the gate. A single mode-set call at sweep entry is enough; sweep steps inherit the mode.

3. **If a canonical neutral-rest macro exists**, apply it via `workbench_apply_pose_macro` (main.js:20183) *after* the clear. Clear sets zero-transform neutral; the macro (if it exists for the active family) lands a stable declared rest state. Otherwise skip.

### What this does NOT repair on its own

- It does not verify that downstream pose-state mirrors (`pose_transform_count`, `current_pose_transform_present`, `macro_pose_entry_present`) actually propagate into the text-theater / live-cache snapshot. If the mode-gate was the only blocker, `workbench_clear_pose` → live sync → snapshot will now register. If there is a **second** mirror-propagation gap, the clear will succeed but the sweep diagnostic fields will still be empty. Codex's next diagnostic after implementing this should compare `cache_advanced_after_command` against the action type: if pose-mode calls now advance the cache but structure-mode calls do not, the mode-gate was the only gap.

### Smallest verification probe after the repair

Run a single sweep variant with:
- baseline: `workbench_clear_pose {all: true}` in pose mode
- variant: `workbench_set_pose_batch` with one bone offset change
- observe: `cache_advanced_after_command`, `matched_command_sync`, `pose_transform_count`

If `pose_transform_count` goes from 0 to 1 and `cache_advanced_after_command = true`, the calibration seam is honest. If not, the gap is downstream of the pose layer and needs a mirror-trace pass.

## Q2 — Smallest kneel-route repairs to break the shortest-path brace bias

Four source-verified bias sources, ranked by blast radius. Codex should take them in order.

### Bias A (smallest blast radius) — knee support role is hardcoded to `brace`

**Source:** `static/main.js:4458–4472`

```js
if (grounded && (row.group === 'foot' || row.group === 'hand' || row.group === 'knee')) {
    if (row.group === 'foot') {
        // plant vs brace decided by contact_mode, planted_alignment, manifold_ratio
        supportRole = braceLike ? 'brace' : 'plant';
    } else {
        supportRole = 'brace';  // ← knee and hand have no plant path
    }
}
```

The knee (and hand) **cannot become `plant`** in current source. Every grounded knee is forced to `brace`, which cascades into `support_phase = 'braced_support'` (4511) and the `knee_brace` alert (4518), which in turn drives the transition-template criteria that demand `support_role: 'brace'` at line 1581, 1601, 1621. The whole kneel template is self-consistent *with the brace-only assumption* and so the system never surfaces any evidence that a deeper-contact kneel is even possible.

**Smallest repair:** duplicate the foot's plant/brace discrimination for the knee group, using the knee patch's own `planted_alignment` and `active_manifold_ratio` (the patch fields already exist from `_envBuilderKneeContactPatch` at 2716). ~8 lines inside the existing `if (grounded && …)` block. No new fields, no new concepts — just stop force-branding grounded knees as brace-only.

This change alone will not make the brace-or-plant distinction *correct*, because the knee patch geometry is still the small front-of-shin patch (Bias D below). But it unblocks the evidence path: once plant-vs-brace is decidable for knees, the blackboard and env_report will start showing the discrimination, and the sweep system will start producing reward shape changes that distinguish deep-contact from brace-contact outcomes.

### Bias B (medium blast radius) — `upper_leg_l` is in compensation, not carrier/leader

**Source:** `static/main.js:5262–5275`

```js
{
    controller_id: 'half_kneel_l_topology',
    leader_bone_ids: ['lower_leg_l'],
    anchor_bone_ids: ['foot_r'],
    carrier_bone_ids: ['hips'],
    compensation_bone_ids: ['upper_leg_l', 'upper_leg_r', 'lower_leg_r', 'foot_l'],
}
```

The femur (`upper_leg_l`) is **the bone that actually rotates to lower the body into a kneel**. Its position in `compensation_bone_ids` tells the solver "this is something that passively balances, not something that leads motion." Combined with Bias A (knee forced to brace), the solver's whole model of kneeling is "the shin rotates forward onto its front face while the hips drop a little and the femur passively adjusts" — which is shortest-path brace contact, exactly as the corrected trajectory report describes.

**Smallest repair:** move `upper_leg_l` from `compensation_bone_ids` to a new slot in the topology — either add it to `carrier_bone_ids` (treating it as a carrier segment alongside hips) or introduce a `mover_bone_ids` / `descent_bone_ids` role if the controller contract supports it. Check `_envBuilderControllerRecord` for allowed role fields before adding a new one; if the contract only knows leader/anchor/carrier/compensation, put it in `carrier_bone_ids`.

Blast radius: the controller record is read in several places for pivot-rule and propagation-mode evaluation. Adding `upper_leg_l` to `carrier_bone_ids` is a structural topology change that ripples into gizmo attachment, selection rules, and the ranker's carrier_bone_ids branch. Not a one-line fix; needs a careful grep and visual verification on the workbench.

**Do not do this until Bias A is in place and proven.** Otherwise you compound changes and lose the ability to attribute reward shape changes.

### Bias C (medium blast radius) — `route_targets` only has two entries

**Source:** `static/main.js:1508`

```js
route_targets: [leadKnee, anchorFoot],
```

The route only declares two target bones: the lead knee and the anchor foot. Every phase, every criterion, every evaluator reads from this list. The torso, hips, anchor ankle, swinging foot, and lead hip **are not route targets**, which means the route has no way to express "the lead hip must pass through this corridor" or "the anchor ankle must stay inside this polygon." The shortest-path bias comes from the route having no concept of whole-chain corridors — because the route only knows about two endpoint anchors.

**Smallest repair:** extend `route_targets` to include the carrier bones explicitly, e.g. `[leadKnee, anchorFoot, 'hips', anchorAnkle]` or similar. The transition template criteria at 1520–1628 will need one optional criterion per new target, not a full rewrite — existing criteria only reference `anchorFoot` and `leadKnee`, so new targets can be added as no-op entries first (`{ target_id: 'hips', supporting: false }` as a placeholder) before criteria are actually tightened.

Blast radius: medium. Touches every phase in the template plus whatever code reads `route_targets` for realization tracking. Grep `route_targets` across main.js and server.py before editing.

**Do not do this until Biases A and B are in place and proven.**

### Bias D (large blast radius, defer) — knee contact patch shape

**Source:** `static/main.js:2716` `_envBuilderKneeContactPatch`

The patch is computed with `dims = [0.045, 0.20, 0.034]` then `halfWidth = max(0.012, 0.045*0.42) ≈ 0.019`, `halfDepth = max(0.008, 0.034*0.5) ≈ 0.017`, `halfHeight = max(0.018, min(0.05, 0.20*0.14)) ≈ 0.028`. The patch axis is derived from `alongLeg = (0,-1,0).applyQuaternion(worldQuaternion)` — the local down of the lower leg. This produces a small patch on the front of the lower leg just below the knee joint. Real kneeling contacts the **whole shin from knee to ankle**, not just the front of the shin below the knee. This is shortest-path geometry embedded in the patch itself.

**Smallest-possible repair would be:** parameterize the `halfHeight` multiplier or add a patch-shape variant (shin-length contact vs knee-point contact). But the patch is read by contact realization, stability, load field, and reward scoring. The blast radius touches every system downstream of contact patches.

**Defer.** Bias A + B + C may produce enough evidence to confirm whether the patch shape is actually the critical bias, or whether the bias was always the role/topology cascade above. Only re-open patch geometry if sweep evidence shows the upstream repairs are insufficient.

### Recommended order

1. Bias A (knee plant/brace discrimination) — ~8 lines, zero topology change
2. Verify via sweep: does reward shape change on any grounded-knee variant?
3. Bias B (upper_leg_l → carrier) — topology change, verify via workbench visual
4. Verify via sweep: does the kneel transition start producing whole-chain reorganization?
5. Bias C (route_targets extension) — template change, add placeholder criteria first
6. Verify via sweep: does the carrier-chain sweep from the earlier trajectory now produce a monotonic gradient?
7. Re-evaluate whether Bias D is worth reopening

## Q3 — Smallest text-theater blackboard contract for a first Vitruvian-style range/gate surface

The blackboard already has the contract (from the 04-11 checkpoint memory). No new structure needed — one new family, one new working-set list, one new text_theater render section.

### New family: `range_gate`

Rows, one per (bone, axis) pair the active controller declares relevant:

```
id:              "range_gate.<bone>.<axis>"        e.g. range_gate.lower_leg_l.pitch
family:          "range_gate"
layer:           "articulation"
source:          "joint_limits + pose_transform"
label:           e.g. "L lower-leg pitch"
value:           current angle in degrees
unit:            "deg"
tolerance_state: "ok" | "near_limit" | "at_limit"   (proximity to x_min / x_max from joint_limits manifest)
priority:        derived from controller role (leader > carrier > compensation)
session_weight:  carries over between frames for stickiness
group_key:       e.g. "range_gate.lower_leg_l"     so all axes of one bone group
sticky_ms:       ~1000
anchor:          bone_id
detail:          inline text sparkline / range-bar ASCII (see Q4)
```

### Data source

- Joint limits are already computed by `_envBuilderBodyPlanMechanicsManifest` at `main.js:1644` and read through `_envBuilderPoseMechanicsSpec` at `main.js:1672`. Radians in source; convert to degrees at display time.
- Current pose transforms come from `_envBuilderPoseState()` at `main.js:1726`. For each bone, extract the euler rotation (XYZ order from the spec) and compare component-wise to `x_min/x_max/y_min/y_max/z_min/z_max`.
- `tolerance_state` rule: within 85% of range → `ok`; 85–97% → `near_limit`; ≥ 97% → `at_limit`. Simple, consistent with how existing tolerance_state fields are computed for the balance/contact families.

### Working_set addition

```
range_gate_targets:  list of { bone, axes }
```

Populated from the active controller's leader + carrier + anchor bone ids. Leader and anchor get **all three axes** (pitch, yaw, roll). Carrier gets pitch only unless the controller declares otherwise. Compensation bones are NOT in the working set by default — they would flood the surface. If the operator needs to inspect a compensation bone, they pin it explicitly (which the blackboard contract already supports via `pinned_row_ids`, currently empty).

### Build site

Add a new builder function `_envBuilderRangeGateRows(controllerRecord, poseState, jointManifest)` and call it from `_envBuildBlackboardState` around `main.js:31207` (per the 04-11 memory). It returns the row list; the blackboard builder appends them the same way it appends balance/contact/controller/support rows today.

### Render site

Add a new section `RANGE GATES` in `scripts/text_theater.py` parallel to the existing blackboard / profile sections at ~1021 and ~1043. It iterates `range_gate` rows in priority order, renders `label`, `value`, `tolerance_state` as a color/tag, and `detail` as the range-bar ASCII.

### What this contract does NOT do

- Not a new blackboard. Same blackboard, one new family.
- Not a new renderer. Same `text_theater.py`, one new section.
- Not a web-theater surface. Rendered only in text theater.
- Not a control plane. Read-only observability; no setter, no mutator, no ranker input.
- Not a replacement for the existing blackboard families. Balance, contact, controller, corroboration, load, route, session, support rows all remain.

## Q4 — Glyph orientation / glyph articulation pieces: useful now vs deferred

The relevant docs are:
- `docs/TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md`
- `docs/TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md`

### Useful immediately (consumed by Q3's `range_gate` rendering)

1. **Range-bar primitive** — the low/mid/high indicator glyph sequence (a row of cells with the current position marker inside a min/max sleeve). This is the fundamental unit the `detail` field in the `range_gate` row needs. Any glyph-orientation primitive that renders "value X in range [min, max]" as an inline monospace cell sequence is immediately useful.

2. **Per-axis orientation glyph** — a short compact glyph or braille-cell sequence that indicates "pitch down 12°" or "yaw right 4°" relative to a local neutral. The glyph articulation doc's orientation-bearing primitives fit this role.

3. **Per-bone label glyph conventions** — if the articulation doc defines canonical short labels for bones (e.g. `LLg` for lower_leg_l, `Hip` for hips), use those consistently in the new section. Saves horizontal space and reads as data.

### Deferred

1. **Full body-shape glyph synthesis** — any attempt to render the whole body as a composed glyph picture. This is text theater embodiment work and competes with the existing embodiment renderer. Don't build a parallel path.

2. **Glyph-as-control input** — any mechanism where glyphs are typed or selected to drive pose state. The range_gate surface is observability only. Control goes through `workbench_set_pose_batch`.

3. **Animated glyph sequences** — time-evolving glyph renders showing motion. The motion layer owns sequencing; the blackboard is a snapshot surface.

4. **Glyph-based measurement overlays on the web theater** — explicitly out of scope per the corrected execution rule. Web-theater text stays selective and special-purpose.

5. **Glyph-to-body-shell mapping** — the glyph articulation doc describes articulation authority existing elsewhere. Don't route that authority through the blackboard. The blackboard reads articulation state; it does not define it.

### Recommendation

Codex should read the two glyph docs end-to-end before implementing the `range_gate` detail field, then pick only the primitives from sections 1–3 above. If a primitive from the docs is not in those three categories, it is deferred — even if it looks useful.

## Q5 — Corrected execution order

This order treats Q1 and Q2 as truth repair (must come first), Q3 as the first new surface built on repaired truth, Q4 as a consumer of Q3, and explicitly defers anything else.

1. **Q1 neutral-anchor repair** — fix the sweep baseline reset to use `workbench_clear_pose {all: true}` in pose mode, not `workbench_reset_angles`. One-commit change. Verify via single-variant sweep: `pose_transform_count` must move off 0 and `cache_advanced_after_command` must be `true`.

2. **Re-run the three carrier-chain sweeps** from the earlier calibration trajectory (`hips offset.z`, `hips pitch`, `spine pitch`) with the repaired baseline. This is the empirical discriminator for the user's carrier-chain hypothesis. Outcome becomes the actual gradient evidence the ranker should eventually consume. **Do not retune the ranker yet.**

3. **Bias A kneel-route repair** — duplicate foot's plant/brace discrimination for knee/hand at `main.js:4458–4472`. ~8 lines. Verify via fresh sweep: does any grounded-knee variant produce a non-zero reward delta that wasn't visible before?

4. **Bias B kneel-route repair** — move `upper_leg_l` from `compensation_bone_ids` to `carrier_bone_ids` in both `half_kneel_l_topology` and `half_kneel_r_topology` at `main.js:5262–5289`. Verify via fresh sweep + visual inspection on the workbench.

5. **Bias C kneel-route repair** — extend `route_targets` in `_envBuilderHalfKneelTransitionTemplate` at `main.js:1508` with carrier and anchor-ankle placeholders. Verify via fresh sweep.

6. **Q3 `range_gate` blackboard family** — new builder function called from `_envBuildBlackboardState`, new section in `scripts/text_theater.py`, working_set `range_gate_targets` populated from active controller. Read-only; observability only.

7. **Q4 glyph primitive import** — pick range-bar, per-axis orientation, and per-bone label conventions from the glyph docs; use them inside the `range_gate` section rendering. Defer everything else in those docs.

8. **Ranker retune against empirical sweep evidence** — only now, with trustworthy sweeps and the kneel-route bias repaired. Change the ranker heuristic branches to read from a new `calibration` / `sweep_result` history store (orthogonal to this report's scope; not Vitruvian). Do not pre-commit to any ranker change until steps 1–5 have produced real gradient data.

9. **Defer** — Bias D knee patch geometry, web-theater text effects, Additions 1+2 from the earlier trajectory report (`observe(signal_type='mechanics_v1')` capsule wiring), any Pan work, any HD speculation. All deferred until steps 1–7 land and the kneel convergence story has actual evidence behind it.

## Summary

- **Q1 root cause probably found:** `workbench_reset_angles` is structure-mode and mode-gated; the sweep baseline reset was almost certainly being rejected with `MODE MISMATCH`, which is the exact fingerprint of `cache_advanced_after_command=false`. Fix is to use `workbench_clear_pose {all: true}` in pose mode.
- **Q2 kneel bias has four sources**, three of which are tractable (knee support role hardcoded to brace; upper_leg_l in compensation not carrier; route_targets has only two entries) and one that should stay deferred (knee contact patch shape).
- **Q3 Vitruvian surface is a single new `range_gate` family** added to the existing blackboard contract and rendered as a new section in `text_theater.py`. No new system, no new control plane, no new renderer, no web surface.
- **Q4 glyph docs have three immediately useful primitives** (range-bar, per-axis orientation, per-bone labels); everything else defers.
- **Q5 execution order** puts truth repair before surface building, verifies at each step, and defers everything that isn't on the kneel-convergence arterial.
