# Four Theater Feasibility Report 2026-04-14

Repo: `F:\End-Game\champion_councl`

Purpose:

- determine the smallest honest route to `4 theaters`
- separate `more views` from `more runtimes`
- pin which shared surfaces currently collapse multi-view ambitions
- connect this facility back to the active weather/text/web trajectory

## 1. Bottom Line

`4 theaters` is worth doing.

But there are two different target shapes:

1. one runtime with multiple independent views
2. two runtimes with one primary world and one adjacent controller/branch world

The repo supports the second shape more honestly today than the first.

Why:

- one browser runtime already knows how to package `shared_state.text_theater`
- one text theater already knows how to consume `/api/text-theater/live`
- but one server currently maintains one live cache and therefore one effective live text-theater stream

So if the goal is:

- `primary world + adjacent runtime`

then a second capsule/runtime is the clean move.

If the goal is only:

- `two different views onto one runtime`

then a second capsule is not conceptually required, but the current runtime still does not support that honestly without namespacing work.

## 2. Verified Surfaces

### Runtime launch

`run_local.ps1` already exposes:

- `WEB_PORT`
- `MCP_PORT`
- `PERSISTENCE_DATA_DIR`

That makes separate local runtimes operationally straightforward.

### Text theater transport

`scripts/text_theater.py` already supports:

- `--host`
- `--port`
- `--view render|consult|split|theater|embodiment|snapshot`

So text theater is already a separate consumer process, not a browser-only panel.

### Browser-side text-theater carrier

`static/main.js` already builds:

- `sharedState.text_theater.snapshot`
- `sharedState.text_theater.theater`
- `sharedState.text_theater.embodiment`

This is the existing carried bundle for web/text parity work.

### Adjacent-theater language already exists

The browser UI already renders an `Adjacent Theater` utility.

That matters because the multi-theater idea is already native to repo language, not an alien abstraction.

## 3. What Blocks One-Runtime Four-Theater Operation

### 3.1 One server currently exposes one live stream

`server.py` keeps one `_env_live_cache`.

`/api/live-sync` updates that one cache.

`/api/text-theater/live` reads from that one cache.

Operational consequence:

- two web windows against one runtime do not yield two stable paired text-theater feeds
- they collapse into one latest live stream

This is the load-bearing reason one runtime does not yet honestly provide `web A + text A + web B + text B`.

### 3.2 Same-origin browser state is global

`static/main.js` stores theater session/view state in global `localStorage` keys such as:

- `env_theater_session_v1`
- `env_theater_view_modes`

Operational consequence:

- two windows on the same origin can fight over theater/session state

Separate ports naturally isolate this because browser storage is origin-scoped.

### 3.3 Text-theater launcher convenience is singleton-shaped

`open_text_theater.ps1` and `run_text_theater.ps1` both use:

- `data/text_theater_window.json`

Operational consequence:

- the runtime substrate can support multiple text-theater windows
- the convenience launcher currently cannot manage them cleanly

### 3.4 No-code same-runtime browser workarounds are incomplete

Different browser profiles or private windows can isolate browser storage, but they do not solve the single live-cache problem.

So they are not the honest answer if the goal is two stable web+text pairs.

## 4. What Blocks Same-Root Second-Capsule Operation

Starting two servers from the same repo root is not fully isolated yet.

### 4.1 Fixed capsule path in `server.py`

`server.py` currently uses:

- `CAPSULE_PATH = Path("capsule/champion_gen8.py")`

That means both servers launched from the same root point at the same capsule file unless code is changed.

### 4.2 Capsule-local dotfiles are written beside `champion_gen8.py`

`capsule/champion_gen8.py` writes several runtime files next to itself, including:

- `.relay_center.cmd`
- `.mcp_server.log`
- `.bag_state.json`
- `.capsule_state.json`
- `.slot_manifest.json`
- `.signal_intake.json`
- `tui.log`

Operational consequence:

- two servers sharing one capsule directory can step on each other even if ports differ

### 4.3 Server-side capture history is also repo-local

`server.py` writes capture artifacts under:

- `static/captures`
- `static/captures/_index.json`

