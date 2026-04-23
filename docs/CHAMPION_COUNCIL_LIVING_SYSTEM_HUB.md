# Champion Council Living System Hub

Repo: `D:\End-Game\champion_councl`

Purpose:

- give the repo one human-facing document that explains what Champion Council is as a whole
- sit above `get_help`, `env_help`, continuity, and the dated sprint docs without replacing them
- keep the named runtime lanes, authority split, and operator surfaces in one readable place
- serve as the best "start here" document for a new operator or a reacclimating agent

## Bottom Line

Champion Council is a local-first AI operator runtime.

It is not just:

- a Hugging Face Space shell
- a model switchboard
- a workflow editor
- a theater demo
- a memory store

It is the combined runtime where these surfaces meet:

- council slots and provider routing
- web theater and text theater
- workbench and embodiment
- blackboard query-work
- `output_state` and its orienting sub-surfaces
- continuity recovery
- FelixBag and docs planning
- diagnostics, reports, and captures
- workflows and MCP exposure

## The Three Help Faces

There are three different "explain the system" faces, and they should not be collapsed into one vague blob.

### 1. `get_help(...)`

This is the capsule/tool help surface.

Use it for:

- capsule-side tools
- MCP tool contracts
- broad system/tool capability discovery

It is the backend/tool registry face.

### 2. `env_help(...)`

This is the environment/browser/runtime help surface.

Use it for:

- theater commands
- workbench commands
- browser-local controls
- surface bridges
- operator playbooks

It is richer than capsule help for environment-side behavior and transport details.

### 3. This Hub Doc

This document is the human-facing system map.

Use it for:

- understanding the whole stack
- understanding how the major surfaces relate
- finding the right next canonical doc
- onboarding someone who needs the shape before the command reference

Rule:

- `get_help` explains tools
- `env_help` explains runtime/browser controls
- this hub explains the system

None of them should try to fully subsume the others.

## Authority Split

Champion Council is built on one non-negotiable rule:

- one truth source, no duplicate authority planes

Current authority order:

1. live runtime state
2. live theater and capture corroboration
3. blackboard/query-work and `output_state` as derived readable carriers
4. scoped reports and contracts
5. docs and continuity packets as planning/archive faces

What that means:

- docs do not outrank live theater
- continuity does not outrank fresh corroboration
- blackboard does not become a second brain
- `env_report` does not become a second runtime

## Core Runtime Surfaces

### Council

The council surface is the model runtime:

- up to 32 council slots
- provider routing
- model invocation
- multi-model comparison and chaining

This is the AI execution layer, not the whole system by itself.

### Web Theater

The web theater is the spatial/browser-facing observation and interaction surface.

It carries:

- 3D scene/environment observation
- workbench interaction
- embodiment staging
- selective text-rendered overlay surfaces
- browser-local operator controls

### Text Theater

The text theater is the compact consult/render/diagnostic surface.

It carries:

- render summaries
- consult view
- blackboard view
- evidence lanes
- embodiment reads
- snapshot-oriented diagnostics

It is a serious operator surface, not a novelty terminal.

### Workbench / Embodiment

The workbench is the embodiment and authored staging surface.

It carries:

- skeleton
- scaffold
- attachments
- pose
- authored sequences
- builder/helper strip behavior

### `sequence_field` And `skin_service`

The embodiment/render lane is becoming more explicit instead of staying hidden in theater glue.

- `sequence_field` carries the active resource and phase lane
- `sequence_field.force_wave` carries the downstream embodiment packet
- `skin_service` is the visible embodiment translator over that packet

Current role:

- consume pose, support, weather, and field truth
- project into web material, text braille, hair field, and trail consumers
- stay downstream of support/contact/balance truth

It is not:

- a new authority plane
- a replacement for `Pan`, `output_state`, or workbench truth
- a controller that writes spectacle back into blackboard/query state

## Query And Orienting Surfaces

### `blackboard.working_set.query_thread`

This is the visible query-work lane.

It carries:

- objective
- visible read
- anchor rows
- help lane
- next reads
- raw-state guardrail

It is the ordered evidence worksheet.

### `output_state`

This is the orienting crane over runtime truth.

It is not a new authority plane.

Important live child surfaces include:

- `equilibrium`
- `trajectory_correlator`
- `continuity_cue`
- `tinkerbell_attention`
- `pan_probe`
- `watch_board`
- `drift`
- `freshness`
- `confidence`
- `docs_packet`
- `continuity_packet`

Canonical continuity-side index for the named associative surface set:

- `docs/ASSOCIATIVE_SURFACES_CONTINUITY_INDEX_2026-04-22.md`
- `docs/CONTINUOUS_OBSERVATION_DREAMER_GOVERNANCE_NOTE_2026-04-22.md`

### Role Split

Current code-backed role split:

- `output_state` carries the orienting summary
- `equilibrium` is the settling gauge
- `trajectory_correlator` grades intended vs actual path/sequence
- `continuity_cue` is the visible reorientation bell
- `Tinkerbell` points
- `Pan` measures
- `Dreamer` proposes and scores
- HOLD latches intervention points
- captures corroborate what the runtime is actually doing

## Named Systems

### Tinkerbell

