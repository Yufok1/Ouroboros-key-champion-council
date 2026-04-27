# Multi-Theater Facility TODO 2026-04-14

Repo: `F:\End-Game\champion_councl`

Purpose:

- pin the smallest honest path to `4 theaters` without widening into a new authority system
- distinguish `more windows` from `more roles`
- keep second-capsule orchestration separate from immediate UI convenience work
- capture deferred edits without touching `champion_gen8.py` yet

## 1. Bottom Line

Four theaters is already close with minimal change if the goal is:

- one current capsule
- one adjacent capsule
- one web theater per capsule
- one text theater per capsule

That does **not** require a new renderer family.
It does **not** require a new truth plane.
It does **not** require direct `champion_gen8.py` edits as the first move.

But one correction matters:

- a second runtime on different ports is only clean immediately if it lives in an isolated repo copy or otherwise isolated capsule path
- two servers started from the same repo root still share several capsule-side dotfiles and server-side capture files

So the smallest honest path is operational:

1. run a second isolated runtime on a different port set and data dir
2. open its web theater in a second browser window/tab
3. run a second text-theater process pointed at that second web port

The current system already supports:

- web theater on FastAPI `WEB_PORT`
- text theater as a separate process against a chosen `--host/--port`
- separate capsule runtimes if ports, persistence dirs, and capsule-local files do not collide

## 2. Why Four Theaters Might Be Worth It

Four theaters only makes sense if each one has a distinct role.

Good reasons:

- primary world view vs adjacent world/controller view
- action surface vs query-work surface
- current live world vs branch / comparative world
- operator-facing command surface vs subordinate policy surface
- corroboration across two capsules without collapsing them into one giant tab
- development lane where one capsule stays stable and one runs experimental procedures

Bad reasons:

- opening more windows just to feel like more is happening
- duplicating the same surface four times
- pretending many views automatically equal better control

## 3. The Strongest Four-Theater Layout

### Capsule A

- `web theater`
  - authoritative live actuation world you are actually steering
- `text theater`
  - consult/query-work or render view for the same live frame

### Capsule B

- `web theater`
  - adjacent branch, worker habitat, or alternate control/inspection world
- `text theater`
  - its query-work, audit, or glyph/render surface

This is the cleanest first step because it gives:

- one web + one text pair per capsule
- easy comparison
- low conceptual ambiguity

## 4. Why Not Jump Straight To Six

Six windows is only useful if there are three clear role pairs.

Possible valid triplets:

- `actuation`
- `query-work`
- `audit / snapshot / glyph-render`

But six becomes noise fast if the extra pair has no unique job.

Default recommendation:

- start with 4
- prove distinct roles
- only then consider 6

## 5. What The Codebase Already Allows

### Text theater can already run in many modes

`scripts/text_theater.py` already exposes:

- `--view render`
- `--view consult`
- `--view split`
- `--view theater`
- `--view embodiment`
- `--view snapshot`

So multiple text windows do not require text-theater runtime changes.

### Web theater already has an adjacent-theater framing

The browser UI already renders an `Adjacent Theater` utility.
That means the concept is already native to the repo language even if multi-window operation is not fully productized.

### Current limitation

The convenience launcher scripts are single-instance shaped:

- `open_text_theater.ps1`
- `run_text_theater.ps1`

They both pin one shared state file:

- `data/text_theater_window.json`

So the text-theater substrate is multi-instance capable, but the launcher convenience is not.

### Current web limitation

The web theater persists session/mode state in `localStorage`.
That means multiple browser tabs/windows of the same capsule can fight each other on theater/session state.

There is also a deeper limit:

- one server currently keeps one live-sync cache
- `/api/text-theater/live` reads from that one cache

So one capsule does not yet support two honest independent web+text pairs, even if browser storage is isolated.

So:

- second capsule on separate ports is clean now only when capsule-local files are also isolated
- many windows against one capsule need live-sync namespacing and session scoping later

## 6. Smallest Honest Immediate Path

No runtime edits required if the second runtime is isolated from the first at the filesystem level:

1. keep current capsule on current ports
2. start a second local runtime from an isolated repo copy or isolated capsule path, with different:
   - `WEB_PORT`
   - `MCP_PORT`
   - `PERSISTENCE_DATA_DIR`
3. open both web theaters
4. run one text theater against each port

This yields `4 theaters` immediately in the honest sense.

## 7. Why This Is Actually Useful

The strongest real use is not spectacle.
It is role separation.

Examples:

- Capsule A acts on the main world while Capsule B studies, stages, or branches
- Capsule A remains operator-near while Capsule B is a subordinate controller
- one text theater becomes query-work and the other becomes render/glyph/audit
- one capsule can stay stable while another explores an aggressive configuration

This is especially useful if the user wants:

- one trusted lane
- one experimental lane
- one place to act
- one place to think

## 8. Deferred Edit List

These are worthwhile later, but not first.

### `launcher`

- add instance labels / ids to `open_text_theater.ps1` and `run_text_theater.ps1`
- write state files per instance, not globally
- add optional default `--view` at launch

### `web session scoping`

- stop multi-window collisions by moving theater/session state from global `localStorage` to:
  - per-window `sessionStorage`
  - URL params
  - or namespaced instance keys

### `live-sync namespacing`

- carry a theater/window instance id through browser live-sync
- let the server keep more than one live cache per runtime
- let text theater choose which live stream to read

Without this, one capsule cannot provide two stable web+text pairs.

### `capsule runtime isolation`

- parameterize `CAPSULE_PATH` in `server.py`
- isolate capsule-local files now written next to `champion_gen8.py`
- consider optional capture-dir namespacing for server-side image captures

### `multi-capsule convenience`

- add a small orchestrator script:
  - launch capsule A
  - launch capsule B
  - open both web theaters
  - open both text theaters with chosen views

### `adjacent controller bridge`

- define whether second capsule is:
  - just another observed runtime
  - a remote slot endpoint
  - or a tool-using subordinate runtime with explicit bridge semantics

Do not blur these into one thing.

### `Champion web_search`

- current local `web_search` probe failed on default `searxng` because localhost provider was unavailable
- treat this as separate infrastructure work
- do not tie it to the four-theater lane

## 9. Correct Order

1. prove the value of `4 theaters` with separate ports and no runtime edits
2. if useful, add multi-instance text launcher support
3. if useful, fix per-window web theater session collisions
4. only then decide whether second-capsule orchestration should be:
   - visual only
   - remote-slot only
   - or full subordinate-runtime control

## 10. Short Version

The cheapest honest path to four theaters is:

- two capsules
- two web theaters
- two text theaters

Run them on separate ports, separate persistence dirs, and separate capsule-local file footprints.

That gives a real role-separated facility now.

The first follow-up edits should be:

- live-sync namespacing for multi-window same-runtime operation
- multi-instance text-theater launcher support
- per-window web session scoping

Not `champion_gen8.py` surgery.
