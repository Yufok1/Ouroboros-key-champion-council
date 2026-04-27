# Hold Door Comedia Reactor Spec 2026-04-19

## Goal

Create the smallest honest reactive performer for the Techlit stream:

- one mounted body
- one meme-coin reactor
- two spoken lexemes: `hold`, `door`
- reactor decides the emotion
- text theater shows the words before real audio is wired

## Current Contract

`hold_door_comedia_packet` is derived from `technolit_reactor` and carried in `output_state`.

It currently decides:

- `stage`
  - `watch`
  - `burn_hungry`
  - `buy_surge`
  - `bleeding`
  - `red_candle`
- `mood`
- `reaction`
- `spam_level`
- `caption_line`
- `caption_tokens`
- `tempo_bpm`
- `utterance_gap_ms`
- `trajectory_trigger`

## Interpretation Rule

This lane is deliberately simple:

- if trajectory turns greener and buy pressure rises, Hold Door hypes
- if burn hunger is present, Hold Door leans forward and chatters
- if sell pressure rises, Hold Door gets hurt
- if the candle really red-candles, Hold Door starts dying emotionally

## Audio Philosophy

Sound is treated as a byproduct of elemental interaction, not a separate sovereign system.

So the sequencing order is:

1. reactor field changes
2. `hold_door_comedia_packet` updates
3. body reaction/text caption update
4. later audio uses the same packet

## Missing Next Slices

1. live market/trade ingest instead of seeded reactor-only updates
2. automatic `character_play_reaction` dispatch from packet transitions
3. text-theater word materialization around the body
4. viseme/lip-sync binding from `audio_sequence`
5. optional web-theater export of the same words/HUD
