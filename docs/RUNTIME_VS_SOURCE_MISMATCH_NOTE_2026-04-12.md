# Runtime vs Source Mismatch Note 2026-04-12

Repo: `F:\End-Game\champion_councl`

Purpose:

- document known mismatches between local worktree source and live runtime state
- prevent reasoning errors caused by assuming source == runtime
- give Codex/Opus a checklist to verify before trusting either side

## Mismatch 1: Half-Kneel Pose Seed — RESOLVED 2026-04-12

**Status:** RESOLVED. Live runtime now shows the 9-bone macro with hips/spine/chest. Verified by Codex via text_theater_snapshot.

**Remaining problem:** The 9-bone macro is live, but the body is still in a bad residual braced-support state. `lower_leg_l` still lifting, `stability_risk = 1`, only `foot_r` supporting. The macro updated but the kneel problem did not disappear. The issue is no longer "wrong macro loaded" — it is "the correction loop has not yet been run against the loaded macro."

## Mismatch 2: env_help / env_report Guidance — PARTIALLY RESOLVED 2026-04-12

**Status:** PARTIALLY RESOLVED. The environment_command_registry.json now repeatedly teaches `env_report(route_stability_diagnosis)` at line 105 and related entries. Verified by Codex.

**Remaining issue:** Discoverability / surface parity, not total absence. The registry teaches env_report, but the overall help surface still doesn't consistently position it as the PREFERRED diagnostic path between theater reads and raw shared_state. Some playbooks may still suggest shared_state reads as a routine verification step.

**Resolution:** Minor cleanup pass needed — ensure env_report is consistently positioned as step 3 (after theater embodiment and snapshot, before raw shared_state) everywhere it appears in help content. Not a blocker.

## Mismatch 3: Capsule Help vs Local env_help Split

**Capsule `get_help('environment')`:** Returns the seeded capsule category view. This is the ouroboros capsule's own help system.

**Local `env_help(topic='...')`:** Returns the environment-specific help from the server's help registry. This is richer, more current, and specific to the environment runtime.

**Capsule `get_help('env_help')`:** Returns no help.
**Capsule `get_help('env_report')`:** Returns no help.

**Impact:** There are two separate help layers with no cross-reference:
- Capsule help (broad, seeded, less current)
- Local env_help (specific, current, environment-focused)

An agent using only capsule `get_help` will miss the entire local env_help system. An agent using only `env_help` will miss broader capsule capabilities.

**Resolution:** This is a known architectural split, not a bug. But it should be documented in both help systems. Capsule help should mention that `env_help` exists for environment-specific topics. env_help should mention that `get_help` exists for broader capsule capabilities. Neither should try to subsume the other.

## Mismatch 4: Dreamer obs_buffer_size = 0

**Capsule status (verified 2026-04-12):**
- `dreamer.active = true`
- `dreamer.has_real_rssm = true`
- `dreamer.training_cycles = 196`
- `dreamer.reward_count = 6302`
- `dreamer.obs_buffer_size = 0`

**Local source and docs:**
Multiple docs describe Dreamer as consuming observations from blackboard, route report, and text theater. The TEXT_THEATER_BLACKBOARD_SPEC explicitly lists "Dreamer observations" as a consumer.

**Impact:** Dreamer is described as a consumer of structured observations, but it is receiving zero observations. It has been trained (196 cycles, 6302 rewards) on something, but not on the current environment observation stream. Any reasoning that assumes Dreamer is "learning from the environment" is currently false.

**Resolution:** This is the entire point of the Dreamer v1 operationalization plan. Phase A wires the observation feed. Until that is done, Dreamer is real but starving.

## Mismatch 5: Dreamer Reward Stream Is Not Mechanics-Grounded

**Capsule status / show_rssm (verified 2026-04-12):**
- Dreamer reward_count is non-zero and rising
- recent rewards are generic events like `tool_success`, `workflow_*`, `hold_*`

**Impact:**
Dreamer is learning from capsule/tool usage success signals, not from kneel/contact/balance outcomes. Any reasoning that assumes the current critic/reward head already understands mechanics quality is false.

