# Convergence Engine Gentle Observer Patch Plan - 2026-05-01

## Status

Patch plan, not yet applied to `D:\End-Game\Convergence_Engine`.

Reason: Convergence Engine is outside the current writable workspace and already has substantial uncommitted local edits. The first safe step is to name the exact patch seam and avoid mixing this contract into unrelated dirty work.

## Verified Seam

Convergence Engine already has live organism chat surfaces:

- `causation_web_ui.py` exposes `/api/butterfly/chat`.
- `causation_web_ui.py` exposes `/api/organism/<organism_id>/chat`.
- `cra_cli.py` can call Butterfly Chat and direct organism chat.
- `reality_simulator/language/butterfly_chat.py` stores chat interactions as learning experiences.
- `butterfly_chat.py` can learn words from chat as `chat_heard` and `chat_used`.

Therefore, organism chat is not inherently read-only.

It is an organism-memory mutation lane unless explicitly configured otherwise.

## Target Contract

Add a gentle observer gate to every CRA-to-organism teaching path:

```text
chat request -> start actuator -> interaction_context -> Source HOLD/data class check -> observe_only or learn mode -> organism response/runtime events -> logs/signals -> optional receipt emission -> review packet
```

The request/start surface is a control actuator.

The organism response and runtime activity emit signals/events.

Logs are learning and inspection material.

Receipts are emitted after the event by the provenance lane.

Convergence Engine runs off logs, signals, observations, and episodes as material. It does not run on logs as its substrate, and a play/start/stop button is not a receipt.

## First Code Slice

### 1. Add request fields

Targets:

- `causation_web_ui.py` `/api/butterfly/chat`
- `causation_web_ui.py` `/api/organism/<organism_id>/chat`
- `cra_cli.py` `butterfly-chat`
- `cra_cli.py` `organism-chat`

Fields:

```json
{
  "learn": false,
  "teaching_mode": "observe_only",
  "data_classification": "public | simulated | aggregate | deidentified | sensitive | unknown",
  "source_hold_status": "not_required | pending | approved | rejected",
  "method_stage": "observe | hypothesize | predict | test | measure | revise | receipt",
  "danger_type": "none | pressure | timing | instability | evidence_drift | hidden_uncertainty | authority_crossing | learning_risk",
  "review_required": true
}
```

Default must be:

```json
{
  "learn": false,
  "teaching_mode": "observe_only",
  "data_classification": "unknown",
  "source_hold_status": "pending",
  "review_required": true
}
```

### 2. Gate memory mutation

Target:

- `reality_simulator/language/butterfly_chat.py`

Current mutation points:

- `_store_chat_experience`
- `_learn_words_from_chat`
- `_trigger_chat_training`

Required behavior:

- If `learn=false`, respond but do not store experience, learn words, reward atoms, or trigger training.
- If `learn=true`, require `data_classification` in `public | simulated | aggregate | deidentified`.
- If `source_hold_status` is not `approved` for sensitive or unknown data, park the lesson.

### 3. Emit gentle observer runtime event and receipt

Target:

- event emission in `butterfly_chat.py`
- security receipt path in `causation_web_ui.py`

Boundary:

- `/api/butterfly/chat` is a request/control actuator.
- `/api/organism/<organism_id>/chat` is a request/control actuator.
- chat logs/signals are learning material and review material.
- the gentle observer receipt is emitted after response/event handling, not before it.

Receipt fields:

- `memory_mutation`
- `teaching_mode`
- `data_classification`
- `source_hold_status`
- `method_stage`
- `danger_type`
- `uncertainty`
- `review_required`

### 4. Update CRA prompt/state

Target:

- CRA prompt block in `causation_web_ui.py`
- CRA CLI help text in `cra_cli.py`

Rule:

CRA may engage organism chat as a societal organism surface, but must state whether the call is:

- observe only
- lesson proposal
- approved teaching
- parked

CRA must not imply it can commune safely when the call mutates memory without explicit teaching posture.

## Acceptance Test

1. `/api/butterfly/chat` defaults to observe-only.
2. `/api/organism/<id>/chat` defaults to observe-only.
3. A response can be generated without storing experience.
4. A learning call emits runtime signals/logs before any receipt is recorded.
5. A learning call records `organism_gentle_observer_lesson.v1`.
6. Sensitive or unknown data with no Source HOLD parks instead of training.
7. CRA response names memory mutation status.
8. Champion Council can import/display the packet as review-required.
9. No start/stop/play control is described as a receipt.
