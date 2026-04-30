# eDreamer FCS Operationalization Report

Date: 2026-04-28
Workspace: `D:\End-Game\champion_councl`
Branch observed: `checkpoint-2026-04-20-full-snapshot`

## Purpose

Create an honest operator-facing FCS layer for Dreamer without overstating current learning capability. The change turns the existing Dreamer mechanics/proposal/episode-step surfaces into a named preflight and single-step control surface.

## Executive Status

Source wiring is complete. Runtime reload is still required.

Confirmed:
- Dreamer already had mechanics observation, bounded proposal ranking, reward scoring, bounded sweep, and episode step routes.
- New FCS routes now exist in source:
  - `GET /api/dreamer/fcs/status`
  - `POST /api/dreamer/fcs/step`
- The Dreamer tab now has an `eDREAMER FCS` panel with preflight gates and a manual FCS step button.
- Public exposure hardening already blocks `/api/dreamer` as a private route prefix, so the new FCS endpoints do not expand the public surface.

Not yet live:
- The running local server on `127.0.0.1:7866` is stale.
- `GET /api/dreamer/state` responds, but `GET /api/dreamer/fcs/status` returned `404`.
- A server restart is required before the new routes are available in the browser/runtime.

## Evidence

Source locations:
- `server.py:14099` defines `_DREAMER_FCS_SCHEMA_ID = "edreamer_fcs_v1"`.
- `server.py:15920` defines `_dreamer_fcs_status_payload(...)`.
- `server.py:16761` adds `fcs` into `/api/dreamer/state`.
- `server.py:16787` defines `dreamer_fcs_status`.
- `server.py:16803` defines `dreamer_fcs_step`.
- `static/panel.html:11914` adds the `eDREAMER FCS` panel.
- `static/panel.html:13136` defines `renderDreamerFcs(...)`.
- `static/panel.html:13390` defines `dreamerFcsStep()`.

Verification commands run:
- `python -m py_compile server.py cocoon_adapter.py`
- `node --check static/main.js`
- `git diff --check -- server.py static\panel.html`
- `python -c "import server; print(server._DREAMER_FCS_SCHEMA_ID); print('/api/dreamer/fcs/status')"`
- `python -c "import server; p=server._dreamer_fcs_status_payload(...); print(p['phase'], p['can_step'], p['training_truth'])"`

Verification result:
- Python compile passed.
- JavaScript syntax check passed for `static/main.js`.
- Diff whitespace check passed, with only a Git LF/CRLF warning for `static/panel.html`.
- Direct Python import confirmed the schema id and route string.
- Direct helper test returned `manual_step_ready True trained_but_mechanics_starved` for a simulated active Dreamer with empty observation buffer.

## Current Runtime Truth

Live `/api/dreamer/state` on `127.0.0.1:7866` reported:

- `dreamer.active`: `true`
- `dreamer.has_real_rssm`: `true`
- `dreamer.training_cycles`: `0`
- `dreamer.obs_buffer_size`: `0`
- `dreamer.reward_buffer_size`: `2`
- `dreamer.reward_count`: `2`
- `rssm.action_dim`: `8`
- `rssm.total_latent`: `5120`

Interpretation:
- Dreamer runtime is present and real.
- It is not currently demonstrating closed-loop training.
- The observation buffer is empty, so mechanics-grounded training is still starved.
- FCS can be a bounded manual proposer/scorer/stepper once restarted, but it should not be represented as autonomous mastery yet.

## What Changed

Server:
- Added FCS status model with explicit gates:
  - control mode
  - mechanics observation
  - bounded proposal
  - capsule runtime
  - real RSSM
  - capsule observation buffer
  - reward feed
- Added training truth classification:
  - `closed_loop_training_ready`
  - `capsule_training_feed_present`
  - `trained_but_mechanics_starved`
  - `trained`
  - `no_training_cycles_reported`
- Added `/api/dreamer/fcs/status` for read-only preflight.
- Added `/api/dreamer/fcs/step` for a guarded single step through the existing `/api/dreamer/episode_step` path.

Panel:
- Added an `eDREAMER FCS` panel.
- Shows phase, mode, task, can-step status, training truth, cycles, observation count, and reward count.
- Shows each preflight gate as OK/WARN/BLOCK.
- Adds `FCS STEP`, which calls `/api/dreamer/fcs/step`.

## Risk Notes

- The change does not start autonomous loops.
- The FCS step endpoint delegates to the existing bounded episode step.
- The preflight gate allows manual stepping when mechanics and ranked proposals exist, even if capsule training is starved. That is intentional: manual stepping is useful for evaluation, but the UI separately reports closed-loop training is not ready.
- If future work adds a repeating FCS controller, document it as a `Kleene-star run` / `Kleene st★r run`: repeatable and watchable, but only with an explicit stop rule, visible state, and checkpoint boundary.
- The running server must be restarted before browser validation.
- Worktree contains unrelated dirty files: `run_local.ps1`, `static/main.js`, `static/sw.js`, plus edited `server.py` and `static/panel.html`. Do not commit/push without isolating intended files and reviewing unrelated changes.

## Recommended Next Review Steps

1. Restart the local Champion Council server.
2. Hit `GET http://127.0.0.1:7866/api/dreamer/fcs/status`.
3. Open `http://127.0.0.1:7866/panel`, Dreamer tab, and verify the `eDREAMER FCS` panel renders.
4. If `can_step=true`, press `FCS STEP` once and verify:
   - a bounded action is selected,
   - `workbench_set_pose_batch` runs,
   - reward breakdown is recorded,
   - `history.episode_steps` increments.
5. If `obs_buffer_size` remains `0`, treat Dreamer as a scorer/controller harness, not as a mechanics-grounded training loop.

## Reviewer Question

Should the next patch wire mechanics observations into the capsule observation buffer continuously, or should it keep the safer manual FCS step loop and only add an explicit operator-controlled "feed observation" action?
