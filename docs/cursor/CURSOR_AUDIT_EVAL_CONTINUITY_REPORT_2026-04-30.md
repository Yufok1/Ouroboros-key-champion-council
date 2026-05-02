# Cursor Audit/Eval Continuity Report - 2026-04-30

Audience: Cursor taking over audit and eval support for Champion Council.

## Mission

Cursor's job is not to rediscover the whole system from scratch, and it is not to receive every answer pre-chewed. Cursor should run continuity first, connect to both Champion Council surfaces, then audit/evaluate against live evidence:

- local self-deploy: `http://127.0.0.1:7866`
- Hugging Face Space: `https://tostido-champion-council-private.hf.space`
- repo root: `D:\End-Game\champion_councl`

Read this operator contract before beginning audit/eval:

- `docs/cursor/CURSOR_OPERATOR_CONTRACT_CLIPBOARD_2026-04-30.md`

For Convergence Engine organism JSON and organism-chat audit, also read:

- `docs/cursor/CONVERGENCE_ORGANISM_JSON_READING_PROTOCOL_2026-04-30.md`

Official Cursor MCP notes used for this setup:

- `https://docs.cursor.com/en/context/model-context-protocol`
- `https://docs.cursor.com/cli/mcp`

Cursor supports project-scoped MCP config at `.cursor/mcp.json`, and the Cursor agent can list MCP servers/tools with `cursor-agent mcp list` and `cursor-agent mcp list-tools <server>`.

## MCP Setup

This repo now includes project MCP config:

```json
{
  "mcpServers": {
    "champion-ouroboros-self-deploy": {
      "url": "http://127.0.0.1:7866/mcp/sse"
    },
    "champion-ouroboros-space": {
      "url": "https://tostido-champion-council-private.hf.space/mcp/sse",
      "headers": {
        "Authorization": "Bearer ${env:HF_TOKEN}"
      }
    }
  }
}
```

Before using the Space MCP server, set `HF_TOKEN` in the environment where Cursor is launched. Do not paste the token into `.cursor/mcp.json`.

Recommended verification from a terminal opened in this repo:

```powershell
cursor-agent mcp list
cursor-agent mcp list-tools champion-ouroboros-self-deploy
cursor-agent mcp list-tools champion-ouroboros-space
```

If Cursor cannot see the Space tools, first confirm `HF_TOKEN` is available to Cursor's process and that the Space is running. If Cursor cannot see the local tools, confirm the local Champion Council server is running on port `7866`.

Verified from this workstation on 2026-04-30:

- `champion-ouroboros-self-deploy` listed `192` MCP tools through `http://127.0.0.1:7866/mcp/sse`
- `champion-ouroboros-space` listed `192` MCP tools through `https://tostido-champion-council-private.hf.space/mcp/sse`
- sample tools on both: `get_cached`, `clear_cache`, `forward`, `deliberate`, `imagine`, `embed_text`, `get_provenance`, `bag_get`, `bag_put`, `list_slots`, `plug_model`, `spawn_swarm`

So the MCP transport and tool discovery are in order on both servers. Cursor still needs to load the project config and have network access from its own process.

## Clipboard Access

If the operator asks Cursor to check the Windows clipboard, use:

```powershell
Get-Clipboard -Raw
```

Rules:

- Treat clipboard content as operator-provided context, not verified truth.
- If it contains tokens, passwords, cookies, private keys, or auth headers, do not write it to repo files.
- If it is doctrine, logs, prompts, or runtime notes, summarize or store it only when the operator asks.

## Required Continuity Lane

For orientation, reset recovery, audit posture, server-state questions, or text theater work, run this sequence before source crawling:

1. `continuity_status`
2. `continuity_restore(summary='Cursor audit eval takeover for Champion Council self-deploy and Space parity', cwd='D:\End-Game\champion_councl')`
3. `env_help(topic='continuity_reacclimation')`
4. `env_read(query='text_theater_embodiment')`
5. `env_control(command='capture_supercam', actor='assistant')`
6. `env_read(query='supercam')`
7. `env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)`
8. `env_read(query='text_theater_snapshot')`
9. `env_report(report_id='paired_state_alignment')`

Rule: live theater, blackboard, snapshot freshness, scoped reports, and supercam captures outrank archive summaries when they disagree.

