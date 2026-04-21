# Current Active Trajectory 2026-04-13

Repo: `F:\End-Game\champion_councl`

Purpose:

- give the repo one current operative trajectory after the recent chat-heavy ideation cycle
- pin what is actually in source now versus what is only partially landed
- keep parity/relay, text-theater query-work, calibration, and blueprint work in one sequence
- make the next checkpoint legible

This doc is the current operative handoff. It does not delete the earlier trajectory/sitrep docs. It supersedes them only where this report names a corrected execution order or a corrected source reading.

## 0A. 2026-04-18 Reactive Stream Pivot

Read this doc together with:

- `docs/REACTIVE_COIN_STREAM_TRAJECTORY_2026-04-18.md`

Current live correction:

- the meme-coin lane is no longer best framed as a social / club product center
- the stronger current thesis is a reactive stream surface that behaves like the coin's live nervous system
- `F:\End-Game\glassboxgames\twitch-stream` is reference evidence only, not a repo we should import, depend on, or center

Current execution order for this lane:

1. reduce external coin/market events into typed readable state
2. render that state through one stream-facing facility
3. bind operator controls and diagnostics to the same reduced state
4. add treasury / burn pulses only after the visual/state reducer path is truthful

Guard rails:

1. do not treat the donor stream repo as the new authority plane
2. do not let arcade / game / tip-control baggage redefine the lane
3. do not let treasury / burn theatrics outrun the event reducer
4. keep the broader repo doctrine intact while the public stream lane becomes the current hot seam

## 0. 2026-04-14 Live Seam Correction

Read this doc together with:

- `docs/WEATHER_WEB_OVERLAY_SITREP_2026-04-14.md`
- `docs/BLACKBOARD_FIELD_UNIFICATION_SITREP_2026-04-14.md`

Current live correction:

- the repo still carries the relay/parity concerns described below
- but the active orienting surface on the live 2026-04-14 frame is blackboard/query-work
- the live blackboard objective is `Surface Alignment Review`
- weather/rain is the active field exemplar inside that orientation

So do not read this file as license to skip:

1. `env_read(query='text_theater_view', view='render', diagnostics=true)` or `text_theater_embodiment`
2. browser-visible corroboration through the existing capture lane
3. consult / blackboard query-work
4. text theater snapshot
5. `contracts` or `env_report(...)`

And do not treat relay-tier work as the only possible first move for every current seam.

## 1. Non-Negotiable Rules

1. One truth source, no duplicate authority systems.
2. Blackboard is for text theater only.
3. Web-theater text stays selective:
   - special effect
   - measurement overlay
   - text-rendered object surface
4. Text theater and web theater are peer consumers of shared truth.
5. `env_report` is a stateless read-side materializer over existing truth, not a second plane.
6. Repair existing systems before adding new surfaces.

## 2. Current Source-Verified Position

### 2.1 Text-theater-first query-work path is real

Verified in `server.py`:

- `_env_note_text_theater_read(...)`
- `_env_shared_state_prereq_payload(...)`
- consult/query-work requirement for raw state
- `env_report` session-thread build from `shared_state.blackboard.working_set`

Verified in `scripts/text_theater.py`:

- consult view includes:
  - `Orientation`
  - `Query Work`
  - `Evidence Lane`
- blackboard section renderer exists and reads `snapshot.blackboard`

Verified in `static/main.js`:

- `_envBuildBlackboardState(snapshot)` already populates:
  - `working_set`
  - `query_thread`
  - query guardrail text

Operational meaning:

- the gate/query-work path is already real
- blackboard is still not a fully mature worksheet/slate yet
- the next blackboard work is deepening, not invention

### 2.2 Current relay split is only half-landed

Verified in `static/main.js`:

- `_envBuildCameraTextTheaterBundle(...)`
- `_envCompactTextTheaterSnapshotForCamera(...)`
- `_envBuildCameraLiveSyncPayload(...)`

Current truth:

- there is no explicit `relay_tier` field yet
- there is no strict hot whitelist yet
- there is no separate archive relay path yet
- hot camera pulses skip full theater/embodiment string rendering
- but hot camera pulses still carry a cloned text-theater snapshot that is far too large

This is the current parity bottleneck.

### 2.3 Calibration/kneel truth repairs are partly landed

Verified in `server.py`:

- neutral restore uses `workbench_clear_pose {"all": true}` in pose mode

Verified in `static/main.js`:

- knee support-role logic can now discriminate `plant` vs `brace` from patch fields
- half-kneel route criteria permit knee `support_role_in: ['brace', 'plant']`
- route targets include hips + lead upper leg + lead knee + anchor foot
- semantic `carrier_bone_ids` are preserved separately from translation-only carriers

Important live caveat from recent verification:

- the runtime read used during the last pass was not actually inside an active half-kneel route
- `active_controller = none`
- `route_report = null`

So kneel-route source repairs are real, but a clean live half-kneel verification pass still remains.

### 2.4 Load-field semantics improved, but the renderer lane is not finished

Verified in `static/main.js`:

- web load visuals are now driven by `load_field` truth rather than crude local `load_share` tinting alone

But:

