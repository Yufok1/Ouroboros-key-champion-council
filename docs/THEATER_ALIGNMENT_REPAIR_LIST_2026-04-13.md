# Theater Alignment Repair List 2026-04-13

Purpose: collate live discrepancies between text theater, web theater, snapshot/shared truth, and mirrored summaries after the current reset, then turn them into a repair sequence.

## Current Reads

Live reads used:
- `env_read(query='text_theater_embodiment')`
- `env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)`
- `env_read(query='text_theater_view', view='render', diagnostics=true)`
- `env_read(query='text_theater_snapshot')`

Source seams read:
- [static/main.js](../static/main.js)
- [scripts/text_theater.py](../scripts/text_theater.py)

## What Already Aligns

- `world_profile.active = island_cove` and `world_profile.family = coastal` align between the text-theater snapshot and the web render truth in `snapshot.render.world_profile`.
- `scene.object_count = 14` aligns between the text-theater snapshot and the web render truth.
- The text-theater snapshot is fresh for the current camera preset frame:
  - `bundle_version = 131j`
  - `stale_flags.mirror_lag = false`
  - `last_sync_reason = camera:preset:overview`

These are not the current breakpoints.

## Repair Ledger

### 1. Snapshot Weather Exists, But The Local Theater Sidebar Drops It

Classification:
- contract-consumer mismatch
- rendering mismatch

Confirmed:
- `snapshot.weather` is populated in live state:
  - `enabled = true`
  - `kind = rain`
  - `flow_class = precipitation`
  - `density = 0.62`
  - `speed = 1`
- JS-side summary builder includes a weather line in source:
  - [static/main.js](../static/main.js:32112)
  - [static/main.js](../static/main.js:32248)
- Python local theater summary omits weather entirely:
  - [scripts/text_theater.py](../scripts/text_theater.py:4643)

Observed symptom:
- `text_theater_view(render).theater_text` shows `THEATER`, `CAMERA`, `BUNDLE`, `PARITY`, `SCENE`, `RUNTIME`, `NEARBY`
- no `WEATHER` line appears even though snapshot weather is active

Why it matters:
- the operator-facing theater summary disagrees with the actual snapshot contract for the same frame

Repair:
- add `WEATHER` to `_render_local_theater_text(...)`
- keep format aligned with the JS summary builder

Priority: P1

### 2. Consult / Blackboard Query Work Is Blind To Active Weather

Classification:
- consult mirror mismatch
- query-work objective mismatch

Confirmed:
- live blackboard/query-work objective stays on `Scene Orientation`
- help lane points only at `text_theater_embodiment` and a pose corroboration playbook
- no weather rows, no weather help lane, no weather next reads
- source objective selection has no weather-aware branch:
  - [static/main.js](../static/main.js:31544)

Observed symptom:
- consult view says the visible read is `Humanoid Biped. CoM outside support polygon (0 risk).`
- active weather is absent from query objective, help lane, and next reads

Why it matters:
- consult/query-work is supposed to stage the active seam
- it is currently staging embodiment/balance only, even in an environment-weather frame

Repair:
- introduce a weather-aware query objective branch when `snapshot.weather.enabled`
- add weather-specific help lane / next-read steps
- avoid collapsing weather into balance/pose orientation

Priority: P1

### 3. Weather Is In The Snapshot Contract, But Not In Shared-State / Web Mirror Contracts

Classification:
- truth/contract ownership gap
- web peer-consumer gap

Confirmed in source:
- text-theater snapshot owns a `weather` field:
  - [static/main.js](../static/main.js:32897)
- browser live sync/shared-state builder carries `world_profile` but no `weather` field:
  - [static/main.js](../static/main.js:62590)
- web render truth surface also exposes `world_profile` but no `weather` payload:
  - [static/main.js](../static/main.js:37587)

Observed consequence:
- text theater has a weather contract
- web theater and live/shared mirrors do not have an equivalent weather contract yet

Why it matters:
- weather can never be brought into peer-theater alignment if it only exists on the text-theater snapshot path
- this also makes raw/shared-state corroboration weaker for the weather lane

Repair:
- decide and pin ownership:
  - either `shared_state.weather` becomes the producer truth
  - or weather remains text-theater-only by doctrine and all docs/help must say that explicitly
- if peer-theater parity is intended, add weather to the shared/live mirror contract

Priority: P1 architectural

### 4. Weather Currently Reads As Anonymous Floating Specks, Not Directional Weather

