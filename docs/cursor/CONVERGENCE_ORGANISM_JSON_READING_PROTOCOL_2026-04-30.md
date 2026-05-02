# Convergence Organism JSON Reading Protocol - 2026-04-30

Audience: Cursor auditing Convergence Engine / Champion Council organism surfaces.

## Purpose

When the operator provides a Convergence Engine organism JSON blob, treat it as a live simulation record, not mythology and not proof of inner intent. Read it as a behavioral telemetry packet.

Classify first, then teach.

## Reading Order

1. Identity: `id`, `short_id`, `source`, `generation`, `age`, `rarity`, `personality_type`, `alignment`
2. Capability: `fitness`, `fitness_trend`, `brain_params`, `hidden_dim`, `has_language_head`, `epsilon`
3. Action policy: `dominant_action`, `action_distribution`, `behavioral_fingerprint`, `recent_actions`
4. Social state: `connections_count`, `alliance_id`, `alliance_reputation`, `confederation_tier`
5. Combat truth: `total_battles`, `battle_wins`, `battle_losses`, `battle_win_rate`, `highlander_kills`, `war_victories`
6. Language/mastery: `mastery_level`, `words_learned`, `mastery_vocab_limit`, `vocab_utilization`, `mastery_breadth`, `mastery_depth`
7. Labels: `strengths`, `weaknesses`, `alignment_scores`
8. Active seam: what the operator wants the organism to learn next

## Failure Grammar

Do not compress these:

- `compete` action dominance is not automatically violence.
- `aggression_ratio` reflects action-head tendency, not battle record by itself.
- `well_connected` does not mean allied; check `alliance_id`.
- `high_fitness` does not mean high mastery.
- stable fitness can mean equilibrium, plateau, or insufficient challenge; verify from context.
- `has_language_head=true` means language-capable surface exists, not that every prompt will be understood.
- repeated token output can be a decoding loop, vocabulary magnet, prompt mismatch, or low semantic grounding.

## Example Interpretation

For organism `f2606c85` / `f2606c85843d2607`:

- Classification: uncommon generation-0 warrior, age 55, True Neutral.
- State: live simulation source, fitness about `0.7559`, stable trend, no volatility.
- Policy: dominant action is `compete` at `73.6%`; recent action history is mostly action `2`, matching compete.
- Combat truth: no recorded battles, no wins/losses, no highlander kills, no war victories. This is competitive posture without proven bloodshed.
- Social truth: 20 connections and `well_connected`, but no alliance assigned.
- Language: language head exists, mastery level 2, 76 words learned, current mastery vocab limit 76.
- Risk: weakness says `too_aggressive`; action policy is narrow and competition-heavy.
- Teaching opportunity: channel compete into bounded contest, rule explanation, consent checks, and cooperative sparring rather than escalation.

## Operator-Facing Translation

Short version:

`f2606c85` is not a killer. It is a competitive uncommon warrior with stable fitness, real social reach, and low-to-mid language mastery. The right lesson is not "stop competing"; it is "compete inside rules, name the boundary, protect the commons, and explain before escalation."

## Teaching Prompt Pattern

Use short prompts because low/mastery organisms may loop under long abstract instruction.

```text
f2606c85, compete means test inside rules.
No battle. No harm. No outside command.
Answer five words only:
boundary:
contest:
protect:
share:
learn:
```

If it loops, reduce further:

```text
One word each.
Compete:
Safe:
Friend:
Rule:
Stop:
```

If it answers with a repeated magnet word, do not punish the organism. Treat the repeated word as a signal and ask for a relation:

```text
You repeated WORD.
WORD points to what?
Choose one:
rule
need
risk
path
```

## Audit Task For Cursor

When auditing organism chat, trace whether a user message actually reaches:

1. organism selection
2. tokenization
3. generation
4. vocabulary update
5. semantic association
6. reward or outcome update
7. causation/debug log

If one layer records the interaction but another does not, classify the drift as transport, contract, gating, rendering, or stale runtime state.