- the live interaction lag/parity problem remains upstream of the load display
- further load visualization sophistication should wait until relay cadence is repaired

## 3. Corrected Relay Framing

Do not call these separate mirrors.

They are one truth source with three relay cadences:

### Hot relay tier

For motion ticks only. Carries identifiers and transforms, not heavy analysis.

Intended contents:

- camera pose
- selection id
- focus bone/object id
- hover id
- active-bone highlight id
- Tinkerbell guidance ids later

### Settled relay tier

For debounced post-motion or non-camera state changes.

Intended contents:

- full text-theater render
- full text-theater snapshot
- blackboard snapshot
- route/controller diagnostics
- load-field summary
- `env_report`-backed reasoning consumers

### Archive relay tier

Explicit-trigger only.

Intended contents:

- capture bundles
- provenance/corroboration bundles
- Dreamer episode boundaries/traces

Guard rails:

1. no relay tier owns truth
2. no relay tier writes
3. no relay tier recomputes truth independently
4. blackboard rides settled tier only

## 4. Active Locales In Source

### Relay/parity hot path

- `static/main.js`
  - `_envCompactTextTheaterSnapshotForCamera(...)`
  - `_envBuildTextTheaterCameraSnapshotPatch(...)`
  - `_envBuildCameraTextTheaterBundle(...)`
  - `_envShouldAttachTextTheaterToCameraSync(...)`
  - `_envBuildCameraLiveSyncPayload(...)`

### Text-theater query-work / blackboard

- `server.py`
  - `_env_note_text_theater_read(...)`
  - `_env_shared_state_prereq_payload(...)`
  - `_env_report_build_session_thread(...)`
  - route-stability `recommended_next_reads`
- `scripts/text_theater.py`
  - `_render_blackboard_section(...)`
  - `_consult_query_thread(...)`
  - `_consult_query_evidence(...)`
  - `_render_consult_view(...)`
- `static/main.js`
  - `_envBuildBlackboardState(...)`

### Calibration / Dreamer outer loop

- `server.py`
  - neutral restore
  - mechanics observation payload
  - transform relay
  - bounded sweep
  - reward breakdown / episode step

### Kneel-route truth

- `static/main.js`
  - half-kneel transition template
  - support-role assignment
  - controller record / topology

## 5. Corrected Execution Order

This is the current order. It replaces the overlapping one-off sequences from chat drift.

### Step 1. Finish the relay-tier split

Priority one.

Concrete target:

- add explicit `relay_tier`
- hot tier becomes a strict whitelist
- settled tier carries the real text-theater/blackboard payload
- archive tier stays explicit-trigger only

Success condition:

- web-theater interaction becomes materially smoother
- text theater stays responsive and paired
- hot camera motion no longer drags the full text-theater snapshot

### Step 2. Re-run live half-kneel verification cleanly

Only after Step 1.

Verification sequence must explicitly:

1. clear pose
2. load/apply half-kneel baseline/controller
3. confirm `active_controller`
4. read the text render and paired browser-visible corroboration
5. then inspect route/mechanics truth

This prevents parity lag from contaminating kneel verification.

### Step 3. Deepen blackboard as the visible worksheet

After parity is trustworthy:

- richer query-work lineage
- pinned rows
- row trace/history exposure
- stronger visible scratchpad/slate behavior

No new authority. Same blackboard.

### Step 4. Build the measurement contract

Only after truthful settled snapshots and a verified route/calibration base.

Contract scope:

- per bone
- per chain
- per contact
- whole body
- three frames:
  - absolute now
  - delta from neutral
  - delta from task

This is derivation over truth, not a second model.

### Step 5. Blackboard measurement family

Text theater only.

This is the first real bridge into the later Vitruvian/range-gate/blueprint lane.

### Step 6. Internal scaffold strata

First geometric internal layer over the measurement contract.

Rules:

- derivation only
- no separate cached authority
- geometric, not soft-organic

### Step 7. Negative-space mold view

Renderer/profile over the same shared truth and measurement/scaffold substrate.

Not a new system.

## 6. Blueprint Direction, Correctly Scoped

The blueprint/CAD/anatomical-internal direction stays valid, but it is downstream of repaired truth.

Current rule:

1. fix parity/relay
2. verify route/calibration truth
3. deepen blackboard worksheet
4. build measurement contract
5. build internal scaffold strata
6. then build specialized render profiles

That includes:

- Vitruvian/range/gate surfaces
- internal measurement tapes
- geometric anatomical internals
- negative-space mold view

## 7. What Not To Do Next

1. Do not add more web-theater text surfaces now.
2. Do not build measurement/blueprint contracts over stale parity.
3. Do not retune Dreamer/kneel logic again before a clean live verification run.
4. Do not create a second authority plane for relay, measurement, or scaffold work.

## 8. Immediate Next Build

Current priority:

1. finish the explicit relay-tier split in `static/main.js`
2. validate:
   - `node --check static/main.js`
   - live manual drag
   - live wheel zoom
   - live turntable
3. then checkpoint

Only after that:

4. run a deliberate half-kneel verification pass
5. continue blackboard deepening / measurement work
