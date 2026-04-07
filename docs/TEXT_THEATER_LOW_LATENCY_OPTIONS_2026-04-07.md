# Text Theater Low-Latency Options 2026-04-07

## Problem Statement

The current browser/text-theater parity path is truthful enough for command-attached observation, but still too slow for live camera-motion parity.

User-visible symptoms:

- text theater trails the browser theater during turntable/manual camera motion
- motion presents as a slideshow rather than concurrent movement
- long freeze periods can occur while the browser view keeps rotating

## Measured Local Facts

Measured against the live local runtime on 2026-04-07:

- `env_read('shared_state')`
  - avg: ~812 ms
  - avg payload size: ~114 KB
- `env_read('text_theater_snapshot')`
  - avg: ~674 ms
  - avg payload size: ~46.7 KB
- `env_read('text_theater')`
  - avg: ~704 ms
  - avg payload size: ~402 B
- `env_read('text_theater_embodiment')`
  - avg: ~775 ms
  - avg payload size: ~1.3 KB
- `env_read('text_theater_view')`
  - avg: ~1194 ms

Key inference:

- the dominant cost is not payload size alone
- the dominant cost is repeated render / transform work in the live read path
- any architecture requiring a fresh HTTP round-trip plus text-theater render for every motion frame will remain visibly laggy

## Confirmed Architectural Seams

### 1. Polling is too expensive

The terminal viewer still depends on high-frequency `env_read(...)` polling.

Even after slimming some paths, the measured live reads are still in the 0.6s-1.2s range, which is fundamentally too slow for turntable/manual camera parity.

### 2. Server-side render is too expensive for motion

`server.py` still uses the text-theater Python renderer on live read surfaces:

- `text_theater_snapshot`
- `text_theater`
- `text_theater_embodiment`
- `text_theater_view`

This is acceptable for consult/on-demand verification, but not for continuous camera motion.

### 3. Browser-side text bundle generation is still part of motion cost

`static/main.js` publishes:

- `sharedState.text_theater.snapshot`
- `sharedState.text_theater.theater`
- `sharedState.text_theater.embodiment`

That is the correct truth surface, but recomputing or cloning it during camera motion still has real cost.

### 4. Timer-only fixes are insufficient

The queue starvation bug in the live-mirror timer was real and needed fixing, but the measured read/render cost is still high enough that timer tuning alone cannot get to current-view parity.

## Ranked Solution Options

## Option A — Push the browser text bundle directly over a streaming channel

### Shape

- browser remains the canonical producer of:
  - snapshot
  - theater text
  - embodiment text
- server exposes a dedicated live stream endpoint for text theater
  - SSE or WebSocket
- terminal viewer subscribes once and renders pushed updates
- polling is removed from the hot path

### Why it fits this codebase

- FastAPI already supports `StreamingResponse`
- FastAPI already supports WebSockets
- the server already has SSE infrastructure for MCP-facing flows

### Strengths

- biggest likely latency reduction
- eliminates repeated HTTP request setup and response parsing per frame
- avoids “freeze until next poll succeeds”
- preserves canonical browser truth

### Risks

- requires a new live stream contract
- must handle reconnect / backpressure cleanly

### Recommendation

This is the strongest medium-term fix.

## Option B — Split the system into a live lane and a consult lane

### Live lane

- browser-published `text_theater.theater`
- browser-published `text_theater.embodiment`
- camera pose / sync freshness
- optimized for motion parity

### Consult lane

- Python-rendered `text_theater_view`
- full compact/full observation
- expensive diagnostics, compare, verification
- on-demand only

### Strengths

- aligns with actual usage
- avoids spending consult-grade cost during turntable motion
- preserves rich diagnostics where they matter

### Risks

- requires explicit mode separation in server/tooling
- operators must understand “live” vs “consult”

### Recommendation

Do this even if Option A is chosen. The live lane should not be blocked by the consult renderer.

## Option C — Delta protocol for camera and scene changes

### Shape

- publish a base canonical snapshot
- during camera motion, send only camera deltas and freshness
- during scene/object changes, send partial JSON updates
- terminal/server applies patches to a cached snapshot

### Supporting standards

- JSON Patch (`RFC 6902`)
- JSON Merge Patch (`RFC 7396`)

### Strengths

- scales to future proc-gen / scene complexity
- avoids shipping full snapshots for small changes
- pairs well with streaming

### Risks

- more complex correctness surface
- patch application bugs can cause drift if not carefully verified

### Recommendation

Best long-term transport model, but should follow the live streaming lane, not precede it.

## Option D — Browser worker/off-main-thread text generation

### Shape

- move text-theater string generation or projection work into a Worker
- keep browser UI motion smooth while text bundle updates in parallel

### Supporting standard

- WHATWG Workers

### Strengths

- reduces main-thread jank
- keeps authoritative generation near the browser truth

### Risks

- scene/mesh access is not worker-friendly
- likely requires refactoring text-theater generation into worker-safe data preparation + worker rendering

### Recommendation

Useful later if browser-side bundle generation remains expensive after the streaming split.

## Option E — Keep polling and keep optimizing timers

### Recommendation

Do not keep betting on this path.

Measured live read cost is already too high. More timer tuning cannot turn 0.6s-1.2s request/render costs into concurrent motion parity.

## Recommended Trajectory

1. Stop using the expensive consult renderer for live motion.
2. Establish a dedicated live text-theater stream from the browser truth surface.
3. Keep the Python consult renderer for:
   - command-attached observation
   - before/after compare
   - assert/diagnostic views
4. Introduce a delta protocol after the live stream is stable.
5. Only then consider worker-based off-main-thread generation if browser-side text generation still costs too much.

## Concrete Next Build

### Phase 1

- add a dedicated low-latency `text_theater_live` stream endpoint in `server.py`
- stream:
  - `snapshot_timestamp`
  - `last_sync_reason`
  - `freshness`
  - `theater`
  - `embodiment`
  - minimal camera metadata
- update `scripts/text_theater.py` to subscribe instead of poll for live mode

### Phase 2

- keep `env_read('text_theater_view')` as consult/on-demand only
- keep command-attached observation for tool results

### Phase 3

- add delta transport for camera-only and small scene mutations

## Bottom Line

The problem is no longer “find the right timer.”

The problem is that the current live path is still architecturally polling and rendering too much work per update. The correct fix is to separate low-latency live observation from heavy consult rendering, and move live observation to a pushed stream.
