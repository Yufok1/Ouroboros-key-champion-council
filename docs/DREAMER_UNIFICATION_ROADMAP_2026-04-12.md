# Dreamer Unification Roadmap 2026-04-12

Repo: `F:\End-Game\champion_councl`

Purpose:

- define the staged implementation path for Dreamer operationalization
- keep the stages ordered by blast radius: shell/runtime first, server bridge second, capsule last
- pin the exact conditions under which capsule edits are justified
- list the smallest high-leverage seams to implement first

## Active Execution Rule

For the active Champion Council track, capsule edits are off-limits. Treat any capsule-oriented material below as archived reference only, not executable work. The live roadmap now stops at shell/runtime/help first, then server/theater association.

Related docs:

- [DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md](DREAMER_V1_OPERATIONALIZATION_PLAN_2026-04-12.md) — v1 contract, observation/action/reward spec
- [DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md](DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md) — 12-system responsibility map
- [RUNTIME_VS_SOURCE_MISMATCH_NOTE_2026-04-12.md](RUNTIME_VS_SOURCE_MISMATCH_NOTE_2026-04-12.md) — known mismatches
- [ENV_REPORT_SCHEMA_2026-04-11.md](ENV_REPORT_SCHEMA_2026-04-11.md) — env_report contract

## Bottom Line

Dreamer operationalization is now a two-layer active program with one archived reference layer. The executable path is shell/runtime/help first, then server/theater association. Capsule analysis remains useful for orientation, but it is not part of the active implementation program.

```
Layer 3: CAPSULE — archived reference only, not in scope
Layer 2: SERVER  — bridge endpoints, episode loop, UI        (SECOND, moderate cost)
Layer 1: SHELL   — runtime truth, checkpoint, help, docs     (FIRST, lowest cost)
```

## Stage 1: Shell / Runtime / Docs (No capsule touch)

**Goal:** Make the truthful substrate stable and discoverable before wiring anything to Dreamer.

### 1a. Checkpoint the worktree (CRITICAL PREREQUISITE)

The worktree has ~2500 lines of uncommitted changes across server.py, main.js, text_theater.py, help registries, and docs. This includes the 9-bone kneel seed, env_report recipe, theater-first gate wiring, and blackboard builder.

**Action:** `git add` + `git commit` the current worktree.

**Why first:** Every subsequent stage builds on this code. If it's lost, all Dreamer wiring is pointless.

### 1b. Verify runtime loads current source

After checkpoint and server restart:
- Confirm `text_theater_snapshot` shows the 9-bone kneel seed (hips/spine/chest), not the old 6-rotation macro
- Confirm `env_report(report_id='route_stability_diagnosis')` returns a well-formed report
- Confirm `env_help(topic='env_report')` returns the help entry

**Action:** Restart server, refresh browser, run verification probes via MCP.

### 1c. Update env_help to teach env_report as preferred diagnostic path

The theater-first gate's `required_sequence` already lists env_report, but the help playbooks still teach `shared_state` as the routine verification step.

**Action:** Edit `static/data/help/environment_command_registry.json` and/or `server.py` env_help entries to teach:
1. text_theater_embodiment first
2. text_theater_snapshot second
3. env_report third
4. shared_state last resort

### 1d. Align the Dreamer tab header with reality

The Dreamer tab in `panel.html:11166` currently says "DREAMER WORLD MODEL" with no grounding information. Before any new panels, add a one-line status strip at the top:

```
Mode: PASSIVE | Task: none | Obs source: generic | Reward source: generic
```

This is one `<div>` with 4 `<span>` elements. Costs nothing. Immediately tells the operator whether Dreamer is grounded or just running on generic tool telemetry.

**Action:** Add status strip to `panel.html` Dreamer tab header. Wire it to `_dreamerState` fields that already exist in `/api/dreamer/state`.

**Estimated scope:** ~15 lines HTML + ~10 lines JS.

### Stage 1 deliverables:
- Checkpointed worktree
- Runtime confirmed matching source
- env_help teaching env_report
- Dreamer tab shows grounding status

---

## Stage 2: Server-Side Bridge (No capsule touch)

**Goal:** Build the server-side infrastructure that can pack mechanics observations, score them, and expose episode-step controls — all without modifying the capsule.