**Resolution:**
Dreamer v1 needs a scoped mechanics reward feed for bounded evaluation episodes. At minimum:
- gap decrease
- support realization
- phase advance
- stability improvement
- manifold gain
- penalties for penetration, stage_blocked, and brace collapse

These can coexist with generic rewards, but they should not be mixed blindly during mechanics evaluation.

## Mismatch 6: Dreamer Stores An Action Slot But World-Model Training Ignores It

**Capsule source:**
- The obs buffer stores tuples shaped like `(prev_obs, action, next_obs)`.
- But the phase-1 world-model loss in `_train_step()` predicts `emb_next` from `emb_t` alone and does not use `action_t` when computing the next-state prediction loss.

**Impact:**
Even after observation wiring, Dreamer will not fully learn "which correction caused which mechanics transition" unless the action-conditioning seam is repaired or the first strike is scoped to a simpler proposer/scorer role.

**Resolution:**
Treat this as a known v1 seam:
- first strike: bounded observation + reward + 8-action proposal loop
- later repair: make the world-model update action-conditioned for mechanics episodes

## Mismatch 7: Uncommitted Worktree Drift

**Git status at session start:**
```
M  docs/OPUS_SITREP_2026-04-10.md
 D scripts/eval_workbench_mechanics.py
 M scripts/text_theater.py
 M server.py
 M static/data/help/environment_command_overrides.json
 M static/data/help/environment_command_registry.json
 M static/main.js
```

Plus untracked files including `capture_probe/`, new docs, and texture directories.

**Impact:** The local worktree has significant uncommitted changes across critical files (server.py, main.js, text_theater.py). Any reasoning about "what the repo contains" must distinguish between:
- committed HEAD (what git log shows)
- local worktree (what file reads show)
- live runtime (what MCP probes show)

All three can differ. The worktree is ahead of HEAD. The runtime may be behind the worktree (if the server hasn't been restarted since the last edit).

**Resolution:** Checkpoint the worktree. This has been flagged as urgent across multiple sessions but not done. Until checkpointed, the risk of losing the current diff (which includes the 9-bone kneel seed, env_report recipe, theater-first gate wiring, and blackboard state builder) is real.

## Verification Checklist

Before trusting any claim about the current state, verify in this order:

1. **Is the claim about source or runtime?** They may differ.
2. **Is the worktree checkpointed?** If not, local edits could be lost.
3. **Theater first:**
   - `env_read(query='text_theater_embodiment')` — what does the theater show?
   - `env_read(query='text_theater_snapshot')` — what structured state is exposed?
4. **Report second:**
   - `env_report(report_id='route_stability_diagnosis')` — what does the broker diagnose?
5. **Raw state last resort:**
   - `env_read(query='shared_state')` — only if theater + report are insufficient
6. **Capsule status:**
   - `get_status()` — generation, Dreamer state, bag items
   - `heartbeat()` — alive, slots

Do not skip steps. Do not assume the previous session's observations are still current.

## Summary

Seven mismatches tracked. Two resolved as of Codex verification 2026-04-12:

| # | Mismatch | Severity | Resolution |
|---|---|---|---|
| 1 | ~~Kneel seed: 9-bone vs old 6-rotation runtime~~ | RESOLVED | Runtime now shows 9-bone macro. Kneel problem persists (correction loop not yet run). |
| 2 | ~~env_help doesn't teach env_report~~ | PARTIAL | Registry now teaches env_report. Minor discoverability cleanup remains. |
| 3 | Capsule help and local env_help are separate | LOW | Cross-reference in both |
| 4 | Dreamer obs_buffer_size = 0 despite docs saying it consumes | HIGH | Dreamer v1 wiring (roadmap seams 1-8) |
| 5 | Dreamer reward stream is generic, not mechanics-grounded | HIGH | Scoped mechanics reward feed |
| 6 | Dreamer stores an action slot but train_step ignores it | HIGH | Action-conditioning repair after first strike |
| 7 | Uncommitted worktree with critical changes | CRITICAL | Git checkpoint |
