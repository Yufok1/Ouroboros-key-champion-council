# Home Ops Organism Finder Architecture - 2026-05-01

## Status

Draft operating architecture.

Purpose: state the end-game loop plainly.

Champion Council is the home ops console.

Convergence Engine is the organism/finder swarm.

CRA state is the honor-bound equilibrium/coherence teaching and review posture.

Humans hold Source HOLD authority.

The operating formation is collaborative by default.

Working phrase:

`it_takes_a_planet`

Observer phrase:

`gentle_danger_observer`

## Core Read

The organisms are not decoration.

They are autonomous finders: small bounded agents that are good at assembling fragments, surfacing candidate fits, finding seams, routing evidence, and creating reusable operating packets.

Their job is not to replace human judgment. Their job is to keep looking, pairing, sorting, and proposing so the human team can see the next honest move.

## System Split

### Champion Council

Role: home command, audit, review, plug, display, and deployment console.

Responsibilities:

- run diagnostics
- inspect organism outputs
- manage model/tool slots
- receive cocoon/capsule artifacts
- show public/private dashboards
- enforce Source HOLD gates
- package reports, docs, and receipts
- decide what is safe to expose
- import Holo-Ghost and Holo Deck observation packets for review

### Convergence Engine

Role: organism swarm, finder field, simulation, learning, and assembly engine.

Responsibilities:

- evolve organisms
- let organisms search, pair, and compose
- run off logs, signals, observations, and episodes as learning material
- preserve interaction episodes
- export cocoons/capsules
- produce candidate artifacts
- track lineage and fitness
- detect seams, routes, and reusable patterns
- send outputs to Champion Council for review
- keep organism chat observe-only unless a teaching packet explicitly authorizes learning

### CRA State

Role: equilibrium/coherence posture for teaching and review.

Responsibilities:

- translate approved lessons into organism-readable teaching episodes
- keep uncertainty visible
- compare organism concepts against evidence and context
- route candidate toolwords into review instead of execution
- park packets when authority, data clearance, or coherence is missing
- select safe scientific/lab cases and convert them into organism method lessons

`friend_ollama` may be a local implementation surface for CRA state, but the state is the contract.

### CRA Scientific Lab Resource

Role: selective scientific-method teaching surface.

Responsibilities:

- provide public, simulated, de-identified, or approved cases for organism learning
- teach organisms to observe, hypothesize, predict, test, measure, revise, and preserve receipts
- route sensitive hospital, humanitarian, civic, or intervention cases to Source HOLD
- preserve uncertainty instead of smoothing results into false certainty

### Holo-Ghost

Role: witness surface.

Responsibilities:

- capture bounded local signals with consent-first defaults
- emit review cues and receipts
- avoid verdict language
- keep raw key capture, LLM, recording, API, and identity export gated

### Holo Deck

Role: replay and teaching room.

Responsibilities:

- stage receipt-backed scenarios
- convert observation packets into safe teaching cases
- let humans and organisms inspect the same bounded replay
- never treat replay as automatic authority

### Human Team

Role: authority, ethics, source, taste, and final decision.

Responsibilities:

- decide Source HOLD
- approve public release
- review sensitive outputs
- set boundaries
- choose mission priorities
- mark false positives
- protect people and communities

## Operating Loop

```text
observe -> organisms find -> Convergence exports -> Champion reviews -> human holds/approves -> package -> publish/use -> feed receipts back
```

Control loop:

```text
human/agent start-stop control -> runtime state change -> emitted signals/logs -> optional cascade receipt -> review/replay
```

Start, stop, play, and chat submit are controls.

Signals/logs are observation material.

Receipts are emitted by the provenance layer after the event.

Replay is a bounded rerun path, not the source event.

## Organism Finder Contract

Each organism/finder output should carry:

- organism id
- source inputs
- candidate fit
- confidence
- uncertainty
- why this surfaced now
- required human review
- risk flags
- next validation action
- export/cocoon id if preserved

## Home Deployment

The whole point is that this can be run from home:

- local Champion Council for operator review
- local Convergence Engine for organism generation and swarm work
- Hugging Face Spaces for public demo/test surfaces
- Hugging Face Hub model/dataset repos for portable artifacts
- GitHub/PyPI for reusable packages and public tooling

## Authority Boundary

Organisms can find.

Champion Council can route and display.

Humans authorize.

No organism output becomes:

- real-world instruction
- public claim
- deployment decision
- financial action
- civic commitment
- personal judgment

until Source HOLD is satisfied.

## Relation To Current Threads

`middle-passage` package:

- organisms/finders can help assemble safe research zones, bathymetry assumptions, voyage records, and GIS outputs
- Champion Council reviews evidence and release posture
- humans hold descendant/community/legal review boundaries

`civic_traffic_event_horizon`:

- organisms/finders can detect candidate flow seams, crowd risks, and route patterns
- Champion Council displays receipts and recommendations
- humans/public-safety authority decide action

`Atrai organism-mainframe`:

- organisms/finders become visible component workers
- animal/civic depiction makes roles readable
- mechanical primitive ids keep truth grounded

`honor_bound_equilibrium_coherence`:

- CRA state binds equilibrium and coherence into one teaching/review posture
- no white lies, no coercive outputs, no hidden sensitive-data use
- organism toolwords stay candidate packets until Source HOLD clears them

`cra_scientific_lab_resource`:

- CRA can teach organisms the scientific method indirectly through safe lesson packets
- organism lessons carry method stage, data class, uncertainty, and receipts
- sensitive lab cases stay parked until Source HOLD clears them

`gentle_danger_observer`:

- Holo-Ghost witnesses bounded danger signals
- Holo Deck stages safe replay and simulation
- Convergence organisms learn only from safe abstractions or approved teaching packets
- Champion Council reviews before public claims or real-world action

`binnes`:

- operator vocabulary
- unresolved operational definition
- preserve as context until defined, do not infer authority from it

## Next Build Slice

Create a small exchange schema:

`organism_finder_packet.v1`

Then add:

`organism_semantic_tool_packet.v1`

`cra_teaching_episode.v1`

`cra_lab_lesson_packet.v1`

`organism_scientific_method_episode.v1`

`gentle_danger_observation_packet.v1`

`organism_gentle_observer_lesson.v1`

Then wire:

1. Convergence Engine exports packet.
2. Champion Council imports packet.
3. Champion Council shows source/risk/HOLD status.
4. Human approves, rejects, or sends back for more finder work.
