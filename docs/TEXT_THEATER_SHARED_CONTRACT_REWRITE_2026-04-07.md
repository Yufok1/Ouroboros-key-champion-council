# Text Theater Shared Contract Rewrite 2026-04-07

Repo: `F:\End-Game\champion_councl`

## Decision

The correct long-term design is:

- one authoritative browser/runtime scene contract
- one web renderer that draws directly from live scene objects
- one text renderer that consumes the same authoritative contract

Not:

- browser scene -> derived text snapshot -> server re-render -> terminal redraw as the hot path for live motion

That current shape is acceptable for consult/diagnostic views, but it is the wrong architecture for dynamic parity.

## What The Web Theater Renders From

The web theater renders directly from the live Three.js/runtime scene:

- animation loop in `static/main.js`
- camera controls / turntable state in `static/main.js`
- direct `renderer.render(scene, camera)` in `static/main.js`

This means the browser is already operating on the fastest and most truthful surface available: live meshes, transforms, materials, camera state, and mounted runtime state.

## What The Text Theater Renders From Today

The text lane is one or more layers removed:

1. browser mutates live scene/runtime objects
2. browser mirror queue publishes live sync payloads
3. browser builds `sharedState`
4. browser builds `text_theater_snapshot`
5. browser pre-renders `text_theater.theater` and `text_theater.embodiment`
6. server reads from the mirrored cache
7. server may still re-run Python text-theater rendering
8. terminal process polls and redraws

So the system already shares truth, but the sharing boundary is too late and too expensive.

## Measured Consequence

Live local measurements on 2026-04-07:

- `env_read('shared_state')`: ~1937 ms average, ~117 KB
- `env_read('text_theater_snapshot')`: ~1076 ms average, ~48 KB
- `env_read('text_theater')`: ~1816 ms average
- `env_read('text_theater_embodiment')`: ~765 ms average
- `env_read('text_theater_view')`: ~754 ms average, ~69 KB

Important inference:

- payload size is not the only issue
- repeated serialization, cloning, readback, and terminal redraw work is still too expensive for live motion parity

## Was The Original Design Wrong?

Partly.

It was reasonable for:

- diagnostic readouts
- command-attached observation
- settle/assert verification
- low-bandwidth consult views

It is not the correct final architecture for:

- smooth live motion parity
- future proc-gen scenes and body shells
- generalized unknown content
- maintaining two faithful surfaces without constant bespoke support

## What Should Be Kept

Do not throw away the whole text-theater lane.

The following pieces are still good and reusable:

- the browser-side text snapshot builder doctrine
- the current embodied/support/contact diagnostics
- command-attached observation
- the consult/compare/assert renderer role
- the motion history / timeline / settle review logic

These should survive as layers over the new contract.

## What Should Be Collapsed

The expensive duplicated reconstruction path should be collapsed:

- stop treating the terminal consult renderer as the live motion path
- stop requiring the server to rebuild text views from heavyweight `shared_state` reads during motion
- stop adding feature-specific text logic where canonical primitives can carry the truth

## New Shared Boundary

The browser should produce a first-class scene/observation contract before rendering surfaces diverge.

That contract should include:

- camera/view state
- scene objects
- transforms
- bounds
- appearance/color
- focus and neighborhood
- embodiment bones
- scaffold pieces
- contact/support/load data
- timeline/loop/phase data
- assertion/diagnostic state
- generic render primitives

The key point is that the text renderer should consume this contract directly, not reconstruct it secondhand from mixed caches.

## Primitive-First Extension

To survive proc-gen growth, the shared contract must be primitive-first, not feature-first.

Minimum useful primitive vocabulary:

- point
- segment / polyline
- polygon / patch
- box
- ellipsoid / sphere
- capsule / limb
- oriented volume
- marker / label
- bounds proxy

Minimum truth classes:

- bone
- scaffold
- skin_proxy
- support
- contact
- scene_object
- debug
- selection

## Recommended Runtime Split

### 1. Live Motion Lane

Purpose:

- current dynamic orientation
- camera motion
- turntable
- repeated loops

Rules:

- browser is canonical producer
- no heavyweight Python consult rendering on the hot path
- stream or direct cache consumption instead of repeated expensive polling

### 2. Consult / Assert Lane

Purpose:

- exact current inspection
- command-attached snapshots
- compare
- settle/assert
- anomaly review

Rules:

- correctness-first
- can be slower than live lane
- may still use richer Python formatting where useful

### 3. Delayed Loop Lane

Purpose:

- smooth operator viewing for deterministic repeated loops

Rules:

- never replaces current truth
- acceptable only for repeatable motion
- useful as a display optimization, not as the main decision surface

## Migration Risk Assessment

This is not a trivial one-file refactor, but it is also not a “throw everything away and start over” situation.

Risk level:

- moderate

Why it is manageable:

- the browser already produces most of the truthful data we need
- the command sync lane already exists
- the current text lane already distinguishes live vs consult use cases in practice
- the expensive parts are layered, not deeply entangled with every workbench feature

Main risk:

- mixing live and consult responsibilities in one server/terminal path has created accidental duplication

That risk is architectural, not conceptual.

## Practical Rewrite Order

1. Freeze the doctrine: one authoritative contract, two renderers.
2. Define the shared contract explicitly in browser/runtime terms.
3. Split live text motion from consult/assert rendering.
4. Stop using heavyweight server-side re-rendering for live motion.
5. Extend the shared contract with generic primitives for future proc-gen coverage.
6. Keep command-attached observation and compare/assert on top of the same contract.

## Bottom Line

The text-theater system does not need to be discarded.

It does need its truth boundary moved earlier in the pipeline.

If we do that, the redesign is a rewire plus lane split, not a total reinvention of every text-theater depiction feature.