### 2a. Mechanics observation packer endpoint

Create `POST /api/dreamer/mechanics_obs` (or similar) in server.py that:
1. Reads `shared_state.workbench.route_report`, `motion_diagnostics.contacts`, `motion_diagnostics.balance`, `active_controller` from the live cache
2. Packs them into a compact JSON observation object with named fields
3. Returns the observation for inspection

This endpoint does NOT feed Dreamer. It is a read-side observation materializer — the same pattern as env_report, just structured for Dreamer's consumption rather than operator diagnosis.

**Why server-side:** The server has direct access to the live cache. The capsule only sees shared_state through MCP tool calls. Building the packer server-side means the observation is always fresh, always from the live truth, and does not require capsule modification.

**Schema (from v1 plan):**
```json
{
  "route": {
    "realized_count": int,
    "missing_count": int,
    "phase_index": int,
    "stability_risk": float,
    "stability_margin": float,
    "operational_state": str,
    "stage_blocked": bool
  },
  "contacts": {
    "lower_leg_l": { "gap": float, "manifold_points": int, "load_share": float, "supporting": bool, "state": str },
    "foot_r": { "gap": float, "manifold_points": int, "load_share": float, "supporting": bool, "state": str }
  },
  "balance": {
    "balance_mode": str,
    "nearest_edge_distance": float
  },
  "pose": {
    "hips_offset_y": float,
    "hips_pitch": float,
    "spine_pitch": float,
    "chest_pitch": float,
    "lower_leg_l_pitch": float,
    "foot_r_yaw": float
  },
  "timestamp": float,
  "obs_source": "mechanics_v1"
}
```

**Estimated scope:** ~80 lines in server.py, following the existing env_report pattern.

### 2b. Correction table constant

Add a server-side constant mapping 8 action integers to named corrections with `workbench_set_pose_batch` payloads:

```python
_DREAMER_CORRECTION_TABLE = [
    {"action": 0, "name": "drop_hips",             "bone": "hips",        "field": "offset_y",     "delta": -0.03},
    {"action": 1, "name": "raise_hips",            "bone": "hips",        "field": "offset_y",     "delta": +0.02},
    {"action": 2, "name": "shift_hips_fore",       "bone": "hips",        "field": "offset_z",     "delta": +0.02},
    {"action": 3, "name": "shift_hips_aft",        "bone": "hips",        "field": "offset_z",     "delta": -0.02},
    {"action": 4, "name": "counter_rotate_spine",  "bone": "spine",       "field": "pitch_deg",    "delta": -3.0},
    {"action": 5, "name": "counter_rotate_chest",  "bone": "chest",       "field": "pitch_deg",    "delta": -3.0},
    {"action": 6, "name": "tuck_lead_knee",        "bone": "lower_leg_l", "field": "pitch_deg",    "delta": +5.0},
    {"action": 7, "name": "widen_anchor_foot",     "bone": "foot_r",      "field": "yaw_deg",      "delta": +3.0},
]
```

This lives in server.py. It is pure data — no behavior. Dreamer, the UI, and the episode endpoint all read from this single table.

**Estimated scope:** ~15 lines constant + ~30 lines helper to convert a correction into a `workbench_set_pose_batch` payload.

### 2c. Mechanics reward scorer

Add a server-side function that takes two mechanics observations (before and after a correction) and computes a reward scalar + decomposition:

```python
def _dreamer_mechanics_reward(obs_before, obs_after):
    # positive: gap decrease, support realization, manifold gain, stability improvement, phase advance
    # negative: penetration, stage blocked, brace collapse, regression
    # returns: { "total": float, "decomposition": {...} }
```

This uses the exact reward table from the v1 plan. It does NOT touch the capsule's `_reward_buffer`. It is a server-side scoring function that the episode endpoint will use.

**Estimated scope:** ~60 lines.

### 2d. Episode step endpoint

