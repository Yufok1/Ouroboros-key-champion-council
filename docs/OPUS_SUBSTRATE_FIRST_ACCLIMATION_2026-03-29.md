# Opus Substrate-First Acclimation

Status: Active handoff
Date: 2026-03-29
Audience: Fresh Opus/Codex/Claude agents entering `F:\End-Game\champion_councl`
Scope: Correct the architectural frame before any further reasoning or edits

## Purpose

This document exists to prevent a repeated framing error.

The primary system is not:

- the frontend
- the Environment theater
- the MCP surface
- FastAPI
- the product docs

The primary system is the generated quine capsule runtime:

- `capsule/champion_gen8.py`
- with `capsule/capsule.gz` as the protected compressed artifact

Everything else in this repo is a wrapper, host, adapter, or manifestation layer around that substrate.

## Non-Negotiable Hierarchy

Interpret the system in this order:

1. **Primary substrate**
   - the quine capsule runtime
   - the self-contained agent artifact
   - the source of council/swarm/replication capability

2. **Runtime shell**
   - `server.py`
   - process management, web serving, proxying, persistence bridge, activity bus

3. **Adapter surface**
   - MCP exposure
   - HTTP tool endpoints
   - external client interoperability

4. **Host surfaces**
   - browser theater
   - panel/UI
   - live mirror
   - Environment tab

5. **Downstream product doctrine**
   - environment product
   - character product
   - mount contract
   - desktop companion delivery form

If an agent reasons in the reverse order, it will overfit to UI or MCP behavior and misdiagnose the system.

## Repo Facts That Prove This

### 1. The server is explicitly a gateway around the capsule

`server.py` opens with:

- runtime gateway
- panel serving
- proxying capsule tool calls
- exposing the substrate to browser and MCP-facing clients

This is wrapper language, not source-of-truth language.

Key anchors:

- `server.py:1-8`
- `server.py:1278` -> `CAPSULE_PATH = Path("capsule/champion_gen8.py")`
- `server.py:1606` -> `start_capsule()`
- `server.py:1614` -> launches `champion_gen8.py` as the runtime process
- `server.py:1822-1829` -> decompresses `capsule/capsule.gz` when needed

### 2. The protected artifact policy centers the capsule, not the shell

The repo repeatedly treats the capsule as protected:

- `server.py:3204`
- `server.py:3635`
- `docs/RESUME_PROMPT_AGENT_COMPILER_MODALITIES_2026-03-14.md`
- `docs/OPERABILITY_CHECKPOINT_2026-03-15.md`
- `docs/CODEX_SKILLS_SYSTEM_FULL_PROMPT.md`

The stable rule is:

- do not edit `capsule/champion_gen8.py` directly
- do not edit `capsule/capsule.gz` directly
- if substrate behavior must change, the true source is the external compiler/factory

### 3. Prior repo audits already identified the true upstream source

`docs/AGENT_COMPILER_MODALITY_ACCLIMATION_REPORT_2026-03-14.md` states:

- factory source: `F:\End-Game\ouroboros-key\agent_compiler.py`
- generated runtime inspected: `F:\End-Game\champion_councl\capsule\champion_gen8.py`
- `agent_compiler.py` is a multi-level quine generator

That means this repo contains the generated capsule runtime, not the compiler of record.

## Correct Interpretation Of The Current Docs

There are two real documentation layers in this repo, and they can be mistaken for architectural primacy if read carelessly.

### Layer A: Capsule-first / quine-first traces

These documents preserve the original substrate truth:

- `docs/AGENT_COMPILER_MODALITY_ACCLIMATION_REPORT_2026-03-14.md`
- `docs/RESUME_PROMPT_AGENT_COMPILER_MODALITIES_2026-03-14.md`
- `docs/OPERABILITY_CHECKPOINT_2026-03-15.md`

These are the best references when the question is:

- what is sacred
- what is generated
- what can be edited safely
- where true runtime changes originate

### Layer B: Product/doctrine/runtime manifestation docs

These documents describe how the capsule is being embodied in the current product lane:

- `docs/CHAMPION_COUNCIL_IDENTITY_2026-03-25.md`
- `docs/CHAMPION_COUNCIL_ROADMAP_2026-03-24.md`
- `docs/CHARACTER_RUNTIME_AND_PORTABILITY_ARCHITECTURE_SPEC.md`
- `docs/CHARACTER_EMBODIMENT_SPEC.md`
- `docs/CHARACTER_RUNTIME_ACCLIMATION_2026-03-28.md`
- `docs/rode.txt`

These are useful, but they are downstream doctrine.

They explain:

- how the theater should behave
- how character/environment products should be treated
- what the active lane is
- how the browser/runtime shell is supposed to work

They do **not** outrank the capsule-first truth.

## The Practical Architecture

### A. Core substrate

The quine capsule is the actual intelligence-bearing artifact.

In practical terms, it is responsible for:

- identity
- council slot semantics
- replication/swarm primitives
- tool registry and execution
- provenance/integrity concepts
- memory model
- workflow/cognition substrate

