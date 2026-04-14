# Blackboard Query Procurement Deep Dive 2026-04-13

Repo: `F:\End-Game\champion_councl`

Purpose:

- map the current blackboard/query/help/report/mirror substrate as it actually exists
- name the smallest honest extension that lets blackboard procure evidence without becoming a second authority
- identify artifact and payload classes that fit the existing system
- tie the local design to adjacent known patterns without importing alien architecture

## Bottom Line

The current system already contains the pieces of a procurement-capable blackboard:

- blackboard stores `query_thread` with `objective`, `help_lane`, `next_reads`, and a raw-state guardrail
- text theater renders that thread visibly for both operator and agent
- `env_help` already teaches ordered procedures and transport gotchas
- `env_report` already acts as a stateless diagnostic broker over existing truth
- command-attached text-theater payloads, mirror state, contracts, and capture surfaces already exist

What does not exist yet is a clean execution bridge from:

- blackboard chooses evidence steps

to:

- existing tool lane executes those steps and returns receipts/artifacts back into the same session

That is the smallest truthful extension. It is not a new system. It is an activation of the one already here.

## What Exists Now

### 1. Runtime Truth

The mechanics/environment runtime remains the only truth source.

See:

- `docs/DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md`
- `static/main.js`

Doctrine:

- text theater is not authoritative
- blackboard is not authoritative
- env_report is not authoritative
- env_help is not authoritative

They are all consumers of runtime truth.

### 2. Blackboard As Structured Query Worksheet

The current blackboard is not just row storage. It already carries a session-threaded query substrate.

Source anchors:

- `static/main.js:_envBuildBlackboardState`
- `scripts/text_theater.py:_render_blackboard_section`
- `scripts/text_theater.py:_consult_query_thread`
- `scripts/text_theater.py:_consult_query_evidence`

Current blackboard query-thread fields:

- `objective_id`
- `objective_label`
- `visible_read`
- `anchor_row_ids`
- `help_lane`
- `next_reads`
- `raw_state_guardrail`

This means blackboard already does:

- objective selection
- ordered evidence planning
- help selection
- guardrail declaration
- session threading

It does not yet execute those reads itself.

### 3. Text Theater As Visible Query Surface

Text theater already exposes the blackboard query substrate as a visible operator/agent surface.

Current render roles:

- blackboard section: raw structured thread + rows
- consult orientation: compact objective/help lane
- consult evidence: next reads + reasons + guardrail

This is important because it means the query logic is already inspectable. It is not hidden planner state.

### 4. `env_help` As Discoverability Authority

`env_help` already owns:

- command reference
- family overviews
- playbooks
- transport and mode distinctions
- behavioral guidance such as theater-first ordering

It does not execute tools. It describes what exists and how to use it.

Current relevant help assets:

- `static/data/help/environment_command_registry.json`
- `static/data/help/environment_command_overrides.json`
- `docs/ENVIRONMENT_HELP_SYSTEM_SPEC_2026-04-04.md`

### 5. `env_report` As Stateless Diagnostic Broker

`env_report` is already the fused diagnostic surface over:

- blackboard
- text-theater snapshot
- workbench/route report
- corroboration

It is not a renderer and not a second truth plane.

Current value:

- it proves the repo already supports brokered read-side materialization
- that pattern can be mirrored for procurement receipts or comparison packets without inventing a second authority

### 6. Mirror And Capture Surfaces

The current environment lane already has multiple evidence surfaces:

- command-attached text-theater payloads
- `env_read(query='text_theater_view')`
- `env_read(query='text_theater_snapshot')`
- `env_read(query='contracts')`
- `env_read(query='live')`
- `capture_probe`
- `capture_supercam`
- `capture_frame_overview`

Relevant source anchors:

- `static/main.js:_envToolCarriesEnvironmentPayload`
- `static/main.js:_envStoreMirroredState`
- `static/main.js:_envBuildLiveSyncPayload`
- `static/main.js:_envBuildCameraLiveSyncPayload`

The important fact is:

- these already form a layered evidence stack
- the missing piece is procedural selection and return-path collation

## The Existing Procedure Skeleton

The repo already implies this order:

1. read `text_theater_embodiment`
2. use consult / blackboard query-work to justify the next read
3. read the snapshot
4. use `contracts`, `env_help`, and `env_report` for scoped interpretation
5. use mirror/captures when comparative corroboration is needed
6. open raw `shared_state` last

Current live corroboration on 2026-04-14:

- the live blackboard objective is `Surface Alignment Review`
- weather/rain and parity contamination are already entering through this query path
- so blackboard is already the proper orientation surface for the active weather-associated lane

That is already the shape of a scientific method loop:

- observe
- form local hypothesis
- choose next evidence
- acquire scoped corroboration
- compare surfaces
- only then widen to raw state