Create `POST /api/dreamer/episode_step` that:
1. Reads current mechanics observation (reusing 2a)
2. Sends the observation to the capsule via `observe(data=packed_obs, signal_type='mechanics_v1')` — this is the existing MCP tool, no capsule change needed
3. Asks the capsule for Dreamer's preferred action via `imagine()` — ranking the 8 branches by critic value (existing behavior)
4. Maps the chosen action to a correction via the correction table (2b)
5. Applies the correction via `env_mutate` / `workbench_set_pose_batch`
6. Reads the resulting mechanics observation
7. Computes the reward (2c)
8. Sends the reward via `observe(data=reward_event, signal_type='mechanics_reward')` for CASCADE provenance
9. Returns: `{ obs_before, action, correction_name, obs_after, reward, terminal_state }`

**Critical design point:** This endpoint orchestrates the episode from the server side, using the capsule's existing MCP tools as-is. No capsule modification required. The capsule sees `observe()` calls with `signal_type='mechanics_v1'` and `signal_type='mechanics_reward'` — it just logs them to `_observations`. This gives us a working episode loop before touching the capsule.

**Limitation:** At this stage, Dreamer's `_obs_buffer` is still fed by generic brain inference (embedding slices), not by the mechanics observations. The imagine() call still uses the generic world model. So the action selection is not yet mechanics-grounded — it's imagination over the generic latent space. But the episode loop is real, the corrections are applied, and the rewards are computed against real truth. This is the proof-of-concept stage.

**Estimated scope:** ~100 lines in server.py.

### 2e. Dreamer tab Episode panel

Once 2d exists, add the Episode panel to the Dreamer tab:
- Task selector (half_kneel_l only for v1)
- Mode selector (passive / advisory — active/autonomous deferred)
- Step button, Reset button, Stop button
- Per-step timeline: observation summary, chosen action name, correction applied, reward, terminal state

**Estimated scope:** ~120 lines HTML + ~80 lines JS.

### 2f. Dreamer tab Grounding panel

Add the Grounding panel:
- Current observation schema: mechanics_v1 or generic
- Fields being fed (list)
- Current task
- Current episode step count
- Reward source: generic / mechanics_v1 / mixed
- Obs buffer depth (already shown in buffer bar, but now with source split)

**Estimated scope:** ~40 lines HTML + ~30 lines JS.

### Stage 2 deliverables:
- Server-side mechanics observation packer
- 8-action correction table
- Mechanics reward scorer
- Episode step endpoint
- Dreamer tab Episode + Grounding panels
- A working episode loop that applies real corrections, scores against real truth, logs to CASCADE — all without touching the capsule
- Dreamer associated to environment-native surfaces: env_help, theater HUD, blackboard, text theater, env_report, workflow/facility wrappers

---

## Stage 3: Capsule Bridge (Capsule touch — justified)

This section is retained for historical orientation only. It is not part of the active plan and should not be scheduled.

**Goal:** Wire the capsule's Dreamer internals to use mechanics observations for world-model training and action-conditioned prediction, so that imagination rollouts become mechanics-grounded.

This stage is ONLY justified after Stage 2 proves:
- The episode loop works end-to-end
- The corrections are meaningful (some improve, some degrade)
- The reward function discriminates well
- The observation schema is stable

### 3a. Mechanics observation adapter in _obs_buffer

