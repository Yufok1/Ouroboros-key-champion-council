# Weather / Web Overlay Sitrep 2026-04-14

Repo: `F:\End-Game\champion_councl`

Purpose:

- preserve the current live seam across reset/compression
- pin what was actually verified on the fresh 2026-04-14 frame
- keep the next move inside existing weather/text-theater/web-theater surfaces

## 1. Verified Current State

The prompt-ordered live read was completed on a fresh reset frame:

1. `env_read(query='text_theater_embodiment')`
2. `env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)`
3. `env_read(query='text_theater_snapshot')`
4. `env_read(query='contracts')`

The current frame truth:

- `theater.mode = environment`
- `theater.visual_mode = scene`
- `focus = route_test_wall_a`
- `scene.object_count = 14`
- `render.renderer_active = web3d`
- `render.canvas_visible = true`
- `render.css2d_labels_mounted = 13`
- `weather.enabled = true`
- `weather.kind = rain`
- `weather.flow_class = precipitation`
- `weather.density = 0.62`
- `weather.speed = 1.00`
- `weather.turbulence = 0.18`
- `weather.color_hint = #7dd3fc`

Parity is still contaminated on the reset frame:

- `parity.summary = contaminated: builder_subject, focus_fallback`

## 2. What Is Actually Broken

### 2.1 Text-theater scene depiction is under-carrying the live scene

The current main render box in text theater is still too sparse relative to the underlying scene truth.

What is known in snapshot/contracts/web:

- 14 live scene objects
- full object metadata in `scene.objects`
- active web3d canvas
- mounted CSS2D labels

What is happening in text theater:

- the theater sidebar/summary knows the scene and weather are live
- the main scene box still depends too heavily on symbolic sparsity and the bottom object legend

Classification:

- depiction/consumer weakness
- not a truth absence
- not a missing weather contract

### 2.2 The rain lane is real and camera-reactive

The current rain effect is not fake or static.

The field is regenerated from the current snapshot and reprojected through the current camera each frame.

This is why camera movement makes the field feel alive.

### 2.3 “Rain falls up while panning” is a projection/trail seam

The current upward-looking streak effect is explainable in source:

- drop head is the current sampled `point`
- trail head/tail is built from `trail_start = point - flow_hint * trail_length`
- the segment is then reprojected every frame against the moving camera

So the weather truth is still descending, but the screen-space streak can read as rising during pan.

Classification:

- camera-relative depiction seam
- not inverted weather truth

## 3. Web-Theater Text/Glyph Overlay Path

The browser already has the carrier for web-side text-theater expression.

Verified in `static/main.js`:

- `sharedState.text_theater = { snapshot, theater, embodiment }`
- browser mirror remembers that bundle
- web overlay/CSS2D surfaces already exist
- `web_overlay` already exists in the text-theater profile defaults

Operational meaning:

- no parallel renderer is required
- no second truth source is required
- the missing piece is a browser-side consumer of the existing text-theater bundle/snapshot

This means “put the text-based rendering on the web theater” is a direct extension of current architecture.

## 4. Current Root Seams

There are three distinct seams:

1. strengthen text-theater environment/object depiction
2. add a web-theater consumer for the existing text-theater weather/object glyph language
3. later add camera-equilibrium weather controls for near-eye readable bloom / budget / persistence

Do not collapse these into one patch.

## 5. Guardrails

- extend existing weather producer and text-theater/web-theater consumers only
- do not create a second authority plane
- do not make web theater load from text theater as truth; both remain peer consumers of shared truth
- use `shared_state.text_theater` only as the carried render bundle for web-side expression
- keep the required read order alive on every fresh frame:
  1. embodiment
  2. consult/blackboard
  3. snapshot
  4. contracts
- if `contracts` is blocked, treat the gate as the active objective, not as a branch to work around

## 6. Recommended Resume Point

When returning from reset, resume here:

1. re-read this sitrep
2. re-read `docs/CODEX_CHAMPION_COUNCIL_INSTANTIATION_PROMPT_2026-04-13.md`
3. confirm the live frame still shows:
   - under-depicted text-theater environment scene
   - real camera-reactive rain
   - browser-side text-theater bundle carrier
4. then choose deliberately between:
   - text-theater scene depiction strengthening first
   - or web-theater text/glyph overlay consumer first

Current architectural recommendation:

- rain/web overlay consumer is the cleanest next lane
- but the text-theater scene under-depiction remains the clearest visible parity weakness