The failure has not been architectural absence. The failure has been incomplete operationalization.

## The Procurement Facilitator Extension

This is the smallest useful extension:

- blackboard remains planner
- `env_help` remains explainer
- existing MCP/environment tool lane remains executor
- returned artifacts come back as evidence, not as a second truth source

Clean formulation:

1. blackboard selects the next evidence actions
2. executor runs only allowlisted actions
3. results are returned as receipts/artifacts
4. blackboard session thread is updated with what was procured
5. interpretation stays with blackboard/text theater/env_report

This means the blackboard can facilitate procurement without becoming:

- a new runtime
- a new automation engine
- a second authority plane

## Candidate Artifact And Payload Classes

These are the artifact types that fit the current system best.

### A. Theater Evidence Packet

Purpose:

- package the immediate theater-first evidence for one query moment

Contents:

- attached text-theater frame or `text_theater_view`
- `text_theater_snapshot`
- freshness fields
- command sync token
- objective id
- anchor row ids

Why it fits:

- all fields already exist
- this just packages them as one auditable query packet

### B. Comparative Surface Packet

Purpose:

- compare text theater against browser-facing corroboration

Contents:

- text-theater render summary
- snapshot summary
- mirror contract excerpt
- optional capture id(s)
- discrepancy notes

Use when:

- parity contamination
- renderer disagreement
- scene/view mismatch

This is the most important next artifact for your stated methodology.

### C. Procurement Receipt

Purpose:

- record what the query thread asked to procure and what actually came back

Contents:

- requested tool
- normalized args
- artifact id or query result id
- sync token or timestamp
- freshness note
- success / blocked / stale / unavailable

This is the bridge between planner and executor.

### D. Mirror Freshness Packet

Purpose:

- explain whether a comparative read is old, partial, or trustworthy

Contents:

- mirror lag
- bundle mismatch
- cache advanced after command
- matched command sync
- relay tier
- synced at / updated ms

This should be first-class because the system already has freshness logic, but it is too easy to ignore.

### E. Discrepancy Ledger

Purpose:

- persistent row-like list of observed surface mismatches

Possible fields:

- surface_a
- surface_b
- compared_field
- observed_difference
- classification: truth / contract / transport / rendering / gating / freshness
- evidence refs
- status: open / mitigated / resolved / stale

This fits the current repair-list style and could later be rendered through blackboard or `env_report`.

### F. Reset Boundary Marker

Purpose:

- explicitly represent the user-owned refresh/reset boundary

Contents:

- operator reset acknowledged
- pre-reset evidence invalidated
- post-reset first read required

Why it matters:

- you already specified that resets/refreshes are operator-owned
- the system should stop silently acting as if a capture crossed that boundary

### G. Capture Provenance Bundle

Purpose:

- preserve enough metadata to know what a capture was actually proving

Contents:

- capture type
- focus target
- camera mode / preset
- world profile
- command sync token
- paired snapshot timestamp
- related query objective

This is a direct provenance use case.

### H. Surface Alignment Recipe Packet

Purpose:

- recipe output for parity/comparison tasks

This likely belongs as an `env_report` recipe later, not as a separate system.

Possible recipe:

- `surface_alignment_review`

Inputs:

- current blackboard session thread
- text-theater snapshot
- mirrored contracts
- optional latest capture

Outputs:

- alignment summary
- leading discrepancies
- recommended next capture/read
- evidence paths

### I. Weather/Field Observation Packet

Purpose:

- specialized comparative packet for weather/elemental fields

Contents:

- weather contract
- rendered field summary
- scene bounds / density / speed / direction
- text vs browser corroboration
- visual legibility state

This is not a new weather system. It is a procurement-aware observation packet over the one already being built.

### J. Control-Path Discrepancy Packet

Purpose:

- record cases where command results and runtime state disagree

Example already observed:

- `camera_preset` showed as unknown command in one path while camera state still changed through bus-side handling

This class of artifact is important because it catches control-surface inconsistencies, not just scene/render ones.

## What External Patterns Translate Cleanly

The following external ideas fit the repo well.

### 1. Blackboard / Opportunistic Control

Useful import:

- blackboard chooses among candidate next actions opportunistically based on current context

Translation here:

- `query_thread.next_reads` already plays this role
- the missing extension is allowlisted execution plus receipts

Relevant sources:

- Hayes-Roth style blackboard control lineage
- opportunistic-control literature

### 2. Active Perception

Useful import:

- perception is not passive; the agent chooses how to look and what evidence to gather

Translation here:

- camera framing
- focus changes
- capture selection
- comparative read ordering

This fits your insistence that the agent should actually look at the text theater, then decide what other surface to inspect.

### 3. Computational Steering

Useful import:

- observe a live process while changing parameters and gathering immediate feedback

Translation here:

