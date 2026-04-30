# Shuttering Adrenaline Event Activation Ticket 2026-04-29

Repo: `D:\End-Game\champion_councl`
Status: active continuity ticket
Mode: concept hardening / next implementation slice

## Operator Thought

The operator asked for:

- a constant prompting system
- not token based
- something that activates the model "to see"
- a shuttering/adrenaline system
- later correction: synapse-esque, not Hopfield
- later correction: not exactly the same as context continuity
- possible fit: Rubik-style sequencer

## Bottom Line

The clean architecture is:

```text
observer surfaces -> salience gate -> sequencer -> shutter capture -> activation packet -> next model invocation
```

This is not continuous AI thinking.

It is continuous event observation plus bounded activation.

The model is still invoked turn by turn, but the world around the model can keep receipts, detect pressure, prepare a packet, and decide that the next invocation deserves a sharper view.

## What It Is Not

### Not Hopfield

Hopfield is useful as an analogy for content-addressed memory and attractor recall.

It is the wrong center for this system because the main problem is not "which stored pattern should the system settle into?"

The main problem is:

1. what changed
2. whether the change matters
3. which surface should be inspected next
4. what evidence should be frozen
5. what the human must authorize

That is not mainly attractor memory.
That is event gating and sequencing.

### Not Just Context Continuity

Continuity restores posture after reset.

This ticket is the layer before the next turn:

- it watches for change
- it detects pressure
- it captures evidence
- it builds a small activation packet
- it tells the next invocation what to inspect first

Continuity answers: "Where were we?"

Event activation answers: "What just fired, and why should the next mind look there?"

### Not A Hidden Runtime Mind

No hidden autonomous model loop is implied.

The continuous part can be cheap, deterministic, and auditable:

- file watchers
- log tails
- clipboard history
- Rerun/event streams
- browser/capture receipts
- PyPI/GitHub release checks
- auth/provenance checks
- blackboard deltas

The model is activated only when a packet is handed into a normal invocation boundary.

## Synapse Read

The better primitive is synapse/release-valve:

```text
pressure -> threshold -> firing -> route -> latch -> refractory/reset -> recharge
```

Mapping:

| Synapse term | System term |
|---|---|
| pressure | accumulated change, drift, risk, urgency, novelty |
| threshold | salience gate |
| firing | activation packet emission |
| route | sequencer selects target surface |
| latch | HOLD or shutter packet freezes evidence |
| refractory | debounce/cooldown so the system does not spam itself |
| recharge | watchers resume collecting deltas |

This matches the existing release-valve canon better than Hopfield.

## Rubik / Sequencer Read

Rubik remains useful, but only as a bounded permutation model.

It answers:

- which face should rotate into view next
- which layer may move without scrambling the truth spine
- which old surface stays locked while the inspection surface changes

The sequencer is not the authority.

The sequencer is the router between surfaces:

- continuity archive
- live runtime truth
- blackboard query thread
- output_state
- capture shutters
- HOLD
- Dreamer proposal lane
- docs/provenance lane
- organism mainframe visual layer

## Name Rehabilitation 2026-04-29

Correction from the operator:

- the prior deprecation of `adrenaline` and abstract continuity-side `shutter` was a frustration move, not final doctrine
- the system still needs those names because they carry real operator intuition
- the fix is not to ban the names
- the fix is to define the names tightly enough that they do not become a hidden autonomous runtime

Rehabilitated names:

| Name | Rehabilitated meaning | Boundary |
|---|---|---|
| `adrenaline` | salience pressure, urgency, novelty, risk, and readiness-to-inspect | never proof, never authority, never autonomous action |
| `shutter` | capture/attention gate that closes over a bounded surface and emits a receipt | does not freeze the whole runtime |
| `shuttering_adrenaline` | the combined cycle: pressure builds, threshold fires, shutter captures, packet routes next attention | must emit a visible packet |

The old deprecated object was:

```text
hidden continuity-side adrenaline/shutter runtime with vague authority
```

The rehabilitated object is:

```text
visible salience-and-capture sequencer over existing continuity, output_state, HOLD, and capture surfaces
```

Existing names still remain useful:

