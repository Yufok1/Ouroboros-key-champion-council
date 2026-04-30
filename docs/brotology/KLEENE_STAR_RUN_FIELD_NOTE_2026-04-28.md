# Kleene St★r Run Field Note

Date: 2026-04-28

## Term

Technical label: `Kleene-star run`

Operator slang: `Kleene st★r run`

Short label: `st★r run`

## Meaning

A Kleene st★r run is an open repetition runtime with an explicit stop condition.

It is appropriate for loops that keep stepping through chat, game play, simulation, training, serving, observation, or theater polling until one of these release conditions happens:

- user quit
- game over
- episode budget exhausted
- health gate fails
- operator stop
- configured runtime timeout
- explicit save/export checkpoint

## Why The Name Works

In formal language terms, Kleene star means "zero or more repetitions." In operator language, the st★r mark says "repeatable, alive, watchable, and bounded by a stop rule."

This avoids treating a long-running organism/game/server as a mistake. The question is not whether it repeats. The question is whether it has a real guard, visible state, and a clean exit.

## Usage Rule

Use `Kleene-star run` in formal docs and interfaces.

Use `Kleene st★r run` in Brotology/operator notes where tone matters.

Do not use the term to hide runaway behavior. If there is no stop rule, no observability, or no checkpoint boundary, it is not a Kleene st★r run.

## Examples

- `chiefco.py --mode chat` is a Kleene st★r run because it repeats on user turns until quit.
- `chiefco.py --mode serve` is a Kleene st★r run because it serves until operator stop.
- `chiefco.py --mode sphere --headless --misses 1` is a bounded st★r run because game-over is the stop condition.
- `chiefco.py --mode gym --episodes 10` is a finite st★r run because episode budget is the stop condition.

## Operator Contract

Before starting a Kleene st★r run, state:

- the command
- the stop condition
- whether it trains or only evaluates
- where evidence will appear
- whether artifacts will be saved

After it stops, report:

- runtime outcome
- steps/frames/episodes
- reward or loss evidence
- any save/export location
- whether the next run should widen the budget