Modify `_full_brain_inference` (or add a new path alongside it) so that when a `mechanics_v1` observation arrives via `observe()`, it is:
1. Packed into a fixed-length numeric vector (matching the RSSM's input dimension)
2. Paired with the action integer (0-7) that produced it
3. Pushed to `_obs_buffer` as `(obs_t_packed, action_int, obs_t1_packed)`

This is the seam that makes `obs_buffer_size > 0` with real mechanics data.

**Capsule edit scope:** ~40 lines in `champion_gen8.py`.

### 3b. Action-conditioned world model loss

Fix the world model training step at `champion_gen8.py:7721-7728` to actually consume `action_t`:

Currently:
```python
dreamer_input = emb_t @ self._embed_to_dreamer
result = self.dreamer_world_model.forward({'obs': dreamer_input})
```

Should become:
```python
dreamer_input = emb_t @ self._embed_to_dreamer
action_onehot = np.zeros(self.action_dim, dtype=np.float32)
action_onehot[int(action_t)] = 1.0
conditioned_input = np.concatenate([dreamer_input, action_onehot])
result = self.dreamer_world_model.forward({'obs': conditioned_input})
```

This teaches the world model that different actions produce different next states.

**Capsule edit scope:** ~10 lines in `champion_gen8.py`, but requires matching changes in the RSSM input dimension. May require adjusting `_embed_to_dreamer` projection matrix dimensions.

### 3c. Mechanics reward into _reward_buffer

Route mechanics reward events (from Stage 2's `observe(signal_type='mechanics_reward')`) into Dreamer's `_reward_buffer` alongside the existing generic rewards, so the critic and reward_head learn from mechanics truth.

**Capsule edit scope:** ~20 lines in `champion_gen8.py` — add a handler in `observe()` that, when `signal_type='mechanics_reward'`, also calls `_capture_reward` with the mechanics reward value.

### 3d. Grounded imagination

After 3a-3c, imagination rollouts will use the mechanics-trained world model. The 8 branches now correspond to the 8 named corrections. The critic values reflect mechanics rewards. The "best action" output from `imagine()` now means "the correction most likely to improve the kneel."

This is not an edit — it's an emergent property of 3a-3c being done correctly.

### Stage 3 deliverables:
- Mechanics observations flowing into _obs_buffer
- Action-conditioned world model training
- Mechanics rewards in _reward_buffer
- Grounded imagination: action branches correspond to named corrections

---

## Capsule Intervention Protocol

Editing `champion_gen8.py` is expensive because:
- The file is a quine capsule with merkle-linked integrity
- Edits upset the nested quine systems
- Recompilation requires careful procedure
- Incorrect edits can cascade into provenance/integrity failures

### Conditions Under Which Capsule Edits Are Justified

A capsule edit is justified if and only if ALL of these are true:

1. **The seam cannot be achieved server-side.** If the server can orchestrate the same outcome using existing MCP tools (`observe`, `feed`, `imagine`, `forward`, `infer`), prefer the server-side path.

2. **The server-side proof-of-concept works.** Stage 2 must demonstrate a working episode loop with real corrections and real rewards before the capsule is opened.

3. **The edit is small and contained.** The change should be ≤50 lines and touch only one functional area (obs ingestion, reward routing, or world model conditioning). No sweeping refactors.

4. **The edit has a clear test.** After the edit, one MCP probe can verify the change landed: e.g., `get_status()` shows `obs_buffer_size > 0`, or `show_rssm()` shows `action_conditioned: true`.

5. **The edit is documented first.** Before touching the capsule, the exact change is written as a spec (what lines change, what the before/after looks like, what the test is). The spec is reviewed. Then the edit is made.

### Capsule Edits NOT Justified

- "Let's refactor the RSSM to support variable action dims" — too broad, unnecessary for 8-action v1
- "Let's add a new MCP tool for mechanics episodes" — can be done server-side
- "Let's change how _full_brain_inference pushes to _obs_buffer" — too risky without Stage 2 validation
- "Let's rebuild the reward system" — the existing system works, just needs a new signal source
- "Let's add Dreamer modes (passive/advisory/active)" — this is server/UI logic, not capsule logic

### The Three Justified Capsule Seams

Only these three edits are justified, and only after Stage 2 proves the loop works:

| Seam | What | Where | Scope |
|---|---|---|---|
| 3a | Mechanics obs → _obs_buffer | `_full_brain_inference` or `observe` handler | ~40 lines |
| 3b | Action-conditioned world model loss | `_train_step` phase 1 | ~10 lines + dim adjustment |
| 3c | Mechanics reward → _reward_buffer | `observe` or new `_capture_mechanics_reward` | ~20 lines |

Total capsule edit: ~70 lines across 2-3 functions. That's the ceiling for v1.

---

## Smallest High-Leverage Seams (Implementation Order)

These are ordered by leverage-to-effort ratio. Each one is independently testable.

### Seam 1: Mechanics Observation Packer (SERVER, Stage 2a)

**Leverage:** Defines the observation contract that everything else builds on. Without a stable observation, there's nothing to feed, score, or display.

**Effort:** ~80 lines in server.py, no capsule touch, pure read-side.

**Test:** `GET /api/dreamer/mechanics_obs` returns a well-formed JSON observation with real route/contact/balance/pose data from the live cache.

### Seam 2: Correction Table (SERVER, Stage 2b)

**Leverage:** Gives meaning to action integers 0-7. Without this, Dreamer's imagination branches are just "action 0, action 1..." — meaningless to operators.

**Effort:** ~45 lines in server.py, pure data constant + helper.

**Test:** Calling the helper with action=0 produces a valid `workbench_set_pose_batch` payload that drops hips by 0.03.

### Seam 3: Dreamer Tab Status Strip (SHELL, Stage 1d)

**Leverage:** Immediately makes the Dreamer tab honest about grounding state. Tiny cost, high clarity.

**Effort:** ~25 lines total in panel.html + main.js.

**Test:** Open Dreamer tab, see "Mode: PASSIVE | Task: none | Obs source: generic | Reward source: generic".

### Seam 4: Mechanics Reward Scorer (SERVER, Stage 2c)

**Leverage:** Enables quantitative evaluation of corrections. Without scoring, episodes are just random exploration.

**Effort:** ~60 lines in server.py.

**Test:** Feed it two observations where gap decreased; verify positive reward. Feed it two where balance collapsed; verify large negative reward.

### Seam 5: Episode Step Endpoint (SERVER, Stage 2d)

**Leverage:** The payoff — a callable loop that applies real corrections against real truth. This is where Dreamer becomes interactive.

**Effort:** ~100 lines in server.py, depends on seams 1-4.

**Test:** Call `/api/dreamer/episode_step`. Verify: observation returned, correction applied, reward computed, state changed in the runtime.

### Seam 6: Mechanics Obs → _obs_buffer (CAPSULE, Stage 3a)

**Leverage:** Makes `obs_buffer_size > 0` with real mechanics data. The world model starts learning body physics instead of token embeddings.

**Effort:** ~40 lines in champion_gen8.py. First capsule touch.

**Test:** After several episode steps, `get_status()` shows `obs_buffer_size > 0`. `show_rssm()` shows mechanics observations in the buffer.

### Seam 7: Action-Conditioned Loss (CAPSULE, Stage 3b)

**Leverage:** Teaches the world model that action 0 (drop hips) and action 6 (tuck knee) produce different state transitions. Without this, imagination rollouts all predict the same next state regardless of action.

**Effort:** ~10 lines + dim adjustment in champion_gen8.py.

**Test:** After training on mechanics episodes, imagination branches show divergent trajectories for different actions.

### Seam 8: Mechanics Reward → _reward_buffer (CAPSULE, Stage 3c)

**Leverage:** Critic and reward_head learn "gap decrease is good, brace collapse is bad" from real mechanics signals.

**Effort:** ~20 lines in champion_gen8.py.

**Test:** `show_rssm()` shows recent rewards with `type='mechanics_reward'` and values correlated with kneel improvement.

---

## What This Roadmap Does NOT Cover

- **Pan implementation** — Pan depends on Dreamer producing good proposals. Build Dreamer v1 first.
- **Tinkerbell implementation** — Tinkerbell depends on spatial affordance scanning. Deferred until the contact/support substrate is proven via half_kneel_l.
- **Multi-topology generalization** — half_kneel_r, double_kneel, crouch, sit_rest. Deferred to Dreamer v2.
- **Dreamer RSSM retraining from scratch** — the 196 existing training cycles are on generic data. They will be diluted by mechanics data, not destroyed. Retraining from scratch is not needed for v1.
- **Autonomous mode** — Active and Autonomous Eval modes are deferred until advisory mode proves the proposals are good.
- **Saved-report archive** — env_report recall over past reports. Deferred until 10+ recipes exist.
- **Coquina integration** — procedural body/world generation feeds are a separate track, not part of Dreamer v1.

## Active Sequence Summary

1. Stabilize runtime truth and help surfaces.
2. Build the Dreamer server bridge and control plane.
3. Expose Dreamer through environment-native surfaces: env_help, theater HUD, blackboard/text theater, env_report, workflow/facility wrappers.
4. Treat capsule analysis as frozen reference, not implementation scope.

## Summary

Three layers are documented, but only two are active. Stage 1 stabilizes the truthful substrate. Stage 2 builds the Dreamer control plane, server bridge, theater association, and episode loop using existing capsule MCP tools. Stage 3 is archived reference only. Each active seam is independently testable. The capsule stays stable throughout.
