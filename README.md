---
title: Champion Council
emoji: "🐍"
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
license: mit
short_description: 'Operator runtime for AI councils, theaters, continuity, and embodied tooling'
tags:
  - mcp
  - ai-agent
  - workflow
  - local-ai
  - llm
  - multi-model
  - observability
  - simulation
  - diagnostics
  - vscode
app_port: 7860
---

# Champion Council

Champion Council is a local-first operator runtime for AI systems. It combines model orchestration, a 3D/web theater, a text theater, embodiment/workbench tools, blackboard-driven query surfaces, continuity recovery, FelixBag memory, Coquina-style skin embodiment, and workflow automation inside one repo.

This repo is not just a model switchboard and not just a Hugging Face Space wrapper. It is the active runtime and operator surface for building, observing, steering, and diagnosing a living multi-surface AI system.

If you want one canonical human-facing overview of the whole stack, start with [`docs/CHAMPION_COUNCIL_LIVING_SYSTEM_HUB.md`](docs/CHAMPION_COUNCIL_LIVING_SYSTEM_HUB.md).

If you want one single-file external handoff that explains the current system without requiring a doc crawl, use [`docs/CHAMPION_COUNCIL_SHAREABLE_SYSTEM_OVERVIEW_2026-04-22.md`](docs/CHAMPION_COUNCIL_SHAREABLE_SYSTEM_OVERVIEW_2026-04-22.md).

If you want the short public-facing version, use [`docs/CHAMPION_COUNCIL_PUBLIC_OVERVIEW_2026-04-22.md`](docs/CHAMPION_COUNCIL_PUBLIC_OVERVIEW_2026-04-22.md).

## What It Is

Champion Council is built around one core rule:

- one truth source, no duplicate authority planes

In practice, that means:

- runtime state is the authority
- the web theater and text theater are peer consumers of that truth
- blackboard/query-work is an operator worksheet, not a second brain
- continuity is a re-entry and posture-recovery lane, not a truth override
- docs and FelixBag are planning/material surfaces that dock to live work, not detached shelves

## What Lives Here

### Council Runtime

- up to 32 council slots for plugged models
- multi-model chaining, comparison, and workflow-driven orchestration
- OpenAI-compatible and Hugging Face-facing provider surfaces
- MCP tool exposure for external clients and local operator flows

### Theaters And Operator Surfaces

- **Web theater** for spatial observation, workbench interaction, environment surfaces, and selective text-rendered overlays
- **Text theater** for render, consult, diagnostics, blackboard, evidence lanes, and compact embodied state reads
- **Workbench / embodiment** surfaces for skeleton, scaffold, attachment, pose, and authored sequence work
- **Coquina / skin service** for projecting shared pose, support, weather, and sequence truth into web materials, text-braille skins, hair fields, and trails

### Blackboard, Query, And Continuity

- blackboard `query_thread` with `objective`, `help_lane`, `next_reads`, and guardrails
- `output_state`-style orienting surfaces for equilibrium, attention, docs packet, and derived runtime posture
- continuity restore for archive-side reacclimation after resets or context compression
- docs carried as a real planning/query surface instead of a loose evidence shelf

### Named Runtime Lanes

- **`output_state`** is the orienting crane over the live runtime, not a second truth plane
- **`equilibrium`** is the settling gauge inside `output_state`
- **`trajectory_correlator`** grades intended vs actual sequence/path behavior
- **`continuity_cue`** is the visible reorientation bell, not an autonomous override
- **`docs_packet`** is the bounded planning/material face over repo docs and FelixBag docs
- **`continuity_packet`** is the bounded archive/reacclimation face over `continuity_restore`
- **`Tinkerbell`** is the first-pass pointer/attention layer over the orienting field
- **`Dreamer`** is the bounded proposer/scorer over truthful observations, query state, and orienting context
- **`Pan`** is the support/contact/route measurement lane that can later route or propose without bypassing physical truth
- **`watch_board`**, **`drift`**, **`freshness`**, and **`confidence`** are explicit runtime condition surfaces, not implied mood

### Intervention, Capture, And Corroboration

- **HOLD** is an intervention latch and audit seam, not a hidden authority plane
- capture surfaces such as `text_theater_snapshot`, `text_theater_embodiment`, `capture_supercam`, and scoped probe flows provide the corroboration path
- the repo favors visible query-work, bounded packets, and capture receipts over invisible planner state

### Memory, Docs, And Planning

- FelixBag semantic memory and document search
- queryable/checkpointable planning docs
- repo docs as authored source, FelixBag as operational mirror
- continuity packets that recommend the current docs landscape during re-entry

### Diagnostics And Investigation