## Current Verified State

Latest handoff file:

- `docs/brotology/TWITCH_MANEUVER_CONTINUITY_HANDOFF_2026-04-30.md`

Memory key:

- `continuity/handoff/twitch_maneuver/2026-04-30`

Active session:

- `019ddcb6-cab0-7d33-8c78-34cc5517a50e`

Text theater posture:

- local bundle `133d`
- Space bundle last verified `133c`
- canonical repaired base pose `twitch_beat_5_saiyan_fire_uncross_guard`
- corrected clip `twitch_maneuver_chat_pat_uncross_saiyan`
- stance `double_support`
- balance risk `0`
- balance margin `0.5855`
- both feet planted
- active trail `twitch_maneuver_continuity_trail`

Known text theater caveat:

- the render view reported bundle `133d` as fresh, but one output-state read showed mirror lag near 855 seconds. On resume, corroborate with `capture_supercam` and render diagnostics before new animation edits.

## Audit/Eval Priorities

1. MCP health: both self-deploy and Space should list tools and accept simple read-only calls.
2. Continuity lane: `continuity_status`, `continuity_restore`, `env_read`, and `env_report` should work without forcing a source crawl.
3. Text theater parity: local and Space should both expose the text theater view, snapshot, and blackboard surfaces.
4. Dreamer health: verify Dreamer tab/API state before claiming learning is active.
5. Slot safety: local Gemma clones were alive, but the routed `Gemma-3-4B-provider` returned `401 Unauthorized`; provider auth must be fixed before swarm eval depends on it.
6. Tool safety: no reset, state clear, factory restore, or capsule restart unless the operator explicitly asks.

## Audit Knots To Untie

Do not treat these as solved conclusions. Treat them as trailheads and classify the drift with evidence:

1. Local versus Space MCP: are both exposing the same tool contract, or only similar transport?
2. Text theater parity: does parity mean same bundle, same visible render, same blackboard, same snapshot freshness, or same command behavior?
3. Dreamer status: what does "active" prove, and what still needs a behavioral receipt?
4. Slot/provider routing: when a provider fails, is the failure auth, transport, model contract, or tool gating?
5. Organism learning path: does a private organism chat actually reach the linguistic association and reward surfaces?
6. Suggestion popup loop: can organism-authored suggestions be recognized as selected-by-human without becoming grabby or over-attributed?
7. Placeholder geometry: is a blocky visual a missing asset, a renderer fallback, a gated feature, or stale state?
8. Continuity pairing: when archive and live theater disagree, which surface proves the current body state?

Good audit behavior: follow one knot until it classifies cleanly, then publish receipts. Do not flatten everything into one vague "broken" bucket.

## Do Not Touch Without Explicit Operator Approval

- Do not reset the local server or Space just because a read is stale.
- Do not edit `capsule/champion_gen8.py` or `capsule.gz` directly.
- Do not commit Hugging Face tokens.
- Do not revert dirty worktree changes you did not make.
- Do not treat archive continuity as live truth when live theater evidence disagrees.

## First Prompt For Cursor

Use this as Cursor's first chat message in this repo:

```text
You are taking over Champion Council audit/eval support. Read AGENTS.md, .cursor/rules/champion-council-audit-eval.mdc, docs/cursor/CURSOR_AUDIT_EVAL_CONTINUITY_REPORT_2026-04-30.md, docs/cursor/CURSOR_OPERATOR_CONTRACT_CLIPBOARD_2026-04-30.md, and docs/cursor/CONVERGENCE_ORGANISM_JSON_READING_PROTOCOL_2026-04-30.md first. Connect to both MCP servers if available: champion-ouroboros-self-deploy and champion-ouroboros-space. Run the continuity lane before source crawling. Do not reset state. Do not edit generated capsule files. Start with read-only health, continuity, text theater, Dreamer, slot, organism learning, and parity checks. Treat the Audit Knots as questions to untie, not answers. Report findings with file/tool evidence.
```

## Practical Fallback

If MCP is unavailable inside Cursor, use the HTTP tool fallback while the local server is live:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:7866/api/tool/continuity_status' -ContentType 'application/json' -Body '{"limit":3}'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:7866/api/tool/get_status' -ContentType 'application/json' -Body '{}'
```