- world profile / camera / builder edits / weather controls
- text-theater observation
- browser capture
- mirrored contracts
- controlled re-read loop

This fits your environment/debug/evaluation lane very closely.

### 4. Provenance Graphs

Useful import:

- every artifact should retain who/what/when/how it was produced

Translation here:

- capture provenance bundle
- procurement receipts
- discrepancy ledger evidence refs
- command sync token threading

This is how the system avoids becoming a swamp of unlabeled screenshots and stale reads.

### 5. Tool-Selection Models

Useful import:

- planner chooses whether to call a tool, which tool, with what args, and integrates the result

Translation here:

- blackboard `next_reads`
- outer executor
- returned receipts/artifacts
- blackboard/env_report interpretation

This is the correct way to think about procurement without handing blackboard raw execution authority.

## What Should Not Be Imported

The following patterns would cause drift here.

### 1. Blackboard As Autonomous Authority

Bad import:

- blackboard directly mutates runtime, decides truth, and executes arbitrary tools

Why bad:

- creates second control plane
- violates current doctrine

### 2. Hidden Semantic Tooling

Bad import:

- blackboard silently choosing semantically loaded captures or payloads without making that explicit

Why bad:

- undermines the visible worksheet role
- breaks the "reveal, do not insinuate" guardrail

### 3. New Parallel Registries

Bad import:

- a new procurement registry separate from `env_help`

Why bad:

- duplicates discoverability authority
- creates drift immediately

### 4. Free-Roaming Workflow Sprawl

Bad import:

- every surface inventing its own procurement loop

Why bad:

- you already have the blackboard/query substrate
- this should be one extension, not many local hacks

## The Strongest Combinatorials

These are the combinations most worth pursuing.

### Combination 1

Blackboard query thread + `env_help` playbooks + command-attached theater payloads

Result:

- fastest theater-first operator/agent loop

### Combination 2

Blackboard query thread + `capture_supercam` / `capture_probe` + mirror contracts

Result:

- comparative surface debugging lane

### Combination 3

Blackboard session thread + `env_report` + provenance-style evidence refs

Result:

- small auditable diagnosis packets instead of raw-state dumps

### Combination 4

Active perception logic + camera/focus/capture controls + text-theater-first gate

Result:

- an agent that looks on purpose instead of blindly reading mirrors

### Combination 5

Computational steering loop + existing environment controls + procurement receipts

Result:

- online parameter adjustment with structured corroboration

## Smallest Honest Next Extensions

### 1. Executable Query-Thread Allowlist

Allow only existing safe read/capture tools from blackboard `next_reads`:

- `env_read(query='text_theater_snapshot')`
- `env_read(query='text_theater_view')`
- `env_read(query='contracts')`
- `env_report(...)`
- `capture_probe`
- `capture_supercam`
- `capture_frame_overview`

Blackboard chooses. Outer executor runs. Receipt returns.

### 2. Procurement Receipts On Session Thread

Add a small receipt log under blackboard working state or report packet context:

- requested
- executed
- result id
- freshness
- status

### 3. Surface-Alignment First-Class Query Objective

This has already begun in source:

- `surface_alignment_review`

The next step is to make that objective produce a stable comparative evidence order and later an `env_report` recipe.

### 4. Discrepancy Ledger As Consumer, Not Authority

The current repair-list work should become a structured consumer artifact, not a side note in chat.

### 5. Reset Boundary Acknowledgement

Every comparative packet should explicitly know whether it belongs to pre-reset or post-reset evidence.

## Best One-Sentence Framing

The blackboard query substrate should become a visible procurement facilitator over existing read, mirror, report, and capture surfaces: it selects what evidence to gather next, the existing tool lane gathers it, and the returned artifacts remain session-threaded, provenance-aware, and subordinate to runtime truth.

## References

Local:

- `docs/TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md`
- `docs/ENVIRONMENT_HELP_SYSTEM_SPEC_2026-04-04.md`
- `docs/ENV_REPORT_SCHEMA_2026-04-11.md`
- `docs/DREAMER_PAN_RESPONSIBILITIES_MAP_2026-04-12.md`
- `static/main.js`
- `scripts/text_theater.py`
- `static/data/help/environment_command_registry.json`

External:

- W3C PROV Overview: https://www.w3.org/TR/prov-overview/
- ReAct: https://arxiv.org/abs/2210.03629
- Toolformer: https://arxiv.org/abs/2302.04761
- Revisiting Active Perception: https://link.springer.com/article/10.1007/s10514-017-9615-3
- Active Perception (Bajcsy 1988 report): https://repository.upenn.edu/handle/20.500.14332/7566
- Opportunistic control / blackboard lineage overview: https://www.sciencedirect.com/science/article/pii/0098135489850136
- Provenance analysis and visualization: https://doi.org/10.1016/j.procs.2017.05.216
