# Text Theater Pivot Handoff 2026-04-05

## STATUS: HISTORICAL 2026-04-10

This doc reflects the now-removed settle workflow.
Settle was deleted on 2026-04-10; preserve this file as historical reference
only and do not treat its settle guidance as current runtime doctrine.

Repo: `F:\End-Game\champion_councl`

Purpose:

- preserve the exact active state before the text-theater pivot grows into a larger build lane
- keep the current balance/settle/contact work from being lost
- record what is already proven live versus what is still pending

## Active Truth Before Pivot

The current embodiment lane is no longer only a pose/edit lane.

It now includes:

- contact/support truth
- support polygon
- projected center of mass
- stability margin/risk
- per-segment load/support scoring
- visible builder-side settle preview/commit

The new text-theater direction should be treated as a paired observation instrument over that truth, not as a replacement lane.

## What Is Already Working

### 1. Ground / Contact / Load Mechanics

The builder-side load/contact lane is already real enough to support balance reasoning.

Confirmed earlier in this session:

- healthy grounded builder baseline
- planted double-support presets
- single-support step preset behavior
- `support_y = 0.02`

### 2. Settle Controller

The builder-side settle controller is implemented and live:

- `workbench_preview_settle`
- `workbench_commit_settle`

It now:

- reads balance/load truth
- reacts in both lateral and sagittal directions
- uses continuous response weighting instead of only crude threshold flips
- stages visible corrective micro-timelines

### 3. Pose Commands

The pose command lane is working again after the stale-bundle fix:

- `workbench_set_pose`
- `workbench_set_pose_batch`

Important live truth:

- the browser had been pinned to stale bundle `130y`
- bundle refs were bumped to `130z`
- pose changes now stick again when verified after ingress/live-sync settles

### 4. Env Help

`env_help` has already been updated with the practical gotchas from this debugging pass.

It now captures:

- payload goes through `target_id` for pose/settle commands when driven through `env_control`
- `workbench_set_pose_batch` uses `poses`, not `bones`
- immediate mirrored `shared_state` reads can lie for a few seconds
- the right verification fields are:
  - `workbench_surface.pose_transform_count`
  - `workbench_surface.posed_bone_ids`
  - `workbench_surface.settle_preview`
  - `corroboration.last_action`

## What Is Proven Live

These paths were proven in the current runtime after the bundle fix:

- `workbench_set_pose`
- `workbench_set_pose_batch`
- `workbench_preview_settle`
- `workbench_commit_settle`

Observed live:

- batch pose moved the live projected CoM
- settle preview generated real analysis and strategy weights
- mild/ankle settle behavior is proven
- a high/severe step-style settle path was proven earlier in the lane

## What Is Still Pending

These are the remaining active gaps from the settle/contact lane.

### 1. Hip-Regime Corroboration

The middle settle regime still needs a clean explicit corroboration pass:

- mild -> ankle
- medium -> hip
- severe -> step

The system is already continuous now, so this is mostly about proving the middle band honestly rather than inventing new mechanics.

### 2. Mounted Asset Ground Corroboration

The `npc.glb` mounted-asset path still needs the clean visual corroboration pass:

- mount
- inspect planted feet visually
- confirm the floor truth holds in the mounted path

### 3. Contact Generalization

The solver is still:

- `supportingFeet`

Not yet:

- `supportingContacts`

So the current lane is honest for foot-ground support and balance-driven settle, but not yet for fully smart brace/fall/catch behavior using hands/knees/elbows/back/head.

### 4. Carpenter / Level Instrument

Still planned, not built.

The current settle controller works without it because it reads the underlying balance truth directly.

### 5. Voxel / Substrate Depiction

Still planned, not built.

The load/balance computation exists, but the richer inner substrate depiction is still ahead.

## What The Text Theater Must Not Forget

The text-theater pivot should preserve these live truths:

1. The browser theater is still the visual truth surface.
2. The text system should be paired to live runtime truth, not become a second fake renderer.
3. The text system should consume real state from:
   - `shared_state`
   - `workbench_surface`
   - balance/load/contact diagnostics
   - scene/camera/focus state
   - replay/trajectory state
4. The text system should support both:
   - full theater/environment view
   - embodiment / isolated chain / scaffold view

## Immediate Next Step After This Handoff

The clean next move is:

1. define a canonical `text_theater_snapshot` contract
2. build the first repo-local text render from live runtime truth
3. keep the current settle/contact lane ready to resume for:
   - hip-regime corroboration
   - `npc.glb` mounted corroboration
   - later `supportingContacts`

## Bottom Line

We are not leaving an unfinished random mess behind.

The current active state is:

- balance/load/contact truth exists
- settle preview/commit exists
- pose command lane is working again
- env_help captures the recent runtime gotchas
- the next pivot is to build a paired text-native observation surface over this live system

If the text-theater build stalls or branches, resume from this file first, then continue the settle/contact lane.

## 2026-04-07 Alignment Note

The next mechanics/display return should be treated as bone-first, not scaffold-first.

Alignment update:

- mechanics truth remains on canonical joints, contact patches, mass proxies, and load/support diagnostics
- scaffold may carry diagnostics when visible, but should not own the physics lane
- future skin/body shell remains a later product-facing carrier

See:

- [`docs/BONE_FIRST_PHYSICS_ARCHITECTURE_2026-04-07.md`](/F:/End-Game/champion_councl/docs/BONE_FIRST_PHYSICS_ARCHITECTURE_2026-04-07.md)

## 2026-04-07 Live Verification Addendum

Post-refresh live MCP verification now confirms:

- `env_control` is returning attached text-theater observation payloads
- `workbench_assert_balance` is implemented and live
- the attached text view shows `ASSERT: PASS double_support / risk 0.05 / supporting foot_l, foot_r`
- attached snapshot freshness is honest and reports fresh cache advancement on the mutation path

So the text-theater pivot is no longer only a query lane. It is now partially in the command/result loop.

Immediate next text-theater trajectory from this handoff:

1. keep command-attached `current` view live
2. harden sync-classification / camera-only partial routing
3. add payload-policy discipline
4. then build primitive-first export and compare/on-deck