Classification:
- rendering failure

Confirmed in source:
- weather rows are emitted as isolated points with a glyph and world size:
  - [scripts/text_theater.py](../scripts/text_theater.py:2887)
- weather render pass places single glyphs / blobs / dots at those points:
  - [scripts/text_theater.py](../scripts/text_theater.py:4270)
- there is no streak/segment rendering in the current weather path

Observed symptom:
- the user reads the weather field as placeholder or unregistered floating objects
- the render view shows sparse free-floating marks rather than an obvious rain/current field

Why it matters:
- the field is present, but it does not identify itself visually as weather
- this is the main perceptual failure right now

Repair:
- add directional segment/streak rendering for precipitation/current far-field bands
- keep object glyphs and weather glyphs visually distinct
- prefer field-shaped marks over anonymous isolated specks for `spec/blob` weather bands

Priority: P1

### 5. The Local Projection Path Ignores `surface_mode` For Sharp/Cell Rendering

Classification:
- rendering mismatch
- control mismatch

Confirmed in source:
- `_render_projection(...)` hardcodes `use_cell_canvas = False`
  - [scripts/text_theater.py](../scripts/text_theater.py:3595)
- current text-theater control reports `surface_mode = sharp`
  - live `snapshot.text_theater_control.surface_mode`

Observed consequence:
- even in `sharp` mode, the local perspective scene render stays braille-first
- crisp glyph weather / object rendering cannot actually engage in the current local scene projection path

Why it matters:
- the control surface advertises `sharp`
- the renderer cannot honor it in the projection path that matters most for scene/weather

Repair:
- make `use_cell_canvas` depend on `surface_mode`
- define exactly which bands/materials use cell vs braille in `sharp`, `granular`, and `legacy`

Priority: P1

### 6. Scene Render Falls Back To Object Legend Instead Of Carrying The Scene Clearly

Classification:
- rendering weakness
- scene legibility gap

Confirmed in source:
- `_render_projection(...)` always appends:
  - `Perspective · fixed camera/stage/body projection`
  - `Objects: ...`
  - [scripts/text_theater.py](../scripts/text_theater.py:3595)
  - [scripts/text_theater.py](../scripts/text_theater.py:3606)

Observed symptom:
- the rendered scene box is visually sparse
- the bottom legend becomes the most legible description of the scene

Why it matters:
- when the picture is weak and the legend is strong, weather specks and object summaries compete instead of forming one readable scene

Repair:
- improve actual scene depiction before widening legend text
- reduce dependency on the `Objects:` fallback line once the scene/weather substrate reads clearly

Priority: P2

### 7. Direct Weather Controls And `env_help` Weather Topics Do Not Exist Yet

Classification:
- control plane gap
- discoverability/help gap

Confirmed:
- no matches for:
  - `set_weather`
  - `weather_control`
  - `weather_density`
  - `weather_speed`
  - `weather_turbulence`
  - `weather_direction`

Observed consequence:
- the only current way to change weather is through `set_world_profile`
- this also changes biome/world visuals, which contaminates weather testing

Repair:
- add first-class weather control commands
- add `env_help(topic='weather_control')`
- keep weather controls local to `env_help`, not global `get_help`

Priority: P2

### 8. World Profile And Weather Are Coupled Too Tightly For Clean Evaluation

Classification:
- control/design coupling

Confirmed in source:
- weather kind/family are derived directly from `world_profile.family`
  - [static/main.js](../static/main.js:30581)

Observed consequence:
- changing weather also changes the biome/theme
- this can masquerade as theater/render regressions during evaluation

Repair:
- keep world profile as the default driver
- add an explicit weather override lane for testing/evaluation

Priority: P2

## Recommended Repair Order

1. Fix the local theater summary and consult surfaces so active weather is visible where the operator is already looking.
2. Fix the local weather render so it reads as directional weather instead of anonymous floating marks.
3. Honor `surface_mode` in the local perspective renderer so `sharp` actually means sharp.
4. Decide and pin weather ownership across snapshot/shared-state/web mirror contracts.
5. Add dedicated weather control commands and `env_help` topics.
6. Decouple weather evaluation from biome switching with a weather override lane.

## Notes

- Raw `shared_state` live reads were still gated by the text-theater query-work guardrail during this pass.
- That did not block the main repair list because the source already shows a structural weather contract gap outside the text-theater snapshot path.
