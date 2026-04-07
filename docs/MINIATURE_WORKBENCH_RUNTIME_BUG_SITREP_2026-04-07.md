# Miniature Workbench Runtime Bug Sitrep 2026-04-07

## Purpose

Record the exact facts known so far about the "floating miniature" mounted builder/runtime issue, document the temporary recovery approach, and preserve the perceived future-risk model so later sessions do not "fix" the symptom in the wrong place.

This document is intentionally narrow. It is not a root-cause claim. It is a current evidence handoff.

## Current Baseline

- Checkpoint baseline: `99b935b`
- Commit timestamp: `2026-04-06 20:49:34 -0400`
- Commit message: `Checkpoint text theater parity stabilization`

Tracked content has been re-verified against that checkpoint in substance:

- `git diff --ignore-cr-at-eol --ignore-space-at-eol --stat 99b935b -- scripts/generate-env-help-registry.js scripts/text_theater.py server.py static/data/help/environment_command_overrides.json static/data/help/environment_command_registry.json static/main.js`
- Result: no content diff

This matters because the miniature/floating state persisted after reset/refresh from that baseline.

## Known Facts

### 1. The live runtime and the live balance truth disagree

On `2026-04-07`, live reads showed:

- `shared_state.focus.kind = character_runtime`
- `shared_state.scene.cameraMode = focus`
- `shared_state.scene.theaterMode = character`
- `runtime_state.mode = anchored`
- `runtime_state.grounded = true`
- `runtime_state.support_key = ground::default`
- `runtime_state.position.world.y = 1.768`
- `runtime_state.visual_mode = builder_subject`

At the same time, `text_theater_snapshot` showed:

- `balance.support_phase = airborne`
- `balance.supporting_joint_ids = []`
- `balance.stability_risk = 1`
- `foot_l gap = 1.3306`
- `foot_r gap = 1.3306`
- `render.workbench_stage_guide.floor_y = 0.275`

So the current bad state is not "just visual." The system currently carries a real contradiction:

- mounted runtime says "grounded on ground::default"
- builder/contact truth says "airborne with both feet gapped"

### 2. Shared-state / text-theater / mirror surfaces are serializers, not direct size writers

The following surfaces package existing state:

- `sharedState.text_theater = { ... }` in `static/main.js`
- `_envBuildTextTheaterSnapshot(...)` in `static/main.js`
- live mirror packaging in `static/main.js`
- `env_read` / server live-cache exposure in `server.py`

They are clone/serialization paths built around `_envCloneJson(...)`, not mesh transform writers.

These surfaces can make a bad state visible, but they are not currently proven to be the size authority.

### 3. Current size authority is explicit

The whole mounted workbench mesh is scaled here:

- `_envCharacterWorkbenchDisplayScale(...)` in `static/main.js`
- `_env3DApplyCharacterWorkbenchCamera(...)` in `static/main.js`

Critical lines:

- `mesh.scale.setScalar(displayScale);`
- `mesh.userData.baseScale = displayScale;`

This is the active whole-mesh size write for the workbench path.

### 4. Current vertical placement authority is explicit

Mounted runtime Y is snapped here:

- `_envInhabitantSupportOffset(...)` in `static/main.js`
- `_envMountedRuntimeWorkbenchGroundSupport(...)` in `static/main.js`
- `_envInhabitantSnapMeshToSupport(...)` in `static/main.js`

Critical line:

- `mesh.position.y = targetY;`

### 5. Builder local group scaling is not the primary size authority

Builder subject staging resets the local builder group:

- `_env3DScaleBuilderSubjectForWorkbench(...)`
- `group.scale.setScalar(1);`

And the file itself states:

- `Workbench display scale is the sole size authority for the builder body.`

That means future debugging should treat the builder group and the mounted mesh as separate transform layers.

## What Is Not Proven

The following are not proven yet:

- that a recent text-theater or mirror change directly resized the model
- that the current miniature state came from the browser camera alone
- that the current miniature state came from floor alignment alone
- that the root cause is a newly introduced code-content change after `99b935b`

Right now, the strongest evidence says:

- the bad state persists even after returning tracked content to the parity checkpoint baseline
- therefore the issue is either:
  - a pre-existing runtime/persistence bug
  - a persisted bad state being re-applied
  - a transform feedback bug already present in the workbench size/support path

## High-Risk Seam

The most suspicious future-risk seam is the workbench display scale feedback path:

1. `_env3DApplyCharacterWorkbenchCamera(...)` computes `sceneScale` from:
   - `obj.scale`
   - or `mesh.userData.baseScale`
   - or `1`
2. it computes `displayScale`
3. it writes:
   - `mesh.scale.setScalar(displayScale)`
   - `mesh.userData.baseScale = displayScale`

This means output can become future input.

That does not prove the current miniature bug, but it does match the exact class of risk being perceived here:

- a temporary wrong scale becomes the new baseline
- a future recompute multiplies again from the wrong baseline
- ratio errors compound over time

This is the seam to treat as "exponential blow-up / re-growth risk" until disproven.

## Temporary Recovery Approach

The temporary recovery approach is intentionally pragmatic and explicitly not a root-cause fix:

1. restore the visible mounted workbench subject to an acceptable scale using the current size authority
2. ensure the subject is visually settled back into a usable working state
3. continue normal work
4. keep isolating the root bug in parallel across future sessions

Important:

- if this temporary recovery is used, it must be documented as a stopgap
- the stopgap must not be later confused with the true bug fix
- any future scale event must be compared against this sitrep first

## Guardrails For The Temporary Recovery

If a temporary scale-up is applied before full root-cause isolation:

- do not describe it as "fixed"
- do not change multiple transform layers at once
- do not patch both workbench display scale and support offset in one move
- do not normalize away the symptom without recording the exact pre-fix runtime values
- capture pre and post values for:
  - `runtime_state.position.world.y`
  - `runtime_state.grounded`
  - `balance.support_phase`
  - `balance.supporting_joint_ids`
  - `foot_l gap`
  - `foot_r gap`
  - `mesh.scale`
  - `mesh.userData.baseScale`

## Isolation Plan

Future sessions should isolate in this order:

1. verify whether theater session restore is rehydrating a bad mounted/builder state
2. inspect whether `mesh.userData.baseScale` is already wrong before `_env3DApplyCharacterWorkbenchCamera(...)` runs
3. inspect whether `_envCharacterWorkbenchDisplayScale(...)` is computing from scaffold/local bounds that are themselves already skewed
4. inspect whether `_envInhabitantSupportOffset(...)` or mounted support snapping is producing the contradictory "grounded but airborne" state
5. only after that, decide whether the real fix belongs in:
   - session restore
   - display-scale authority
   - support offset / snap-to-support
   - bounds derivation

## Why This Sitrep Exists

This bug now has two separate realities:

- the visible symptom: the model is a floating miniature
- the strategic risk: a bad scale baseline may get re-used later and create a much larger proportional failure

The immediate stopgap and the long-term root fix must not be conflated.

That is the core point of this handoff.

## Exact Omission Found

On 2026-04-07 the first concrete builder-side omission was identified in source:

- asset-ready path clears `mesh.userData._supportOffsetY = 0` before re-snapping the mounted runtime
- builder-stage path rebuilt and re-staged the visible body without clearing that same cached support offset

Relevant source anchors:

- asset-ready reset and snap:
  - [static/main.js](/F:/End-Game/champion_councl/static/main.js:44138)
  - [static/main.js](/F:/End-Game/champion_councl/static/main.js:44140)
- builder-stage path before the fix:
  - [static/main.js](/F:/End-Game/champion_councl/static/main.js:46082)

Live contradiction that made this omission actionable:

- `scene.physics.ground_y = 0`
- mounted runtime `world.y = 1.768`
- mounted runtime `grounded = true`
- mounted runtime builder surface:
  - `builder_active = true`
  - `scaffold_visible = true`
  - `scaffold_piece_count = 17`
- exported visual bounds:
  - `min.y = 1.1199999742507933`
  - `max.y = 3.464236204899909`

That combination is consistent with a stale support offset being reused after builder geometry changed.

## Narrow Fix Applied

Applied in [static/main.js](/F:/End-Game/champion_councl/static/main.js:46082):

- after builder staging, if the mesh is the mounted character runtime:
  - clear `mesh.userData._supportOffsetY`
  - immediately call `_envInhabitantSnapMeshToSupport(...)`

This is intended as the first concrete root-cause fix for the floating state, not a generic scale patch.

## Post-Fix Verification

After reload on 2026-04-07, live surfaces changed as follows:

- mounted runtime workbench surface:
  - `builder_active = true`
  - `scaffold_visible = true`
  - `scaffold_piece_count = 17`
  - `bone_count = 19`
- text-theater balance surface:
  - `support_phase = double_support`
  - `supporting_joint_ids = ['foot_l', 'foot_r']`
  - `stability_risk = 0.0529`
  - `inside_polygon = true`
- mounted runtime export surface:
  - `scale = 1.08`
  - `visual.bounds.size.y = 22.651539923107944`
  - `visual.bounds.min.y = -4.362452961248299`
  - `visual.bounds.max.y = 18.289086961859645`

This confirms the original grounded-vs-airborne contradiction was resolved in live state.

## Remaining Watchpoint

One value still needs future scrutiny:

- mounted runtime `runtime_state.position.world.y` remained `1.768`

That no longer blocks support truth, but it means the runtime anchor height and the visible staged body bounds are not a simple one-to-one reading. That is a follow-up diagnostic seam, not evidence to revert the current fix.
