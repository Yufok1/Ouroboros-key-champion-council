# Codex Trajectory Report 2026-04-12

Repo: `F:\End-Game\champion_councl` branch `main`
Baseline: `3636db1 Checkpoint Dreamer v1 substrate and server bridge groundwork`
Prepared by: Opus (advisory/auditor; no source edits)

Purpose: hand Codex a one-page landed-vs-stub inventory and the three minimal next actions, so he can resume on the main arterial without re-deriving state.

Related docs:

- [DREAMER_UNIFICATION_ROADMAP_2026-04-12.md](DREAMER_UNIFICATION_ROADMAP_2026-04-12.md)
- [DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md](DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md)
- [DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md](DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md)
- [RUNTIME_VS_SOURCE_MISMATCH_NOTE_2026-04-12.md](RUNTIME_VS_SOURCE_MISMATCH_NOTE_2026-04-12.md)

## Checkpoint State

- `3636db1` committed: +7533 / −1213 across 15 files (8 code + 7 docs)
- Stage 1a blocker cleared
- Worktree clean except leftover untracked: `capture_probe` (0-byte stray), three `static/assets/packs/kenney-*/Textures/` dirs (~32K each)
- No uncommitted drift since checkpoint — including Codex's TRAINING HEALTH + DREAMER FIELD DOCUMENT panel work, which is inside the committed `static/panel.html` at lines 11367, 11509, 12287, 12291, 12462, 12727

## Live Capsule State (probed 2026-04-12)

- `generation=8`, `fitness=0.606`, `quine_hash=e104451f4938bd95dc7c36f25156037b`
- `dreamer.active=true`, `has_real_rssm=true`
- `dreamer.training_cycles=220` (was 196 at 04-11)
- `dreamer.reward_count=7065` (was 6302; +763 since 04-11 — still all generic)
- **`dreamer.obs_buffer_size=0`** — unchanged, still starving
- `slots_filled=0/32`
- `causation_hold_active=true`

## Stage 2 Seam Audit (Landed vs Stub)

All four Stage 2 seams from DREAMER_UNIFICATION_ROADMAP are physically present in `server.py`:

| Seam | Symbol / Route | Line | Status |
|---|---|---|---|
| 2a mechanics obs packer | `_dreamer_mechanics_observation_payload` | 10627 | LANDED |
| 2a obs endpoint | `GET /api/dreamer/mechanics_obs` | 11247–11261 | LANDED |
| 2b correction table | `_DREAMER_KNEEL_CORRECTIONS` (8 actions) | 10404–10517 | LANDED |
| 2b task-scoped lookup | `_dreamer_correction_table_for_task` | 10801 | LANDED |
| Proposal ranker | `_dreamer_rank_proposals` | ~10904 | LANDED (heuristic — see GAP below) |
| Action selector | `_dreamer_select_ranked_action` | 11050 | LANDED |
| 2c reward scorer | `_dreamer_reward_breakdown` | 10819 | LANDED |
| 2d episode step | `POST /api/dreamer/episode_step` | 11320–11456 | LANDED end-to-end |
| 2d episode reset | `POST /api/dreamer/episode_reset` | 11297 | LANDED |
| History store | `_dreamer_history.mechanics_rewards` + `episode_steps` | 10272, 11434–11435 | LANDED |
| env_help entries | — | 4002–5124 | LANDED |
| Dreamer tab: TRAINING HEALTH | `renderDreamerTrainingHealth`, `dr-loss-strip` | panel.html 11367, 12462 | LANDED |
| Dreamer tab: FIELD DOCUMENT | `renderDreamerFieldDocument`, `dr-field-doc` | panel.html 11509, 12727 | LANDED (shape redirect pending — see FIELD DOCUMENT section below) |

Episode step handler is complete and end-to-end: reads mechanics obs, ranks, selects, dispatches `workbench_set_pose_batch` via `_dreamer_dispatch_env_control`, re-reads obs, computes reward breakdown, writes history rows, broadcasts activity.

## The Gap — why `obs_buffer_size` is still 0

