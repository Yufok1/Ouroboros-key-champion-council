# Reactive Coin Stream Trajectory

Date: 2026-04-18

## Purpose

Define the corrected centerline for the current meme-coin lane:

- not `social club`
- not `generic creator board`
- not `random dev stream`

The active product thesis is:

- a reactive stream that behaves like the coin's live nervous system
- a market-facing theater driven by external truth
- a reusable production shell that Champion Council can generalize later

This brief is source-grounded against:

- the current `champion_councl` runtime
- recent Pump-oriented utility / treasury / burn exploration
- the old stream repo at `F:\End-Game\glassboxgames\twitch-stream` as reference/audit evidence only

## Corrected Framing

The stream is not a sidecar.

It is the first serious public surface for this lane.

The correct shape is:

- external market / social events arrive
- Champion Council reduces them into typed state
- the stream renders those states as visible action
- overlay, avatar, diagnostics, and commentary all read from that state

So the stream becomes:

- observability
- dramatization
- diagnostics
- identity

and not merely:

- promotion
- looping spectacle
- static storefront

## Source-Verified Reference Substrate

The repo at `F:\End-Game\glassboxgames\twitch-stream` is not dead throwaway code.
But it is being used here as reference evidence only.

The point is not to import or revive that codebase.
The point is to learn from what already worked there:

- delivery shell patterns
- state-reactive rendering patterns
- controller/overlay transport patterns
- diagnostics/provenance discipline

### 1. Production entry and orchestration are real

Verified in:

- `run_stream.py`
- `core/orchestrator.py`

What exists:

- a real production entrypoint
- a central orchestrator/state machine
- component injection
- async startup
- routing between stream, overlay, chat, and control surfaces

The current arcade semantics are specific, but the shell is reusable.

### 2. Overlay + controller + low-latency video shell are real

Verified in:

- `overlay/server.py`
- `extension/overlay.js`
- `extension/video_overlay.html`

What exists:

- HTTP + WebSocket overlay server
- browser controller surface
- WebRTC ICE endpoint
- HLS stream serving
- OBS/browser-source friendly delivery
- session start / end signaling
- per-viewer registration and state messaging

This is a major donor asset.

### 3. State-reactive visual layer is real

Verified in:

- `specter/bridge.py`
- `specter/renderer.py`
- `overlay/renderer.py`

What exists:

- real-time state bridge
- history buffer / replay
- held/frozen state handling
- HTML5 canvas visualization
- overlay rendering patterns for live state panels

The current theme is game-decision probability, but the architecture generalizes well to:

- buy pressure
- sell pressure
- holder delta
- comment bursts
- treasury / burn pulses

### 4. Commentary / ghost layer is real

Verified in:

- `specter/ghost.py`
- `specter/chat_manager.py`
- `run_stream.py`

What exists:

- an observer/commentary layer
- multi-platform chat plumbing
- stream-side message injection patterns

This suggests a clean later path for:

- market commentator
- treasury narrator
- event callouts

without making commentary the primary truth source.

### 5. Diagnostics and provenance are real

Verified in:

- `PROJECT_ANALYSIS_REPORT.md`
- `diagnose_fps.py`
- `diagnose_freeze.py`
- `specter/provenance.py`

What exists:

- freeze and FPS diagnostics
- provenance-style event logging
- operational analysis already performed on the donor repo

This lowers the risk of repurposing it.

## What Is Reusable

The reusable families are conceptual and architectural, not a mandate for code transplant.

What is reusable here means:

- patterns
- interfaces
- operating shapes
- proven divisions of responsibility

### Delivery shell

- controller route
- overlay route
- WebSocket state fanout
- WebRTC/HLS dual video path
- OBS/browser-source compatibility

### State-reactive visual shell

- small state reducer -> live visual transition
- canvas/overlay rendering patterns
- avatar / facecam side surface
- ghost / specter sidecar

### Operational shell

- orchestrator
- diagnostics
- event broadcast
- session / viewer registration patterns

## What Must Be Discarded Or Demoted

Do not import the donor repo wholesale.

Discard or demote:

- arcade game rotation as center
- viewer-tips-for-control as center
- RL wealth extraction as center
- HOLD semantics as the main public hook
- game-specific menuing and key-routing as the first product slice

Those are old-project-specific payloads, not the corrected thesis.

## Corrected Champion Role

Champion Council should not become `arcade-stream but for coins`.

The corrected role is:

- Champion Council facilitates
- external market surfaces provide truth
- cascade-lattice observes and attests
- the stream renders state

So the split is:

- `Pump / chain / public surfaces` = event source
- `Champion Council` = reducer + controller + renderer + operator panel
- `cascade-lattice` = receipts / tape / hold / diagnostics

## First-Class State Families

The stream should reduce external events into a small set of readable states.

Initial families:

- market tempo
- buy / sell imbalance
- holder velocity
- comment / attention velocity
- treasury charge
- burn pulse
- cooldown / exhaustion

These become the visible poles for:

- avatar motion
- overlay color / text
- camera behavior
- commentary cadence

## First Product Shape

The first serious public surface should be:

- `Technolit Reactor`

Meaning:

- one live stream
- one reduced market-state model
- one visible avatar / facility
- one operator overlay

Possible visible states:

- idle drift
- accumulation
- breakout
- instability
- sell shock
- treasury charge
- burn event

## Execution Order

### Step 1. Harvest the proven patterns, not the old codebase

Keep as reference:

- overlay / controller / transport patterns
- specter-style state rendering
- diagnostics and provenance hooks

Do not pull the old repo in as a dependency and do not make its business logic the new center.

### Step 2. Define the coin-state reducer

Turn raw event inputs into bounded typed state.

No raw market spam directly into the renderer.

### Step 3. Define the stream-facing facility

One facility:

- avatar
- environment
- overlay
- commentary lane

all reading from the same reduced state.

### Step 4. Bind the operator side

Champion panel should expose:

- current market state
- last notable events
- treasury / burn status when available
- scene mode / commentary controls

### Step 5. Add treasury / burn pulses after the visual shell is truthful

Do not lead with financial theatrics before the event pipeline and reducer are solid.

## Known Donor Weak Spots

From donor source/docs:

- hardcoded Windows path in `run_stream.py`
- YouTube integration incomplete
- placeholder empty directories
- arcade-specific assumptions baked into some control flows

These do not invalidate the donor shell.
They simply mean extraction should be selective.

## Opus Audit Targets

Opus should pressure-test:

1. whether the donor shell really extracts cleanly from the arcade payload
2. whether the current Champion public-facing text is still stale around older social/club framing
3. whether the first state families are small enough to stay readable
4. whether commentary and diagnostics are correctly subordinate to reduced truth
5. whether treasury / burn rendering is being introduced too early

## Bottom Line

This is a better centerline than the recent social / club framing.

The strongest current thesis is:

- reactive market stream first
- public coin theater first
- reusable delivery shell first

Then later:

- treasury / burn operator surfaces
- utility actions
- broader production-factory generalization
