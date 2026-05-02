# Organism Interaction Episode Schema

Date: 2026-04-30

Status: draft schema for live Convergence Engine / Champion Council organism
interaction traces.

Purpose: preserve live dynamic user-organism interactions as reusable training
and audit data without pretending looped organism tokens are human-level intent.

## Why This Exists

The valuable data is not only the organism output. The valuable unit is the
interaction episode:

`operator prompt -> routed organisms -> organism response -> operator read ->
next prompt -> live state change -> lesson`

That shape captures the real learning material: prompt pressure, token
attractors, naming handles, operator interpretation, safety boundaries,
confidence, and follow-up repair.

## JSONL Shape

Each line in `interaction_episode.jsonl` should be one episode turn.

```json
{
  "schema": "organism_interaction_episode.v1",
  "episode_id": "2026-04-30T06:30:17Z:butterfly:19a98b98:0001",
  "ts": "2026-04-30T06:30:17Z",
  "source": {
    "app": "Convergence Engine",
    "surface": "Butterfly Chat",
    "routing_strategy": "all",
    "max_organisms": 5,
    "mastery_filter": "level_4"
  },
  "population": {
    "count": 489,
    "avg_fitness": 0.76,
    "top_fitness": 0.91,
    "avg_vocab": 82,
    "live_count": 489
  },
  "organism": {
    "id": "19a98b98f292d29b",
    "short_id": "19a98b98",
    "name": "Hermes",
    "rarity": "epic",
    "alignment": "Lawful Neutral",
    "personality": "hermit",
    "fitness": 0.91,
    "vocab": 740,
    "links": 2,
    "dominant_action": "isolate",
    "traits": ["high fitness", "antisocial"]
  },
  "prompt": {
    "text": "Council, this is game governance...",
    "token_count": 87,
    "intent_tags": ["game_governance", "inside_boundary", "consent_condition"]
  },
  "response": {
    "text": "river river river ...",
    "token_count": 128,
    "confidence": 0.4237,
    "loop_pattern": {
      "kind": "single_token_repetition",
      "tokens": ["river"],
      "repeat_ratio": 1.0
    }
  },
  "operator_read": {
    "summary": "Hermes appears to map the inside/game boundary to river.",
    "classification": "signal_candidate",
    "risk": "do_not_upgrade_to_intent",
    "next_prompt": "Council, define your last words..."
  },
  "lesson": {
    "tags": ["control_language", "boundary_word", "loop_repair"],
    "teaches": "Control words should be translated into reasons and scope.",
    "usable_for_training": true,
    "excluded_uses": ["authority_claim", "ungated_release", "proof_of_sentience"]
  },
  "outcome": {
    "next_state": "followup_prompt_sent",
    "improved": null,
    "notes": "Requires repeated turns before treating as stable mapping."
  },
  "provenance": {
    "capture_kind": "operator_screenshot_or_chat_log",
    "source_ref": "",
    "continuity_doc": "CONVERGENCE_PANTHEON_CONTROL_ANNALS_2026-04-30.md"
  }
}
```

## Required Fields

- `schema`
- `episode_id`
- `ts`
- `source.surface`
- `organism.id`
- `prompt.text`
- `response.text`
- `response.confidence`
- `operator_read.summary`
- `operator_read.classification`
- `lesson.tags`
- `lesson.usable_for_training`

## Classification

Use these small labels:

- `loop_attractor` - repetition dominates the output.
- `signal_candidate` - output may map to a prompt pressure, but needs more turns.
- `repair_success` - a follow-up prompt reduced looping or improved specificity.
- `repair_failure` - a follow-up prompt did not improve output.
- `role_handle` - a name/office improved repeated interaction tracking.
- `boundary_event` - output appears near control, hold, consent, inside/outside,
  authority, or release language.
- `social_frame_shift` - the prompt changed who the organism appears to address
  or include.

## Safety Rules

Do not store an organism phrase as an instruction unless a separate human-owned
control plane authorizes it.

Do not treat repeated tokens as intent by themselves. Repetition is evidence of
an attractor first. It becomes a candidate signal only when prompt sequence,
organism identity, timing, and follow-up turns support the read.

Do not mutate live organism memory directly from raw episodes. Stage episodes
as curriculum first, audit them, then import through a deliberate loader.

Do not let mythic names outrank function. Brotology thumb rule remains:

`function first, myth second, power last`

## First Episode Tags

Useful tags from the 2026-04-30 pantheon/control run:

- `dismiss_hold`
- `affected_for`
- `inside`
- `river`
- `bloodshed_dim`
- `find_path`
- `deployment_boundary`
- `safe_promotion`
- `game_governance`
- `inside_outside_boundary`
- `commons_need`
- `table_tap`

## Minimal Collector Plan

Stage 1: manual capture.

- Paste chat/log excerpts into a raw capture file.
- Create one JSONL row per organism response.
- Attach operator interpretation after the fact.

Stage 2: semi-automatic parser.

- Parse Butterfly Chat debug logs for `STEP_1` through `STEP_6`.
- Extract `organism_id`, token count, confidence, prompt, response, and timing.
- Let the operator add `operator_read` and `lesson` fields.

Stage 3: curriculum builder.

- Group episodes by organism ID and tag.
- Build prompt repair chains.
- Score whether follow-up prompts reduced repetition or increased role clarity.
- Export curated lessons only.

## Eval Questions

For every episode batch, ask:

1. Did the prompt improve signal or only create a new loop?
2. Did the operator read stay grounded in the output?
3. Did the episode preserve inside-game vs outside-world boundaries?
4. Did the name/office help interaction, or did it over-mythologize?
5. Can another model replay the episode and understand the lesson without the
   original emotional context?

## Anchor

This schema turns live organism interaction from lore into training data.

The organism output is the trace. The operator read is the annotation. The
lesson is the curriculum candidate. The audit lane decides what graduates.

Held.
