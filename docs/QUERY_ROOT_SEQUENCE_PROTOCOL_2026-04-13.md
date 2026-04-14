# Query Root Sequence Protocol 2026-04-13

Repo: `F:\End-Game\champion_councl`

## Purpose

Capture the next protocol direction for Champion Council's theater-first query systems:

- treat each live inquiry as a rooted, finite, session-scoped sequence
- keep blackboard as planner and visible worksheet
- keep runtime truth singular
- make procurement, corroboration, and replay auditable
- persist the sequence as a queryable resource without creating a second authority plane

This is not a new system proposal.
It is a protocol for composing retained surfaces that already exist.

## Bottom Line

The correct unit is not:

- one isolated `env_read`
- one report
- one capture
- one bag document

The correct unit is:

- one **root sequence**

A root sequence starts from one visible objective over one live subject and accumulates:

- the visible theater read
- blackboard/query-work
- scoped reads
- procurement receipts
- corroborations
- captures
- reports
- operator actions
- resulting interpretations

All of that should be session-threaded and queryable as one finite chain.

The chain is not truth.
It is the **auditable history of how truth was consulted**.

## Existing Retained Surfaces

The repo already has the core pieces:

### 1. Runtime truth

- environment/workbench/runtime shared truth
- one authority plane

### 2. Blackboard query thread

Already carries:

- `objective_id`
- `objective_label`
- `visible_read`
- `anchor_row_ids`
- `help_lane`
- `next_reads`
- `raw_state_guardrail`

See:

- `static/main.js:_envBuildBlackboardState`
- `scripts/text_theater.py:_render_blackboard_section`
- `server.py:_env_report_build_session_thread`

### 3. Theater-first sequencing

Current doctrinal order:

1. `text_theater_embodiment`
2. consult / blackboard query-work
3. text theater snapshot
4. `contracts` or `env_report(...)`
5. captures / mirrors
6. raw state last

### 4. Procurement-capable read surfaces

- `env_read(...)`
- `env_help(...)`
- `env_report(...)`
- `capture_probe`
- `capture_supercam`
- frame/strip captures

### 5. Existing trace/persistence substrate

- workflow execution history with `execution_id`, `node_states`, `updated_ms`
- workflow trace args with `_trace_id`, `_workflow_execution_id`, `_workflow_node_id`
- FelixBag / file docs / checkpoints / search

The protocol should be built from these.

## Core Model

### Root Sequence

A root sequence is one session-scoped inquiry chain over one active objective and one active subject.

Minimal identity:

- `sequence_id`
- `session_id`
- `root_objective_id`
- `root_objective_label`
- `subject_key`
- `subject_kind`
- `subject_id`
- `opened_at_ms`
- `status`: `active | suspended | completed | abandoned`

### Sequence Segment

A root sequence is finite by default.
It contains one or more segments.

Each segment is a bounded pass over the same inquiry:

- observe
- plan
- procure
- compare
- decide

Reasons to start a new segment instead of infinitely appending:

- explicit operator reset/refresh boundary
- objective changed materially
- subject changed materially
- branch became its own avenue
- batch operation starts
- replay/retry pass starts

This keeps chains manageable and searchable.

## Packet Types

Each segment should be made of typed packets rather than freeform logs.

### 1. Observation Packet

What the system saw first.

Fields:

- `packet_type = observation`
- `surface = text_theater | embodiment | consult_blackboard`
- `snapshot_timestamp`
- `visible_read`
- `frame_ref`
- `focus`
- `camera`
- `notes`

### 2. Query Packet

What blackboard asked next.

Fields:

- `packet_type = query`
- `objective_id`
- `anchor_row_ids`
- `help_lane`
- `next_reads`
- `raw_state_guardrail`

### 3. Procurement Receipt

What tool was executed and what came back.

Fields:

- `packet_type = receipt`
- `tool`
- `normalized_args`
- `requested_at_ms`
- `completed_at_ms`
- `result_status`
- `artifact_ref`
- `freshness`
- `gate_state`
- `error`

This is the bridge between planner and executor.

### 4. Comparative Packet

How surfaces agreed or disagreed.

Fields:

- `packet_type = comparison`
- `surfaces`
- `agreement_points`
- `discrepancies`
- `classification`: `truth | contract | transport | rendering | gating | stale_state`
- `decision`

### 5. Action Packet

An operator or workflow action taken because of the prior evidence.

Fields:

- `packet_type = action`
- `tool`
- `args`
- `reason`
- `effect_surface`
- `command_sync_token`

### 6. Resolution Packet

Close a segment with an earned state.

Fields:

- `packet_type = resolution`
- `status`: `confirmed | partly_confirmed | not_supported | adjacent_but_different`
- `root_seam`
- `dependency_order`
- `next_step`

## Sequence Lifecycle

### Open

Open a new root sequence when all are true:

- new operator/user avenue of thought
- materially new objective
- materially new subject/focus
- not merely another receipt inside an existing thread