Only one `observe()` call exists in `server.py` (line 1223), and it mirrors generic activity as `signal_type='agent_debug'`. There is **no** `observe(signal_type='mechanics_v1')` call anywhere, and **no** `observe(signal_type='mechanics_reward')` call anywhere.

### Consequences

1. **Capsule obs bus is not fed.** The server-side loop runs, corrections apply, rewards score — but the capsule's `_obs_buffer` never receives mechanics observations, so `dreamer.obs_buffer_size` stays 0 regardless of how many episode steps run.
2. **Capsule reward bus is not fed.** Mechanics rewards live in `_dreamer_history` only; they never flow into the capsule's `_reward_buffer`. The critic keeps training on generic tool/workflow rewards (current rate: ~34/min, all generic).
3. **The "proposer" is currently the server, not Dreamer.** The ranker is `outer_control_plane_heuristic_v1` (see `_dreamer_rank_proposals`). It gates action candidates with simple rules on hips world-y, gap, risk, load_share, etc. It does **not** call the capsule's `imagine()`. So the current loop is a Dreamer-shaped shadow loop with the real Dreamer bypassed.

This matches the roadmap's Stage 2d note exactly — the loop is "proof-of-concept" with the episode real but the capsule still outside it.

## Three Minimal Additions to Close the Gap (no capsule edits)

All three are localized to `dreamer_episode_step` in `server.py` and reuse the existing `_call_tool("observe", ...)` pattern already in use at line 1223.

### Addition 1: Feed mechanics observations into capsule (pre-step)

After `before_payload` is obtained (~line 11331), before ranking:

```python
try:
    await _call_tool("observe", {
        "signal_type": "mechanics_v1",
        "data": json.dumps({
            "schema_id": _DREAMER_MECHANICS_SCHEMA_ID,
            "task": str(ranked_payload.get("task") or _dreamer_control_plane_task(effective)) if False else body.get("task", "half_kneel_l"),
            "payload": before_payload,
            "ts": time.time(),
        }, ensure_ascii=False),
    })
except Exception:
    pass
```

