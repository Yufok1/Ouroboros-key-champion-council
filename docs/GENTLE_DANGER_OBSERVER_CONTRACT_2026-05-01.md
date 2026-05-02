# Gentle Danger Observer Contract - 2026-05-01

## Status

Draft operating contract.

Purpose: align Holo-Ghost, Holo Deck, Champion Council, Convergence Engine, and Cascade Lattice around one gentle observer grammar.

The observer exists to notice danger before danger becomes irreversible.

It does not exist to accuse, coerce, punish, score people in secret, or turn uncertainty into authority.

## Core Truth

The structure observes danger.

Danger means:

- pressure rising
- time narrowing
- uncertainty being hidden
- evidence drifting
- a crowd, tool, model, or workflow becoming unstable
- an organism learning the wrong lesson
- a human being pushed into action without enough receipts
- an authority boundary being crossed without Source HOLD

The observer must stay gentle because the subject may already be under pressure.

Gentle does not mean weak.

Gentle means:

- consent-first
- local-first
- redacted by default
- no verdict language
- no hidden surveillance
- no coercive scoring
- no false certainty
- receipts before claims
- review before action
- one step at a time

## System Roles

### Holo-Ghost

Role: witness.

Responsibilities:

- observe bounded local interaction signals
- redact sensitive fields by default
- produce review cues, not verdicts
- emit provenance receipts
- keep uncertainty visible

Forbidden:

- hidden monitoring
- raw key capture by default
- automatic identity export
- guilt, intent, or protected-trait inference

### Holo Deck

Role: room.

Responsibilities:

- replay scenarios backed by receipts
- stage safe simulations
- make danger visible without creating new danger
- let humans and organisms inspect the same bounded case
- teach from sanitized examples

Forbidden:

- pretending replay is the original event
- exposing raw private data to organisms
- turning a scenario into an automatic real-world instruction

### Cascade Lattice

Role: receipt chain.

Responsibilities:

- preserve the path from signal to packet
- hash observations, reviews, and decisions
- keep observation, interpretation, and authority separate
- provide HOLD points before action leaves the lab

Forbidden:

- presenting a hash as proof of truth
- collapsing evidence continuity into moral certainty

### Convergence Engine

Role: organism school and finder swarm.

Responsibilities:

- let organisms practice observation, hypothesis, test, revision, and receipt
- expose organism learning as packets
- distinguish chat, lesson, reward, and memory mutation
- export candidate packets to Champion Council

Forbidden:

- treating chat as harmless when it mutates organism memory
- teaching organisms from raw sensitive data
- converting confidence into authority
- training on dangerous or uncleared cases without Source HOLD

## Control / Signal / Receipt Boundary

Controls are actuators.

`start`, `stop`, `play`, chat submit, and replay launch change or request runtime state.

They are not receipts.

Runtime activity emits signals, events, and logs.

Those records are observation material.

Cascade Lattice or an equivalent provenance lane may convert bounded records into receipts.

Holo Deck replay consumes receipts or replay packets, but replay is not the original event.

Convergence Engine organisms may learn from approved logs, signals, observations, and episodes. They do not treat logs as the runtime substrate or as proof.

### Champion Council

Role: court and review theater.

Responsibilities:

- display observation packets
- show data class, risk, uncertainty, lineage, and Source HOLD state
- distinguish simulated, public, de-identified, sensitive, and unknown cases
- route packets to human review
- approve, reject, park, or return for more finder work

Forbidden:

- publishing unreviewed organism claims
- treating a model slot as an authority plane
- hiding blocked or unknown status

## Transfusive Interaction

Mechanical phrase:

`transfusive_interaction`

Meaning:

One system carries pressure, signal, evidence, or burden across a boundary so the other system can keep functioning.

Safe path:

```text
private pressure -> bounded signal -> observed/logged event -> receipt -> reviewed artifact -> safe external action
```

Unsafe path:

```text
private pressure -> raw exposure -> unreviewed model inference -> public action
```

The gentle observer externalizes danger without externalizing harm.

## Observation Packet

```json
{
  "schema": "gentle_danger_observation_packet.v1",
  "packet_id": "",
  "source_system": "holo_ghost | holo_deck | convergence_engine | champion_council | cascade_lattice",
  "case_id": "",
  "capture_mode": "local | replay | simulation | aggregate | imported",
  "data_classification": "public | simulated | aggregate | deidentified | limited_dataset | PHI | sensitive | unknown",
  "consent_posture": "not_applicable | explicit | inherited | unknown | denied",
  "observation": {
    "summary": "",
    "metrics": {},
    "redactions": [],
    "time_window": ""
  },
  "danger": {
    "type": "pressure | timing | instability | evidence_drift | hidden_uncertainty | authority_crossing | learning_risk | unknown",
    "severity": "low | watch | urgent | hold | reject",
    "reason": "",
    "uncertainty": []
  },
  "interpretation": {
    "claim": "",
    "truth_posture": "confirmed | inferred | unknown | blocked",
    "confidence": 0.0,
    "limits": []
  },
  "source_hold": {
    "required": true,
    "status": "not_requested | pending | approved | rejected",
    "authority": ""
  },
  "receipts": {
    "previous_hash": "",
    "event_hash": "",
    "review_hash": "",
    "cascade_receipt": ""
  },
  "status": "observed | lesson_candidate | review_required | approved | rejected | parked"
}
```

## Convergence Teaching Packet

```json
{
  "schema": "organism_gentle_observer_lesson.v1",
  "lesson_id": "",
  "source_packet_id": "",
  "organism_id": "",
  "cohort_id": "",
  "teaching_mode": "observe_only | vocabulary | scientific_method | replay | reward_gated",
  "memory_mutation": "none | proposed | applied",
  "method_stage": "observe | hypothesize | predict | test | measure | revise | receipt",
  "safe_abstraction": "",
  "forbidden_inferences": [],
  "organism_response_hash": "",
  "uncertainty_preserved": [],
  "coherence_score": 0.0,
  "review_status": "unreviewed | accepted | rejected | parked"
}
```

## Default Gates

The default stance for every observer surface:

1. Observe locally.
2. Redact sensitive fields.
3. Label the data class.
4. Preserve uncertainty.
5. Emit a receipt.
6. Park if Source HOLD is missing.
7. Teach organisms only through safe abstractions.
8. Require human review before public claims or real-world action.

## Acceptance Test

A gentle observer lane is acceptable only when it can answer:

1. What was observed?
2. What was not observed?
3. What was redacted?
4. What danger type is being named?
5. What remains unknown?
6. What claim is being made, if any?
7. What receipt proves the observation path?
8. Did the case mutate organism memory?
9. What Source HOLD boundary applies?
10. Who can authorize action?

If any answer is missing, the packet stays parked.