Do not mistake the fact that the repo exposes these through APIs for those APIs being primary.

### B. Runtime shell

`server.py` is the host runtime around the capsule.

Its job is to:

- start/stop the capsule process
- connect to the capsule over MCP/SSE
- proxy or postprocess tool calls
- serve panel/theater static assets
- maintain activity streams and live mirror surfaces
- bridge persistence and packaging

This shell is important, but it is still a shell.

### C. MCP is an adapter, not the doctrine

MCP matters because it is how external agents and clients interact with the capsule.

But MCP is not the essence of the system.

It is one interoperability layer around the capsule.

An MCP tool contract can be narrower, broader, or partially stale without redefining the capsule itself.

This matters because recent confusion came from over-trusting an MCP-facing control surface as if it were the whole runtime truth.

### D. Frontend is a host surface

The browser theater and Environment tab are inspection/control shells.

They are not the origin of the system.

`static/main.js` is still a major operational file because it implements:

- theater/runtime presentation
- mounted runtime control
- environment mirror ingestion
- workbench and animation-control flows

But it remains a host surface around the capsule and runtime shell, not the substrate of record.

## Current Manifestation Layer In This Repo

Right now the active manifestation work is the mounted character runtime lane.

That includes:

- character workbench theater mode
- rig detection
- humanoid scaffold
- mounted runtime export
- animation surface
- owned-surface animation controls

Recent commit chain:

- `7c67d8c` character workbench theater mode
- `a45f19b` inspection surfaces
- `3508c5c` source rig detection
- `ad64031` humanoid scaffold
- `8d55dc3` / `9bba3c0` character model identity stabilization
- `bee4162` theater session persistence
- `ef58c97` mounted animation lane checkpoint

This is important current work, but it is still a downstream embodiment layer.

It should not be mistaken for the architectural center.

## Live Runtime Facts Worth Knowing

The live mirrored state currently shows:

- focus on `character_runtime::mounted_primary`
- theater mode `character`
- mounted character runtime active
- `command_surface.transport = "env_control"`
- animation surface present and live
- mounted asset currently points to `kenney-mini-dungeon/character-human.glb`

This confirms the current shell/runtime lane is active.

It does **not** change the deeper hierarchy:

- capsule first
- shell second
- MCP/HTTP third
- frontend fourth

## What Opus Must Not Assume

Do not assume:

- the frontend is the source of truth
- MCP is the source of truth
- every `env_control` surface is the same thing
- product docs are the deepest architecture
- character/environment doctrine supersedes capsule primacy

Do not reason from:

- a UI affordance outward
- a single external tool contract outward
- a browser control-path issue inward toward the substrate

Start at the substrate boundary and move outward.

## Safe Edit Policy

Inside this workspace:

- safe first targets are docs, `server.py`, `static/*`, and other shell/runtime surfaces
- `capsule/champion_gen8.py` is not a routine edit target
- `capsule/capsule.gz` is not a routine edit target

If a task truly requires substrate changes:

1. prove the shell/adapters cannot solve it
2. identify the upstream compiler/factory as the real source of change
3. treat the generated capsule here as protected output, not hand-edit surface

## Correct Read Order For Fresh Opus

Read in this order:

1. `docs/OPUS_SUBSTRATE_FIRST_ACCLIMATION_2026-03-29.md`
2. `docs/AGENT_COMPILER_MODALITY_ACCLIMATION_REPORT_2026-03-14.md`
3. `docs/RESUME_PROMPT_AGENT_COMPILER_MODALITIES_2026-03-14.md`
4. `server.py`
5. `docs/CHAMPION_COUNCIL_IDENTITY_2026-03-25.md`
6. `docs/CHAMPION_COUNCIL_ROADMAP_2026-03-24.md`
7. `docs/CHARACTER_RUNTIME_AND_PORTABILITY_ARCHITECTURE_SPEC.md`
8. `docs/CHARACTER_RUNTIME_ACCLIMATION_2026-03-28.md`
9. `docs/rode.txt`

This order forces substrate-first orientation before product-lane interpretation.

## Source Anchors

Use these anchors when re-acclimating:

- `server.py:1278` -> capsule path
- `server.py:1606-1639` -> start/stop capsule process
- `server.py:1674-1719` -> connect to capsule MCP server and cache instructions
- `server.py:1822-1834` -> decompress `capsule.gz` and boot runtime
- `server.py:7320` -> HTTP tool proxy
- `server.py:8468-8664` -> external MCP proxy path
- `static/main.js:9509` -> mounted runtime record
- `static/main.js:17625` -> queued control ingress
- `static/main.js:18838` -> browser control executor
- `static/main.js:44950-45033` -> public character helper bridge

## Bottom Line

Champion Council in this repo should be understood as:

- a generated quine capsule runtime at the core
- wrapped by a Python runtime gateway
- exposed through MCP/HTTP adapters
- observed and steered through browser/theater host surfaces
- currently manifested through environment/character product doctrine

If Opus starts from the frontend or from MCP, it will keep making shallow mistakes.

If Opus starts from the capsule boundary and works outward, the rest of the repo becomes legible.
