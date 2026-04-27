# Text Theater Delayed Loop Architecture 2026-04-07

## STATUS: HISTORICAL 2026-04-10

This doc references the now-removed settle workflow.
Settle was deleted on 2026-04-10; preserve this file as historical reference
only and do not use its settle-specific guidance as active doctrine.

## Question

Can the text theater run slightly behind the browser/web theater, replaying the previous completed loop while the browser is already on the next loop, so that the two appear synchronized because they are the same repeatable sequence?

## Short Answer

Yes.

This is feasible, and for repeatable motion it is more realistic than trying to force the current polling/render path into true real-time parity.

However:

- it is not a full replacement for a current-view lane
- it is best for deterministic/repeatable loops
- unique interactive manipulation still needs a current or near-current consult path

## Why It Fits This Repo

The current codebase already has most of the raw ingredients:

- canonical browser snapshot build in `static/main.js`
- browser-published `sharedState.text_theater = { snapshot, theater, embodiment }`
- clip/timeline/motion preset lanes
- loop metadata (`loop_mode`, `preview_loop`, active clip state)
- turntable state and camera pose snapshots
- motion history in `scripts/text_theater.py`
- time-strip capture lane for sequence-oriented work

Important existing seams:

- turntable state in snapshot/workbench
- camera pose snapshots in `_env3DCameraPoseSnapshot()`
- authored clip/timeline/preset control in workbench lanes
- settle preview/commit already generate explicit micro-timelines

## What Delayed Loop Mode Actually Is

It is not "live current parity."

It is:

1. record one full canonical loop from the browser truth surface
2. when the next loop begins, the text theater replays the prior loop
3. browser is on loop `n`, text theater is on loop `n-1`
4. because the loop content is identical, the pair looks aligned enough for orientation and review

That gives the agent a stable indirect view without asking the live terminal path to keep up with every motion frame in real time.

## Where It Works Best

### 1. Turntable

Best fit.

The current turntable is deterministic camera motion around a stable target. That is exactly the kind of loop where delayed replay is cheap and honest.

### 2. Authored clips with repeat loop mode

Good fit.

If a clip is compiled and played with repeatable timing, a prior-loop replay is viable.

### 3. Motion presets rendered as timeline loops

Good fit.

The workbench already compiles presets into timeline state and can scrub/apply poses deterministically.

### 4. Settle preview / corrective micro-timelines

Good fit after generation stabilizes.

Since these are transient but explicit generated timelines, they can be recorded once and replayed for review.

## Where It Does Not Fully Work

### 1. Unique manual manipulation

Not enough by itself.

During one-off posing, dragging, placement, or emergent interactions, there may be no repeatable loop to piggyback on. The agent still needs a current or near-current observation mode there.

### 2. Dynamic physics with non-repeatable divergence

Unsafe unless determinism is guaranteed.

If the next loop is not actually identical, then replaying `n-1` beside `n` becomes misleading.

### 3. Proc-gen during construction

Not enough on its own.

Generation often creates unique states. Delayed replay is useful for review after stabilization, not as the only observation lane during creation.

## Recommended Model: Dual Observation Lanes

The system should split into two explicit lanes:

### Lane A — Current Consult

Use for:

- unique edits
- pose authoring
- placement
- assert/diagnostic checks
- command-attached before/after

This can be slower, because it is correctness-first.

### Lane B — Delayed Loop Mirror

Use for:

- turntable
- repeated authored clips
- repeated motion presets
- timeline loop review
- repeated camera presets/orbits

This is the cheap smooth orientation lane.

## Three Implementation Options

## Option 1 — Record and Replay Pre-rendered Text Frames

### Shape

For each repeatable loop, record a ring buffer of:

- `snapshot_timestamp`
- loop-relative time
- camera pose
- browser-published `theater`
- browser-published `embodiment`

On the next loop, replay those exact strings to the terminal.

### Strengths

- easiest to make visually smooth
- no Python re-render during replay
- no ambiguity about what the text theater looked like during the recorded loop

### Weaknesses

- larger buffer footprint
- less flexible if you later want alternate text render modes from the same recorded loop

### Verdict

Strong near-term path.

## Option 2 — Record Canonical Snapshot Frames, Render During Replay

### Shape

Record canonical snapshots (or primitive deltas) for each frame, then let the text renderer generate the replay output.

### Strengths

- preserves one-truth-many-renderers architecture
- supports alternate replay views later

### Weaknesses

- reintroduces render cost during replay
- likely still too expensive if you try to render every replay frame in Python

### Verdict

Better long-term architecture, weaker short-term performance.

## Option 3 — Record Loop Keyframes + Deterministic Seek

### Shape

For repeatable loops, record:

- loop duration
- start timestamp
- playback rate
- camera curve / azimuth progression
- clip id or timeline id

Then reconstruct the replay from those deterministic controls instead of full frame capture.

### Strengths

- smallest payload
- elegant for turntable and authored clips

### Weaknesses

- only safe when determinism is real
- harder for mixed dynamic states

### Verdict

Best specialized solution for turntable and stable clip loops.

## Recommended Hybrid

### For turntable

Use Option 3.

Record only camera progression and loop period. Turntable is deterministic enough that replay can be driven from the recorded camera path.

### For repeated clips and presets

Use Option 1 first, then evolve toward Option 3.

Record pre-rendered text frames for the prior loop. Once stable, add deterministic seek/replay for authored clips.

### For unique operations

Keep the current consult lane.

## Required Additions in This Repo

### Browser (`static/main.js`)

Add a loop recorder owned by browser truth:

- detect loop start/end
- maintain loop sequence id
- record prior-loop frame buffer
- expose:
  - `loop_id`
  - `loop_phase`
  - `loop_duration`
  - `loop_replay_available`
  - `loop_frame_index`

### Server (`server.py`)

Expose a dedicated delayed-loop observation payload:

- `text_theater_loop`
- `mode: delayed_loop`
- `loop_id`
- `source_loop_id`
- `loop_phase`
- `replay_frame`
- `snapshot` or `delta`

### Terminal (`scripts/text_theater.py`)

Add a live mode selector:

- `consult_current`
- `delayed_loop`
- `sequence_review`

For delayed loop mode, the terminal should consume replay frames, not re-query heavy consult surfaces.

### Help/docs

Document clearly that delayed loop mode is:

- valid for repeatable sequences
- not authoritative for unique current edits

## Standards/Research That Support This

- `requestAnimationFrame()` timestamps are synchronized across same-origin windows/iframes and align to `document.timeline.currentTime`, which supports stable loop-relative timing and synchronized replay scheduling.
- Web Animations provides explicit current-time/playback-rate control, which supports deterministic replay and seek-based review.
- FastAPI already supports WebSockets, and the HTML standard defines EventSource/SSE; either can carry pushed replay frames instead of polling.
- JSON Merge Patch is a viable future transport for frame deltas if replay moves from whole frames to patches.

## Bottom Line

Delayed loop mode is feasible and strategically strong.

It should not replace the current consult lane, but it can absolutely become the primary smooth orientation lane for:

- turntable
- repeat clips
- motion preset loops
- settle micro-timeline review

If the goal is "smooth paired orientation while the browser keeps moving," delayed loop replay is one of the best options currently available for this codebase.