Tinkerbell is the first-pass pointer/attention layer over the orienting field.

It is:

- pointer-only
- derived from current orienting state
- visible in consult/blackboard/report paths

It is not:

- a second authority plane
- a replacement for Pan

### Pan

Pan is the support/contact/route measurement lane.

It is:

- measurement-first
- grounded in support/contact/balance truth
- allowed to later route or propose

It must not bypass physical or staging truth.

### Dreamer

Dreamer is the bounded proposer/scorer lane.

It already consumes meaningful orienting context.

Its correct role is:

- proposal
- ranking
- bounded scoring over truthful observations

Its incorrect role would be:

- direct authority over embodiment truth
- detached speculative controller

### HOLD

HOLD is the intervention latch and audit seam.

It is real as a tool/UI seam.

It is not yet the entire generic shutter/freeze packet system people sometimes gesture at in theory.

### Docs Packet And Continuity Packet

These are the two bounded carried faces that make the system re-enterable.

- `docs_packet` = planning/material face over repo docs and FelixBag mirror
- `continuity_packet` = archive/reacclimation face over `continuity_restore`

They help the operator resume and plan.
They do not decide live truth by themselves.

### Coquina / Skin Service

The current Coquina-facing seam is now explicit enough to name:

- `skin_service` is the downstream embodiment face for procedural skins
- it rides the same truth spine as `sequence_field.force_wave`
- it is where elemental materials, text-surface armor, hair fields, and future palette or cloth layers should dock

Correct doctrine:

- truth first
- embodiment translation second
- spectacle never outranks support/contact/balance

## Memory, Docs, And Planning

Champion Council has two major non-runtime reference surfaces:

### FelixBag

FelixBag is the queryable/checkpointable memory and document mirror surface.

Use it for:

- semantic memory
- bag-backed docs
- checkpointed planning materials
- queryable operator memory

### Repo Docs

Repo docs are the authored source/planning surface.

The current doctrine is:

- repo docs are authored source
- FelixBag is the operational mirror
- continuity can recommend the relevant docs during re-entry
- `docs_packet` carries the bounded live planning face

## Workflows And MCP

Champion Council is also an automation surface.

It exposes:

- MCP tools
- workflow DAGs
- execution/status/history surfaces
- operator automation that docks to the same runtime truth

This matters because the system is not just interactive; it is automatable without inventing a second control plane.

## Historical View

The system did not arrive all at once. Its identity sharpened through several phases:

### Phase 1: Capsule / tool runtime

The backend/capsule/tool logic established the quine-aware substrate and the tool surface.

### Phase 2: Environment and theater surfaces

The browser/runtime surfaces, theaters, workbench, and operator control seams became first-class.

### Phase 3: Blackboard and query-work

The visible worksheet/evidence model became real instead of implied.

### Phase 4: Continuity and planning packets

Archive continuity, docs planning, and operative memory alignment became carried surfaces instead of transcript archaeology.

### Phase 5: Named orienting lanes

`output_state`, `equilibrium`, `Tinkerbell`, `Pan`, `Dreamer`, HOLD, `docs_packet`, and `continuity_packet` became the most useful way to name the living system.

This hub exists because the project is now too large to describe accurately as only:

- orchestrator
- theater
- workflow engine
- Space app

It is all of those, but only as coordinated surfaces in one runtime.

## Start Here

If you need the shortest correct entry path:

1. read this hub
2. read `README.md`
3. read `docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md`
4. read `docs/CONTINUITY_DOCS_PLANNING_SURFACE_SPEC_2026-04-20.md`
5. use `get_help(...)` for capsule/tool discovery
6. use `env_help(...)` for environment/browser/runtime command discovery

## Canonical Next Docs

Read these next, depending on what you are trying to understand:

- `docs/CURRENT_ACTIVE_TRAJECTORY_2026-04-13.md`
- `docs/OPERATIVE_MEMORY_ALIGNMENT_SPEC_2026-04-15.md`
- `docs/CONTINUITY_DOCS_PLANNING_SURFACE_SPEC_2026-04-20.md`
- `docs/FRACTAL_QUERY_CONTINUITY_SURFACE_SPEC_2026-04-21.md`
- `docs/BLACKBOARD_QUERY_PROCUREMENT_DEEP_DIVE_2026-04-13.md`
- `docs/ENVIRONMENT_MEMORY_INDEX.md`
- `docs/ENVIRONMENT_HELP_SYSTEM_SPEC_2026-04-04.md`
- `docs/ENV_HELP_SITREP_2026-04-04.md`
- `docs/TINKERBELL_HOLD_SHUTTER_DREAMER_CODE_ALIGNMENT_CHECKPOINT_2026-04-19.md`
- `docs/COQUINA_SKIN_SERVICE_CONTINUITY_NOTE_2026-04-22.md`

## Update Rule

This is a living hub.

Update it when any of these change materially:

- the named runtime lane split
- the authority order
- the relation between `get_help`, `env_help`, and docs
- the role of `Dreamer`, `Tinkerbell`, `Pan`, HOLD, or `output_state`
- the role of `sequence_field.force_wave` or `skin_service`
- the relation between docs and continuity packets

If this file falls behind, it stops serving its purpose.