(Note: `ranked_payload` isn't computed yet at this point, so the task tag should come from `body` or a local compute. Keep it defensive.)

**Expected effect:** first episode step after this lands pushes `dreamer.obs_buffer_size` off 0.

### Addition 2: Feed mechanics rewards into capsule (post-step)

After `reward_row` is built (~line 11421), before `_dreamer_history_append`:

```python
try:
    await _call_tool("observe", {
        "signal_type": "mechanics_reward",
        "data": json.dumps(reward_row, ensure_ascii=False),
    })
except Exception:
    pass
```

**Expected effect:** capsule `reward_count` starts accumulating mechanics-tagged rewards alongside generic ones. The critic is now exposed to real body-physics signals.

### Addition 3 (optional, makes Dreamer the real proposer)

Before the heuristic ranker call, consult capsule `imagine()` for its preferred action. If it returns an intelligible action index in `[0, 7]`, use it as `action_key` via the correction table; otherwise fall back to the existing heuristic ranker.

This is ~20 lines, depends on what `imagine()` actually returns shape-wise, and is the one seam where "Dreamer is the proposer" becomes literally true rather than metaphorically true. Can be deferred until Additions 1+2 are verified moving the obs buffer.

### Addition 4 (NOT for this pass — flagged to prevent scope creep)

Do **not** touch `champion_gen8.py`. Stage 3 capsule edits are archived reference only per the active execution rule. Additions 1–3 are all server-side and use existing MCP tools as-is.

## FIELD DOCUMENT Shape Redirect (user-stated, 2026-04-12)

The DREAMER FIELD DOCUMENT as currently rendered is generic diagnostic prose across the WORLD MODEL / GROUNDING / PROPOSER / REWARD SCORER / BODY CHAIN lanes. **The user wants a different shape**: the FIELD DOCUMENT should be a **focused cutout of the existing text theater**, not a parallel diagnostic surface.

### What the user wants

- The FIELD DOCUMENT renders an **actual braille/glyph slice** from `scripts/text_theater.py` + `static/main.js`, cropped to the bone or region Dreamer is currently reasoning about
- If the proposer is previewing `counter_rotate_spine -3°`, the panel shows the braille-rendered spine cutout in its current orientation — and, when imagination rollouts exist, the projected after-state
- Arm angling up-left = the braille form of an arm, up-left. Glyphs, not a sentence describing glyphs
- The WORLD MODEL / GROUNDING / PROPOSER / REWARD SCORER / BODY CHAIN lanes can remain as a **one-line header strip** above the braille cutout — context tags, not paragraphs

### Why this shape

- Reuses the braille/glyph pipeline you already built instead of forking a parallel surface
- The panel improves automatically every time text theater improves
- Matches the theater-first doctrine — the text theater is truth, the Dreamer panel is a scoped view of it

### Implementation note (non-prescriptive)

The redirect depends on whether `text_theater.py` already supports per-region cutout rendering. If yes, wire `renderDreamerFieldDocument` in `static/panel.html:12727` to request a region-scoped braille snapshot from the existing theater endpoint and paste it into `dr-field-doc`. If no, that cutout capability is the prerequisite and is the shared interface with the text theater HD work the user has separately researched.

**Do not speculate on the HD research direction.** The user has explicit research drawn up and will brief you directly. Stay inside the braille-cutout redirect scope for the FIELD DOCUMENT.

## Finish-Line Definition for Dreamer v1

Five items, all verifiable via MCP probes:

1. `dreamer.obs_buffer_size > 0` with `mechanics_v1`-tagged observations (Addition 1 lands this)
2. Mechanics rewards separately tracked in capsule — `observe(signal_type='mechanics_reward')` calls visible (Addition 2 lands this)
3. 8-action correction vocabulary wired `_DREAMER_KNEEL_CORRECTIONS` → `workbench_set_pose_batch` (already landed)
4. `/api/dreamer/episode_step` callable end-to-end (already landed; will be richer after Additions 1+2)
5. **One successful `half_kneel_l` episode:** starts from the current residual-brace failing state (`lower_leg_l` lifting, `stability_risk=1`, only `foot_r` supporting), converges to `route_realized` with `stability_risk < 0.72` within 50 steps, via legible proposals citing real evidence and truth-gates

When #5 lands, Dreamer v1 is done and Dreamer recedes into background as a scorer/proposer that Pan consults.

## Known Residual State

- The 9-bone kneel macro is live in runtime, verified matching source
- Body is in bad residual braced-support state: `lower_leg_l` lifting, `stability_risk=1`, only `foot_r` supporting
- The episode loop has never been run against this state, so this is the obvious first target for the `half_kneel_l` evaluation problem
- `env_help` and `env_report` both teach the theater-first sequence; registry rewrites are in place

## Out Of Scope For This Pass

- `champion_gen8.py` — capsule remains frozen (active execution rule)
- Text theater HD enhancement direction — user has separate research
- Pan implementation — depends on Dreamer v1 proving proposal quality first
- Tinkerbell, Coquina integration, multi-topology generalization — all deferred
- `capture_probe` + `kenney-*/Textures/` — user's decision, not a blocker

## Suggested Codex Sequence

1. Read this report + `DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md`
2. Implement Additions 1 + 2 in `dreamer_episode_step` (server.py ~11320)
3. Restart server, probe `get_status` baseline
4. Call `POST /api/dreamer/episode_step` once with no body
5. Re-probe `get_status` — confirm `dreamer.obs_buffer_size > 0` and `reward_count` grew with mechanics-tagged entries
6. Read text theater to see whether the applied correction moved the body
7. If yes, run 5–10 more episode steps; if convergence toward `route_realized` is visible, Dreamer v1 finish line is in reach
8. If no, diagnose via the blackboard rows — the ranker heuristic may need tuning, or the correction table deltas may be too small/large for this residual state
9. Separately, or in parallel: redirect `renderDreamerFieldDocument` in `static/panel.html:12727` to render a text-theater braille cutout instead of generic prose

Every step is server-side or frontend-side. No capsule edits. No scope creep.