This is less critical than the capsule dotfiles, but it is another shared surface when two servers run from one repo root.

## 5. Three Honest Paths

### Path A: Immediate facility, no runtime edits

Use a second isolated repo copy or checkout.

Then run:

- runtime A on one `WEB_PORT` / `MCP_PORT` / `PERSISTENCE_DATA_DIR`
- runtime B on another `WEB_PORT` / `MCP_PORT` / `PERSISTENCE_DATA_DIR`

Then open:

- web A
- text A
- web B
- text B

This is the cheapest honest way to stand up `4 theaters` right now.

Why it wins:

- no `champion_gen8.py` edits
- no live-sync redesign
- no capsule-dotfile collisions
- true role separation immediately

### Path B: Smallest productization path inside one repo

If the goal is to make this normal inside one repo checkout, the smallest real edit set is:

1. `server.py`
   - allow `CAPSULE_PATH` override
   - optionally allow capture-dir override
2. `static/main.js`
   - carry a theater/window instance id in live-sync
   - stop using one global theater session key for all windows on one origin
3. `server.py`
   - namespace live caches by instance id
   - allow `/api/text-theater/live` to select an instance
4. `scripts/text_theater.py`
   - accept the selected instance id
5. `open_text_theater.ps1` / `run_text_theater.ps1`
   - use per-instance state files

This is still relatively small, but it is no longer a no-code launch trick.

### Path C: One runtime, many views

If the real target is just:

- environment authoring in one web view
- inhabitant/workbench authoring in another web view
- paired text surfaces for both

then a second capsule is not architecturally required.

But current code still needs:

- live-sync namespacing
- per-window session scoping

Without those, one-runtime four-theater operation is not trustworthy.

## 6. Why Four Theaters Is Actually Valuable

The value is role separation, not spectacle.

Good reasons:

- one runtime stays operator-near and trusted
- one runtime stages experimental or subordinate behavior
- one web view can stay spatial/actuation-heavy
- one text view can stay query-work/audit-heavy
- world authoring and inhabitant authoring stop fighting for one cockpit
- weather/text/web parity work can be compared without collapsing all observation into one surface

This is especially strong if the user wants:

- one place to act
- one place to think
- one place to compare
- one place to stage or delegate

## 7. Why Six Should Wait

`6 theaters` only makes sense once there is a third stable role pair.

Possible future triplet:

- actuation
- query-work
- audit/render/snapshot

Until that third role pair is explicit, `6` is more likely to become noise than leverage.

## 8. Relation To The Weather Lane

This facility is adjacent infrastructure.

It should not replace the active weather/text/web order.

Once the facility question is settled, the weather lane remains:

1. finish the equilibrium/band-selector substrate
2. keep text/web as peer consumers over shared truth
3. then carry the glyph/text consumer into the web theater over existing `shared_state.text_theater`

The four-theater facility helps that work by separating:

- live actuation
- query-work
- adjacent staging
- comparative observation

It does not change the underlying weather doctrine.

## 9. Deferred Runtime Edit List

These are the right deferred edits if the facility is greenlit.

### Multi-window live-sync

- namespace server live cache by instance id
- allow text theater to request one named live stream

### Web session scoping

- move theater/session state away from one global same-origin key
- use `sessionStorage`, URL keys, or explicit namespacing

### Capsule runtime isolation

- parameterize `CAPSULE_PATH`
- isolate capsule-local runtime files per launched runtime

### Text-theater launcher instances

- replace one global `text_theater_window.json` with per-instance files
- optionally support default `--view` per launched instance

### Capture isolation

- optionally namespace capture history/output per runtime

### Champion web search

- current local probe of Champion `web_search` failed because the default local `searxng` provider was unreachable
- keep that on a separate Champion/runtime maintenance list
- do not tie it to the four-theater lane

## 10. Recommendation

If the user wants `4 theaters` quickly and honestly:

- use a second isolated repo/runtime now

If the user wants `4 theaters` as a normal one-repo facility:

- do the small productization path

If the user mainly wants dual authoring views on one runtime:

- do not reach for a second capsule first
- build live-sync namespacing and per-window session scoping instead
