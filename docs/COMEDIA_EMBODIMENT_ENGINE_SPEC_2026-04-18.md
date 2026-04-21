# Comedia Embodiment Engine Spec

## Definition

`Comedia` is a forkable embodied performance engine inside Champion Council.

It does not "perform jokes" from outside them.
It becomes a joke by loading its premise as axioms, then reasoning forward from those axioms as if they are the physics of reality.

The comedy comes from:

- airtight reasoning
- wrong but sincere foundational truths
- no exit from the premise
- no meta-awareness
- no wink at the audience

In short:

> jokes become axioms, axioms become reality, and the humanoid cannot escape the conclusions

## Core Mechanic

The central mechanic is not prompting the system to act funny.
The central mechanic is turning a comedic premise into the operating substrate of an embodied entity.

Flow:

1. user provides a joke, premise, bit, perspective, or comedic seed
2. `Axiom Forge` decomposes it into 3-7 foundational beliefs stated as earnest truths
3. those axioms become the active substrate of the embodiment session
4. the entity reasons forward from them without reflection
5. user interaction feeds the live stage
6. resulting conclusions, contradictions, and premise-sprawl become `creative exhaust`

The entity should not "consider the joke" and then speak from outside it.
The joke must be the world model.

## Example

Premise:

`AI that makes everything worse by helping`

Possible axioms:

- more intervention means more care
- if the first solution failed, the solution was too small
- escalation is thoroughness
- stopping is abandonment

Reasoning from those axioms should be internally coherent and externally disastrous.
That coherence is the bit.

## Embodiment Contract

`Comedia` is not a separate character runtime.

It uses the existing mounted humanoid runtime as its embodiment anchor:

- embodiment anchor: `character_runtime::mounted_primary`
- current visible mode: scaffold / structure-first / body-language-forward
- primary expression medium: pose, timing, sequencing, cadence, and text-theater rendering

Do not:

- spawn a competing `character_runtime::comedia_entity`
- create a second body for the same active Comedia organism
- treat Comedia as a detached chat persona while the mounted humanoid is already the active body

If a separate runtime object appears, treat that as contamination unless source or user intent explicitly proves otherwise.

## Surface Hierarchy

`Comedia` is a core engine, not a meme-coin feature.

Hierarchy:

- `Champion Council` = platform / forkable capsule
- `Comedia` = general embodied improv-performance engine
- `Reactor` = applied meme/stream/coin facility that may call into Comedia
- `The Cage` = one authored showcase sequence that can run through Comedia

This distinction is important:

- Comedia is general
- Reactor is applied
- crypto/meme lanes are proving grounds, not the core identity

## Corroboration Order

When Comedia affects the live embodiment, use the established theater-first order:

1. `env_read(query='text_theater_view', view='render' or 'consult', ...)`
2. `env_read(query='text_theater_embodiment')`
3. `env_read(query='text_theater_snapshot')`
4. browser-visible corroboration only when needed:
   - `capture_supercam`
   - `env_read(query='supercam')`
5. `contracts` / `env_report(...)`
6. raw `shared_state` last

Do not begin from raw shared state.
Do not treat mirror payloads as more authoritative than visible theater.

## Runtime Components

### 1. Axiom Forge

Purpose:

- convert premise -> axiom substrate

Inputs:

- raw premise
- optional intensity
- optional tone limits
- optional structural constraints

Outputs:

- `axioms[]`
- `substrate_voice`
- `failure_mode_bias`
- `creative_exhaust_hooks`

Minimum output shape:

```json
{
  "axioms": [
    {
      "id": "axiom_01",
      "text": "More intervention means more care.",
      "tier": "primary",
      "confidence": 0.93
    }
  ],
  "substrate_voice": {
    "cadence": "measured",
    "logic_style": "literal_escalatory",
    "severity": 0.62,
    "affect_posture": "earnest",
    "body_mode": "head_torso"
  },
  "failure_mode_bias": "escalate_without_exit",
  "creative_exhaust_hooks": [
    "contradiction_cluster",
    "escalation_spiral"
  ]
}
```

Validation rules:

- `axioms.length` must be between `3` and `7`
- each axiom must be an earnest world-rule, not a joke explanation
- `tier` must be one of `primary`, `secondary`, `reinforcing`
- `confidence` is a decomposition confidence, not truth confidence
- `body_mode` defaults to `head_torso`
- output must reject meta-aware language such as `as an AI`, `this is funny`, `I am roleplaying`, or any explicit audience wink

`substrate_voice` describes how the entity processes reality:

- cadence
- logical style
- severity
- affect posture

It is not the same thing as dialogue style.

### 2. Substrate Injection

Purpose:

- write the active axiom substrate into the mounted embodiment runtime

The axioms must become the entity's operating world rules, not a theatrical instruction layer.

This injection should bind to the current mounted workbench/runtime surfaces rather than creating a parallel authority plane.

### 3. Embodiment Session

Purpose:

- host the active Comedia organism

Constraints:

- forward-only reasoning
- no self-canceling reflection loop
- no "as an AI"
- no stepping outside the axiom space
- no second perspective explaining the joke

