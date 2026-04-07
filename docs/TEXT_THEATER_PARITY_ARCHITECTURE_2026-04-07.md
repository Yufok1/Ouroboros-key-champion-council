# Text Theater Parity Architecture 2026-04-07

Repo: `F:\End-Game\champion_councl`

Purpose:

- re-anchor the text-theater lane after the recent reset/debug cycle
- state the real requirement clearly: text theater is a cheap, frequent, truthful indirect view of the web theater
- prevent the project from drifting into hand-tailored per-feature text render work
- define the missing architecture for before/after, proc-gen, and unknown future scene/body surfaces

## Core Requirement

The text theater is not a separate product surface that must be manually kept up to date feature by feature.

It is a paired observation renderer over the same live browser truth.

The practical goal is:

1. browser/web theater remains the visual truth surface
2. text theater becomes the cheap, frequent, agent-readable indirect view of that same truth
3. both surfaces stay synchronized through one canonical snapshot/model contract
4. before/after observation becomes automatic for relevant actions instead of being manually requested every time

Not:

- bespoke text support for each new mechanic
- a second fake body/scene model
- per-feature one-off render hacks every time proc-gen grows

## What Is Already Real

### 1. Browser -> Snapshot -> Text Publication Path

The browser already exports a real mounted workbench/runtime surface and turns it into a canonical text-theater snapshot:

- mounted workbench surface export: `static/main.js`
- snapshot build: `static/main.js`
- shared publication: `static/main.js`
- server query exposure: `server.py`
- repo-local text rendering: `scripts/text_theater.py`

The live lane is not hypothetical.

### 2. Command Surfaces Already Drive Live Sync

Most relevant workbench and character verbs already refresh runtime state, schedule live sync, and save theater session state.

That includes:

- pose edits
- batch pose edits
- timeline scrub
- motion preset apply
- settle preview
- settle commit
- clip compile/play
- scaffold toggle
- load-field toggle
- character mount/focus/look/clip/loop/speed/reaction

This means the command-to-sync seam already exists.

### 3. Text Theater Already Receives More Than Bones

The current snapshot already carries:

- camera mode / focus
- scene neighborhood
- runtime mode / activity
- embodiment bones and connections
- scaffold visibility plus scaffold pieces
- balance/load/support truth
- contact rows
- settle summary
- timeline state
- selection visual state
- part camera recipes

So the problem is not "no shared state."

The problem is that the renderer and automation layer are still not generalized enough.

## What Is Still Missing

### 1. Generic Scene Primitive Contract

The text theater still knows too much about a few current object/body families and not enough about generalized render primitives.

The missing contract should support generic truth classes such as:

- point
- segment / polyline
- polygon / patch
- box
- ellipsoid / sphere
- capsule / limb
- oriented volume
- label / marker
- object bounds / focus proxy
- optional mesh-proxy silhouette primitive later

If proc-gen emits these primitives honestly from the browser side, the text theater does not need hand-authored support for each future asset or mechanic.

### 2. Automatic Before/After Observation

The current lane is mostly "live now."

It is not yet a proper paired operation surface with:

- frozen pre-action baseline
- current post-action view
- explicit delta summary
- operator-friendly compare mode

There are local baseline concepts in settle/timeline/gizmo lanes, but there is not yet a generic text-theater compare contract.

### 3. Tool-Call Harmonization Policy

The command surfaces already sync, but the text-theater lane is not yet orchestrated as a first-class observation policy for those commands.

The missing policy is:

- which commands auto-capture before
- which commands auto-capture after
- which commands only need current-state refresh
- which commands should freeze a compare pair

### 4. Unknown/Future Proc-Gen Coverage

The current text renderer is still partly embodiment-specific.

That is acceptable for the current lane, but it is not enough for:

- new proc-gen body shells
- new scaffold families
- scene geometry emitted from future generators
- unknown future object classes

The fix is not more special cases.

The fix is to push generalized primitive truth out of the browser and let text theater render primitives, not bespoke feature categories.

## Required Doctrine

### 1. One Truth, Two Renderers

The project should treat the browser and text theater like this:

- browser renderer = primary visual truth
- text renderer = cheap indirect truth
- both consume the same canonical state

If the two differ, the snapshot contract is wrong, stale, or incomplete.

### 2. Text Theater Must Be Truthful, Not Literal

The text theater does not need pixel identity.

It does need:

- exact state parity
- exact temporal parity
- exact diagnostic parity
- equivalent spatial/structural interpretation

