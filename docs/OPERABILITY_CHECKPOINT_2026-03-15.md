# Operability Checkpoint

Date: 2026-03-15
Workspace: `F:\End-Game\champion_councl`
Scope: frontend/control-surface operability in the Environment tab, with runtime/capsule edits explicitly deferred unless proven necessary

## Executive Sit Rep

The project has two distinct threads that must not be conflated:

1. `agent_compiler.py` / skills-system work in `F:\End-Game\ouroboros-key`
2. live Environment-tab operability work in `F:\End-Game\champion_councl`

The skills-system thread is largely complete at the source level. The live Environment-tab thread is not complete and is currently in a mixed state:

- the local frontend files in `champion_councl/static/` contain new operability-oriented edits
- the live browser/mirror state is still clearly reporting the old frontend bundle and old control behavior
- therefore the new frontend changes have not yet been verified live

The most important operational fact right now is:

The current live Environment shell is still behaving as if it is serving the pre-edit frontend, even after browser refreshes and backend resets.

Do not assume the new frontend code is active just because it exists in the local workspace.

## What We Were Trying To Do

The goal shifted away from "make the theater prettier" and toward a broader control-plane operability problem.

The user wanted:

- better granular controls in the Environment tab
- smoother operations between scene, panel, docs, debug, mirror, workflow, and live model activity
- frontend-first changes before touching `champion_gen8.py` or `capsule.gz`
- a deferred runtime TODO list for anything that genuinely cannot be solved in the frontend

The working diagnosis became:

- the backend/runtime truth is fairly strong
- the theater/control-surface layer is comparatively weak
- the main issue is overlapping operational truth, not lack of raw information
- scene, panel, docs, mirror, focus/camera, and workflow/clerk state all compete for authority

## Confirmed Wins Before The Frontend Drift

These things were genuinely working and should be preserved conceptually:

- `get_help(topic=...)` skills system was implemented in `agent_compiler.py`
- `get_cached` discoverability was improved in the compiler/runtime docs
- provider-backed plugging was proven to work through local HF router URLs
- three provider-backed models were plugged successfully for a benign evaluation loop
- a clerk-managed benign tool-eval arena was created in the Environment scene
- a single consolidated report panel replaced multiple mini report boards

Important live artifacts/documents that already exist:

- `docs/tool_eval_tracker_benign_v1`
- `docs/tool_eval_round_*`
- `docs/knowledge_transfer_experiment_v2_eval`
- `docs/operability_interpretive_report_2026-03-14.md`
- `docs/operability_exploration_map_2026-03-14.md`
- `docs/frontend_first_operability_backlog_2026-03-14.md`
- `docs/runtime_todo_deferred_champion_gen8_2026-03-14.md`
- `docs/panel_truth_hierarchy_note_2026-03-14.md`
- `docs/agent_reorientation_frontend_fluidity_2026-03-15.md`

## What Was Learned From Live Diagnosis

The live mirror repeatedly showed the same structural problems:

- scene-first mode remained semantically primary
- the visible report panel never fully became authoritative
- docs context stayed stale relative to the visible scene/report
- live mirror corroboration existed, but without strong primary/canonical framing
- camera/focus/system activity still felt like it could reclaim attention from the operator

The strongest live-state evidence:

- focus remained `scene`
- docs stayed on round-2 artifacts while the report/clerk spoke about later rounds
- runtime/workflow contracts could say `idle` while the visible evaluation machinery appeared active
- `restore_focus_on_activate` remained `true` in the live mirrored shared state
- live mirror kept reporting bundle version `76`

## Local Frontend Changes Currently In The Working Tree

These changes are present locally right now and are not yet proven live:

### `static/main.js`

Local changes include:

- `restoreFocusOnActivate` default changed from `true` to `false`
- corroboration label changed from `LIVE CORROBORATION` to `LIVE MIRROR · SECONDARY`
- new scene-oriented helpers were added:
  - `_envSceneObjectKey`
  - `_envSceneObjectCatalog`
  - `_envSceneFindObject`
  - `_envSceneObjectByKindId`
  - `_envPlainSceneText`
  - `_envExtractSceneRound`
  - `_envExtractSceneTool`
  - `_envScenePrimaryPanelObject`
  - `_envSceneControlObject`
  - `_envSceneCanonicalState`
  - `_envRenderSceneKernel`
- scene-first rendering was changed to:
  - add shell-level cards for canonical surface, operator truth, corroboration, and deferred mismatch
  - replace the old scene placeholder kernel with a compact scene control console
- docs panel was reframed as `Related Evidence` instead of an implicit co-equal truth surface

### `static/envops.config.json`

Local change:

- `actors.restoreFocusOnActivate` changed from `true` to `false`

### `static/panel.html`

Local change:

- script URL bumped from `main.js?v=76` to `main.js?v=77` in an attempt to force asset refresh

## Critical Current Fact

Despite those local edits, the live Environment mirror still reported:

- `restore_focus_on_activate: true`
- `bundle_version: "76"`
- old report/docs/focus state

That means one of the following is true:

1. the running app is not serving from these local static files
2. the running app serves these files through another build/export path that was not updated
3. the browser/webview is pinned to an older served asset despite reset attempts
4. live mirror publication is stale enough to be misleading about actual rendered state

The safest assumption is:

the asset-serving path is not yet understood well enough to trust live verification

## Do Not Lose This Distinction

There are now two realities:

### Local workspace reality

`git status` currently shows modified frontend files:

- `static/main.js`
- `static/envops.config.json`
- `static/panel.html`

These edits parse cleanly locally, but they are unverified in the live app.

### Live environment reality

The MCP live mirror still reflects the old frontend behavior and bundle metadata.

Do not report the new controls as live until the serving path is proven.

## Why The Last Step Likely Went Wrong

The mistake was not purely conceptual. The sequence was wrong.

The frontend refactor was attempted before the asset-serving path was proven trustworthy.

The proper sequence should have been:

1. prove which exact frontend asset files the live app serves
2. prove asset version propagation in the live mirror
3. only then modify cockpit/control behavior
4. verify each change live before adding more

Instead, the work reached a state where:

- the local source changed
- the live app did not demonstrate those changes
- user experience did not improve
- confidence in what was actually running dropped

## Current Constraints

The user was explicit:

- prefer frontend-first work
- avoid `champion_gen8.py`
- avoid `capsule.gz`
- runtime-side issues can be tracked in TODO form and deferred

This constraint still stands unless the next agent can show a specific hard block that truly requires runtime edits.

## Recommended Next-Agent Approach

The next agent should not start by adding more UI.

The next agent should first answer this narrower question:

What exact asset path and bundle identity is the live Environment tab actually serving?

Suggested order:

1. prove the serving path for `panel.html`
2. prove the serving path and live version for `main.js`
3. prove whether `envops.config.json` changes propagate live
4. only after that, decide whether to:
   - keep the local frontend edits
   - refine them
   - or revert them and rebuild incrementally

## Immediate Priorities For The Next Agent

Priority 1:

- trace the asset-serving path for the Environment tab and determine why live still reports bundle `76`

Priority 2:

- decide whether the local `static/*` edits should be retained or rolled back pending proper live verification

Priority 3:

- re-establish a single source of truth for what is running:
  - local files
  - served files
  - mirrored live state
  - visible browser shell

Priority 4:

- only after the above, resume granular Environment-tab control work

## If The Next Agent Wants To Continue Frontend-First

The best frontend-only targets remain:

- a real operator spine in scene-first mode
- explicit canonical vs corroboration labeling
- docs as supporting evidence instead of competing truth
- visible recovery/reopen/stabilize controls
- reduced focus restoration pressure

But those should not be pursued further until live asset truth is nailed down.

## Current Local Diff Summary

At the time of this checkpoint, the local working tree includes:

- modified `static/main.js`
- modified `static/envops.config.json`
- modified `static/panel.html`
- unrelated modified `capsule/capsule.gz`
- unrelated untracked docs and folders

Do not casually revert unrelated user work.

If the next agent chooses to revert the frontend edits, it should revert only:

- `static/main.js`
- `static/envops.config.json`
- `static/panel.html`

and only after confirming that is the desired move.

## Handoff Prompt

Use this to orient the next agent:

You are taking over live Environment-tab operability debugging in `F:\End-Game\champion_councl`.

Read first:

- `docs/OPERABILITY_CHECKPOINT_2026-03-15.md`

Then ground yourself with local and live truth:

- `git status --short`
- `git diff -- static/main.js static/envops.config.json static/panel.html`
- `env_read(query='live')`
- `env_read(query='snapshot')`
- `feed(n=10)`
- `get_cached(...)` as needed

Important:

- do not assume the local frontend edits are actually live
- the live mirror is still reporting bundle version `76` and `restore_focus_on_activate: true`
- local `panel.html` now points at `main.js?v=77`, but that has not been proven to be the served asset
- do not touch `champion_gen8.py` or `capsule.gz` unless you can demonstrate a hard block that genuinely requires runtime-side changes

Your first task is not "improve the cockpit."

Your first task is:

determine the real asset-serving path and explain why the live Environment shell is still presenting the old frontend state

Only after that should you decide whether to keep, refine, or revert the local frontend edits.