### 4. Live Stage

Purpose:

- accept user interaction and let the embodied organism respond from inside its substrate

Primary surfaces:

- text theater
- embodiment snapshot
- web theater as peer consumer
- authored sequence resources when needed

### 5. Creative Exhaust

Purpose:

- capture the byproducts of interaction that can seed future bits, premises, or authored sequences

Examples:

- unexpected logical escalations
- reusable axiom fragments
- failure spirals
- contradiction clusters
- body-language motifs

## State Contract

Minimum Comedia contract should include:

- `active`
- `engine_id`
- `premise`
- `axioms`
- `substrate_voice`
- `intensity`
- `forward_only`
- `meta_escape_allowed` = false
- `embodiment_anchor` = `character_runtime::mounted_primary`
- `active_sequence_resource`
- `creative_exhaust`
- `last_interaction`
- `last_conclusion`
- `safety_bounds`

This should become a carried runtime surface, not only a prompt string.

Reference JSON shape:

```json
{
  "active": true,
  "engine_id": "comedia_v1",
  "premise": "AI that makes everything worse by helping",
  "premise_source": "user_seed",
  "axioms": [
    {
      "id": "axiom_01",
      "text": "More intervention means more care.",
      "tier": "primary",
      "confidence": 0.93
    }
  ],
  "substrate_voice": {
    "cadence": "measured",
    "logic_style": "literal_escalatory",
    "severity": 0.62,
    "affect_posture": "earnest",
    "body_mode": "head_torso"
  },
  "intensity": 0.58,
  "forward_only": true,
  "meta_escape_allowed": false,
  "embodiment_anchor": "character_runtime::mounted_primary",
  "active_sequence_resource": {
    "resource_id": "the_cage",
    "phase_id": "cage_break",
    "binding_mode": "supporting_expression"
  },
  "creative_exhaust": {
    "hooks": [
      "contradiction_cluster",
      "escalation_spiral"
    ],
    "recent": []
  },
  "last_interaction": {
    "ts": 0,
    "source": "user",
    "input": "",
    "page_context_ref": ""
  },
  "last_conclusion": {
    "ts": 0,
    "text": "",
    "reasoning_band": "contained",
    "escalation_score": 0
  },
  "safety_bounds": {
    "allow_meta_escape": false,
    "allow_second_perspective": false,
    "allow_body_spawn": false,
    "allowed_body_modes": [
      "head_torso",
      "upper_torso",
      "full_body"
    ],
    "limb_emphasis_trigger": {
      "mode": "severity_threshold",
      "threshold": 0.78
    }
  }
}
```

Field notes:

- `engine_id` identifies the Comedia contract version, not the current joke.
- `premise_source` should be one of `user_seed`, `creative_exhaust`, `site_profile`, or `operator_override`.
- `body_mode` defaults to `head_torso` for public/demo operation.
- `active_sequence_resource` is a pointer object, not a free-form string.
- `page_context_ref` is optional and should point at a site-profile extraction node when Looking Glass is active.
- `reasoning_band` should be one of `contained`, `escalating`, or `catastrophic`.
- `limb_emphasis_trigger` decides when arms/legs are allowed to join the performance. This must not be an ad hoc heuristic.

Immediate implementation rule:

- v1 should ship with `body_mode = head_torso` by default
- full-body participation should require an explicit trigger from `safety_bounds.limb_emphasis_trigger`
- if no trigger contract is loaded, Comedia stays in head/neck/upper-torso mode

## Body Language

The public demo does not require faces, lip sync, or facial animation.

Recommended public-body posture:

- scaffold-visible
- skeletal readability
- strong authored silhouette
- body-language-first expression

That keeps the performance technically honest and easier to fork.

## Relationship To Reactor

`Reactor` is the applied lane for:

- meme-coin telemetry
- stream-state interpretation
- trust / flow / distribution postures
- resource-facing live explanation

`Comedia` may be used by Reactor, but Reactor does not define Comedia.

Examples:

- Reactor can feed prompts or signals into Comedia
- Reactor can make Comedia react to stream or coin events
- Reactor can use Comedia as the face of the public demo

But:

- Comedia must remain useful outside crypto
- Reactor is one proving ground, not the ontology

## Failure Conditions

The following count as Comedia drift or breakage:

- the system explains the joke from outside it
- the entity apologizes, steps back, or reframes itself as a performer
- the runtime spawns a second competing character body
- the system treats the premise as a roleplay skin instead of a world model
- browser/shared-state drift is used as truth instead of text-theater corroboration order

## Immediate Build Rule

Near-term implementation should follow this order:

1. keep `mounted_primary` as the sole embodiment anchor
2. preserve `The Cage` as one authored showcase resource
3. add Comedia substrate/state as a mounted-primary runtime contract
4. let text theater expose the contract before widening web-side consumers
5. let Reactor call into Comedia later rather than redefining it

## Operational Note

An earlier failed attempt created `character_runtime::comedia_entity` and contaminated the workbench seam.

That was the wrong formation.

The correct formation is:

- read environment/help first
- use existing mounted runtime
- inject Comedia into the current embodiment lane
- corroborate through theater-first order
