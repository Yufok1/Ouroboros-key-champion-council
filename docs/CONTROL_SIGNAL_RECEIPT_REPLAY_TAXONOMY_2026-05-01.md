# Control Signal Receipt Replay Taxonomy - 2026-05-01

## Status

Active taxonomy correction for the Hermes push.

Purpose: keep controls, runtime signals, logs, receipts, and replay packets from collapsing into one word.

This is the gap fix:

```text
start/stop/play -> actuator -> runtime state change -> signals/events/logs -> optional receipt -> review/replay
```

## Primitive Chain

Controls cause activity.

Activity emits signals.

Signals may be written as events or logs.

Events or logs may be converted into receipts by a provenance layer.

Receipts support review.

Replay packets rerun bounded inputs or scenarios under a declared method.

Review compares receipts, replay outputs, source state, and current runtime state.

## Negative Laws

`start`, `stop`, and `play` are controls.

A control is not a receipt.

A UI button is not evidence that the intended work happened.

A log line is not automatically a receipt.

An event is not automatically a receipt.

A receipt must be emitted by a receipt layer with declared fields, hashes, lineage, and review posture.

A replay packet is not the original event.

A replay packet is not source evidence.

A replay packet is a bounded rerun path.

## System Roles

### Convergence Engine

Convergence Engine runs off logs, signals, observations, and episodes as learning or inspection material.

It does not run on logs as its substrate.

It should not treat a start/stop control as proof of an organism event.

It should not treat a log as a receipt until Cascade Lattice or an equivalent provenance lane emits the receipt.

### Champion Council

Champion Council may expose controls, status, diagnostics, review surfaces, and import/export lanes.

It must label controls as controls.

It must label logs/events as signals or runtime records.

It must label receipts as receipts only after the provenance layer emits them.

### Cascade Lattice

Cascade Lattice is the receipt and provenance spine.

Its job is to transform bounded observations, events, decisions, and artifacts into reviewable receipts.

The hash proves the continuity of the recorded packet, not the moral or historical truth of the claim.

### Holo Deck

Holo Deck is the replay room.

It stages scenarios from replay packets and receipts.

It must say when a frame is replay, simulation, reenactment, or live state.

### Holo-Ghost

Holo-Ghost is the witness/capture lane.

It may capture bounded local signals and produce review cues.

It does not become authority by observing.

## Correct Mechanical Language

Use this:

```text
operator presses start
runtime begins work
runtime emits signals/events/logs
provenance lane emits receipt
review lane reads receipt
replay lane reruns bounded packet
human or Source HOLD decides what may be used
```

Do not use this:

```text
operator presses play
control click proves the work
logs are the substrate
replay proves the event
```

## Acceptance Test

A surface is aligned only when it can answer:

1. What is the control actuator?
2. What runtime state changed?
3. What signal or event was emitted?
4. What log or observation recorded it?
5. What receipt layer converted it into provenance?
6. What replay packet, if any, can rerun it?
7. What remains source evidence, and what remains only review material?