The text surface should tell the same truth in a different medium.

### 3. Unknown Future Features Must Flow Through Primitives

Proc-gen should not require separate text-theater implementation work for each new thing.

Instead:

1. browser-side systems emit canonical transform/appearance/primitive truth
2. snapshot publishes that truth
3. text theater renders the primitive vocabulary
4. new systems inherit text coverage automatically when they emit valid primitives

## Recommended Architecture

### Layer 1. Canonical Snapshot

Extend `text_theater_snapshot` so it is explicitly partitioned into:

- scene
- embodiment
- scaffold
- bones
- contact/support/load
- diagnostics
- camera/view
- timing/sequence
- comparison
- generic render primitives

The key addition is a first-class primitive list so non-embodiment scene/proc-gen surfaces do not depend on custom text logic.

### Layer 2. Renderer-Independent Primitive Vocabulary

Each primitive should be described by data, not by a text-theater special case.

Examples:

- `kind: segment`
- `kind: box`
- `kind: ellipsoid`
- `kind: patch`
- `kind: marker`
- `transform`
- `size`
- `points`
- `appearance`
- `visibility_class`
- `truth_class`
- `priority`

Important truth classes:

- `bone`
- `scaffold`
- `skin_proxy`
- `support`
- `contact`
- `scene_object`
- `debug`
- `selection`

### Layer 3. Automatic Observation Policy

Each relevant command should declare an observation policy:

- `none`
- `after_only`
- `before_after`
- `sequence`

Examples:

- `workbench_set_pose` -> `before_after`
- `workbench_set_pose_batch` -> `before_after`
- `workbench_set_timeline_cursor` -> `after_only`
- `workbench_assert_balance` -> `after_only`
- `workbench_preview_settle` -> `before_after`
- `workbench_commit_settle` -> `before_after`
- `character_play_clip` -> `sequence`
- `capture_time_strip` -> `sequence`
- scaffold toggle / skeleton toggle -> `after_only`

This should be automatic in the command lane, not a manual extra step during operation.

### Layer 4. Compare / On-Deck Surface

The text-theater lane should gain an explicit compare product:

- baseline snapshot
- current snapshot
- key deltas
- optional split render

This is the actual "before/after on deck" system needed for positioning, orientation, and motion tuning.

### Layer 5. Freshness / Sync Truth

The text surface must always expose freshness honestly:

- bundle version
- last sync time
- lag status
- mirror staleness hints

If the text theater lags, it should say so clearly instead of pretending certainty.

## Immediate Execution Order

1. preserve current browser/text snapshot parity work
2. stop adding bespoke text support for each new feature where a primitive contract can solve it
3. add a first-class generic primitive export lane to the snapshot
4. add automatic before/after observation policy for relevant command surfaces
5. add a compare render mode over baseline/current snapshots
6. then let proc-gen scenes/skins/scaffold families ride through the same contract

## Bottom Line

The right model is simple:

- do not "develop the text theater alongside everything else"
- develop one truthful canonical observation contract
- let the browser and text theater both consume it
- add automatic before/after capture for the command surfaces that matter

That is the only path that scales to proc-gen, new body shells, new scaffold families, and future unknown scene content without turning text theater into permanent maintenance debt.

## Live Verification 2026-04-07

After reset/refresh, the first command-attached observation lane is verified live through MCP rather than only in source:

- `env_control("workbench_assert_balance")` returned an attached `text_theater` payload
- live delta fields confirmed:
  - `text_theater_attached = true`
  - `text_theater_waited_ms = 832`
  - `text_theater_cache_advanced = true`
  - `text_theater_matched_command_sync = true`
- attached freshness reported:
  - `stale = false`
  - `mirror_lag = false`
- attached snapshot carried live assert truth:
  - `active = true`
  - `passed = true`
  - `status = pass`
  - `support_phase = double_support`
  - `stability_risk = 0.0529`
  - `supporting_ids = [foot_l, foot_r]`
- attached text render surfaced:
  - `ASSERT: PASS double_support / risk 0.05 / supporting foot_l, foot_r`

Read-only command attachment is also live:

- `env_control("character_get_animation_state")` returned an attached `text_theater` payload
- it advanced the cache and returned fresh state
- `matched_command_sync` was `false` there because the sync reason was the generic `env_control:activity`, not a command-specific reason

Updated immediate trajectory:

1. keep the attached observation path
2. tighten sync classification / camera-only partial routing
3. formalize payload policy discipline
4. then extend the primitive-first snapshot and compare lanes