Open criteria should be explicit, not inferred loosely.

### Continue

Continue the current sequence when:

- objective is the same
- subject is the same
- current reads are still resolving the same seam
- the new packet is just another observation/procurement/comparison for that seam

### Branch

Create a child branch when:

- the same root objective splits into distinct sub-seams
- multiple procurement paths are being compared
- one branch is experimental and should not contaminate the main line

A branch is still subordinate to the same root sequence.

### Suspend

Suspend when:

- operator reset boundary
- waiting on refresh
- waiting on external capture
- objective still valid but not currently active

### Resume

Resume an old sequence only when at least one is true:

- explicit operator requested it
- same session and same subject/objective identity
- blackboard objective matches and the prior chain is the most recent active chain for that subject

Do not silently revive old chains across unrelated sessions.

## Session And Scope Rules

Session scoping should be primary.

Default rule:

- chains are session-local first
- archived second
- cross-session reuse only by explicit resume or narrow identity match

This prevents stale cognitive bleed from old investigations.

Recommended keys:

- `query_seq/session/<session_id>/<sequence_id>`
- `query_seq/archive/<date>/<sequence_id>`

## Surface Discipline

The sequence must preserve current doctrine:

- text theater is first object
- consult/blackboard is second object
- snapshot is structured corroboration
- report is scoped broker
- captures are comparative evidence
- raw shared state is last resort

No packet may invert that order without an explicit gate/override record.

## Relationship To FelixBag

FelixBag should persist sequences as searchable documents.

But it should not store every raw payload inline.

Correct pattern:

- store compact sequence docs
- store packet metadata
- store artifact refs
- checkpoint important milestones
- use bag/file search for retrieval

Suggested persisted doc shape:

- sequence header
- segment list
- packet summaries
- artifact refs
- classifications
- resolution notes

Artifact payloads can stay in:

- capture stores
- workflow history
- cached payload refs
- separate file docs when needed

Bag stores the chain index, not the whole universe.

## Relationship To Workflow / Batch Execution

This is where the protocol becomes operationally powerful.

A root sequence can become a replayable batch when:

- the objective is stable
- the subject is stable
- the action order is known
- the corroboration steps are known

Then the sequence can compile into:

- a workflow
- a traceable batch
- a replayable evaluation lane

Existing workflow fields already support useful parts of this:

- `execution_id`
- `node_states`
- `_trace_id`
- `_workflow_execution_id`
- `_workflow_node_id`

The protocol should reuse those identifiers rather than inventing a second trace language.

## Correlation And Grouping

Borrow one idea from the Convergence Engine cleanly:

- group related updates by one correlation/root id

In Champion Council terms:

- one `sequence_id`
- one `segment_id`
- many typed packets / receipts beneath them

This is the right grouping primitive for:

- batched pose work
- route eval passes
- parity investigations
- environmental comparative debugging
- future autonomous traversal batches

## Guardrails

### 1. No second authority plane

Sequences record consultation history.
They do not become truth.

### 2. No hidden reordering

If the gate requires:

1. theater
2. blackboard
3. snapshot

then receipts must show that order.

### 3. No unbounded chains

Use segments and explicit status changes.

### 4. No cross-session ghost reuse

Old chains do not silently reactivate.

### 5. No freeform logging as substitute

Everything important becomes a typed packet or receipt.

### 6. No bespoke renderer per chain

The sequence is data first.
Consumers render it.

## Recommended First Implementation Slices

### Slice 1. Sequence Header In Blackboard Working State

Add only enough to identify the active root sequence:

- `sequence_id`
- `segment_id`
- `session_id`
- `objective_id`
- `subject_key`
- `status`

### Slice 2. Procurement Receipts

When blackboard-prescribed reads/captures execute, return a small receipt packet to the same session thread.

### Slice 3. Comparative Packet

Add one small comparison packet format for theater/snapshot/report/capture discrepancies.

### Slice 4. FelixBag Persistence

Persist completed or suspended segments as compact docs.

### Slice 5. Workflow Compilation

Allow a mature root sequence to compile into a replayable batch/workflow.

## Optimal Read

The strongest design is:

- session-scoped
- finite by default
- root/segment/packet based
- blackboard-planned
- executor-receipted
- bag-archived
- workflow-compilable

That gives you:

- procedural rigor
- auditability
- resumability
- replayability
- semantic searchability
- no second truth plane

## External Pattern Notes

Two outside patterns reinforce this direction:

- blackboard control architectures are explicitly about opportunistic control over many candidate actions, not about flattening everything into one monolithic planner
- event-sourced systems keep immutable, ordered consultation history separate from current truth state

Champion Council should adopt only the useful parts:

- blackboard for control/selection
- receipts for ordered history
- runtime remains truth

## Conclusion

The next protocol step is not "more tools."

It is:

- turn one inquiry into one root sequence
- make the packets typed
- make the receipts explicit
- archive the sequence compactly
- compile mature sequences into replayable batches

That is the path from isolated query work
to a real rooted operational system.