- `resume_focus`
- `surface_prime`
- `reset_boundary`
- `continuity_cue`
- `live_render_shutter`
- `structured_snapshot_shutter`
- `contact_body_shutter`
- `web_theater_shutter`

But they no longer replace `adrenaline` and `shutter`.

They are the implementation surfaces under the operator-facing names.

So the implementation-safe packet name is:

```text
event_activation_packet
```

The operator-facing system name may be:

```text
shuttering_adrenaline
```

The binding rule:

```text
adrenaline detects pressure -> shutter captures evidence -> event_activation_packet routes the next invocation
```

## Activation Packet Schema

Proposed minimal packet:

```json
{
  "packet_kind": "event_activation",
  "packet_id": "event_activation:2026-04-29T00:00:00Z:example",
  "observed_at": "2026-04-29T00:00:00Z",
  "trigger_kind": "operator_message | file_change | log_signal | auth_event | release_event | visual_capture | provenance_delta",
  "salience": {
    "score": 0.0,
    "reasons": [],
    "risk_flags": [],
    "novelty_flags": []
  },
  "source_refs": [],
  "changed_since": {
    "session_id": "",
    "commit": "",
    "timestamp": ""
  },
  "continuity_refs": {
    "continuity_packet": "",
    "resume_focus": {},
    "surface_prime": {},
    "reset_boundary": {}
  },
  "shutter_refs": {
    "live_render_shutter": null,
    "structured_snapshot_shutter": null,
    "contact_body_shutter": null,
    "web_theater_shutter": null
  },
  "blackboard_delta": {},
  "source_hold_required": false,
  "recommended_reads": [],
  "permitted_actions": ["inspect", "summarize", "propose_patch"],
  "prohibited_actions": ["deploy", "publish", "spend", "authenticate", "delete"],
  "refractory_until": ""
}
```

## How To Finish It

Smallest honest implementation sequence:

1. Create the packet schema as docs first.
2. Add a tiny local `event_activation` builder that accepts:
   - current operator message
   - current cwd
   - file/log refs
   - continuity restore output
3. Make it emit a packet only when salience passes a threshold.
4. Surface that packet in `output_state` as a child surface, next to `continuity_cue`.
5. Thread packet receipts into the blackboard query thread.
6. Only after that, add daemon/watch behavior.

No daemon first.

The schema and visible packet should exist before any continuous watcher grows teeth.

## Safety Boundary

The event activation system may:

- observe
- score
- capture
- prepare
- route attention
- recommend next reads
- request HOLD

It must not:

- mutate source silently
- publish packages
- push to GitHub
- run auth flows
- spend funds
- promote a Dreamer proposal into truth
- treat visibility as authority

Human Source HOLD remains the authority boundary.

## Continuity Run 2026-04-29

Two continuity restore passes were run.

Champion Council cwd:

- best session: `019dcde2-ebea-70a0-bcf5-f0ff7e23032a`
- session path: `C:\Users\Jeff Towers\.codex\sessions\2026\04\27\rollout-2026-04-27T03-41-34-019dcde2-ebea-70a0-bcf5-f0ff7e23032a.jsonl`
- score: `115.631`
- note: useful repo posture, but not the exact live turn

Convergence Engine cwd:

- best session: `019dda08-9fe5-7740-b53f-49eeaeb11201`
- session path: `C:\Users\Jeff Towers\.codex\sessions\2026\04\29\rollout-2026-04-29T12-18-11-019dda08-9fe5-7740-b53f-49eeaeb11201.jsonl`
- score: `164.0`
- open loop recovered: `oops sorry go over all those again then run continuity`
- recent pressure recovered: `i dont know how to finish it`

Current interpretation:

The operator is asking for the missing bridge between continuity and live reactivation.

That bridge should be a synapse-like event activation sequencer, not a Hopfield memory, not a hidden always-on model, and not abstract shutter mythology.

## Next Slice

Next code target:

- add `event_activation_packet` as a visible, serializable planning surface
- keep it proposal/capture only
- connect it to `continuity_cue`
- require Source HOLD before it can trigger writes, deployments, auth, publishing, or spending