- environment/operator help surfaces
- report and snapshot-driven diagnosis
- theater capture lanes such as `capture_supercam` and scoped probe/corroboration flows
- read-side diagnostic brokering instead of ad hoc duplicate analysis planes

### Workflow Automation

- DAG workflows for tool, agent, merge, branch, HTTP, search, and fan-out steps
- automation that can stay docked to the same runtime surfaces as the operator

## System Doctrine

Champion Council is best understood as an operator cockpit with multiple coordinated surfaces:

- **Council** chooses and runs models
- **Theaters** show runtime state in different forms
- **Workbench** edits and stages embodied/spatial behavior
- **Blackboard** carries ordered query work and evidence planning
- **Continuity** restores posture after interruption
- **FelixBag + docs** carry memory and planning material
- **Workflows + MCP** automate and expose the system externally

The important architectural split is:

- this repo is the descendant/runtime/consumer surface
- the broader upstream quine/speciation/lattice framework lives in `D:\End-Game\ouroboros-key`

Champion Council is therefore a runtime instrument built on a larger Ouroboros substrate, not the entire parent architecture by itself.

The current code-backed role split is:

- `output_state` carries the orienting summary
- `blackboard.working_set.query_thread` carries the visible sequence and ordered evidence lane
- `Tinkerbell` points
- `Pan` measures
- `Dreamer` proposes and scores
- HOLD latches intervention points
- capture surfaces corroborate what the runtime is actually doing
- docs and continuity packets assist re-entry, but do not outrank live theater, snapshot, or source

## Current Identity

The project has moved beyond a plain “AI model orchestrator” description.

The accurate read now is:

- a local-first AI control room
- a multi-surface runtime for observing and steering live AI state
- a continuity-aware operator environment
- a diagnostics and planning surface that can carry its own working posture forward
- a build space for embodied, theatrical, procedural, and workflow-driven AI behaviors

## Local Mode

This repo can run locally from the same folder used for the Hugging Face Space.

Use:

```powershell
./run_local.ps1
```

Default local-mode settings from `run_local.ps1`:

- `WEB_HOST=127.0.0.1`
- `WEB_PORT=7866`
- `MCP_PORT=8766`
- `APP_MODE=development`
- `MCP_EXTERNAL_POLICY=full`
- `PERSISTENCE_MODE=local`
- `PERSISTENCE_DATA_DIR=./data/champion-council-state`

What this gives you:

- local web UI at `http://127.0.0.1:7866/panel`
- local-only persistence by default
- the same repo layout used by the Space build

Notes:

- If you want Hugging Face Inference Provider routing locally, set `HF_TOKEN` before launch.
- OpenAI-compatible providers can still be plugged through the UI.
- Local runtime state under `./data/` is ignored by git.
- To preview product behavior locally, set `APP_MODE=product` and either:
  - `MCP_EXTERNAL_POLICY=closed` for no external MCP access
  - `MCP_EXTERNAL_POLICY=guided` for a curated external MCP surface such as `env_read`, `env_control`, `workflow_execute`, `workflow_status`, `workflow_history`, `get_status`, `heartbeat`, and `get_cached`

## Key Repo Surfaces

- [`server.py`](server.py) — runtime, tool endpoints, output-state and continuity-facing server logic
- [`static/main.js`](static/main.js) — web theater, workbench, blackboard mirroring, browser/runtime operator surfaces
- [`scripts/text_theater.py`](scripts/text_theater.py) — text theater rendering, consult/blackboard/evidence views
- [`docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md`](docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md) — current operative trajectory
- [`docs/CHAMPION_COUNCIL_LIVING_SYSTEM_HUB.md`](docs/CHAMPION_COUNCIL_LIVING_SYSTEM_HUB.md) — single-document human-facing system map
- [`docs/CONTINUITY_DOCS_PLANNING_SURFACE_SPEC_2026-04-20.md`](docs/CONTINUITY_DOCS_PLANNING_SURFACE_SPEC_2026-04-20.md) — docs as planning/query substrate
- [`docs/COQUINA_SKIN_SERVICE_CONTINUITY_NOTE_2026-04-22.md`](docs/COQUINA_SKIN_SERVICE_CONTINUITY_NOTE_2026-04-22.md) — current skin-service continuity and recovery seam
- [`docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md`](docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md) — continuity posture and reset/re-entry alignment

## VS Code Extension

[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/Ouroboros.champion-council?label=VS%20Code%20Marketplace&logo=visual-studio-code)](https://marketplace.visualstudio.com/items?itemName=Ouroboros.champion-council)

Links:

- [GitHub Repository](https://github.com/Yufok1/Ouroboros_extension)
- [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Ouroboros.champion-council)

## License

MIT
