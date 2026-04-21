# Techlit Pump Tokenized Agent Setup 2026-04-19

## Goal

Arm the smallest real Pump buyback/burn lane for Techlit so Hold Door can sit on top of a live hourly furnace instead of a parked one.

## Successor Posture

The previous `Technolit` mint cannot be upgraded post-launch into Pump tokenized-agent mode.

So this setup now exists for the `Techlit` successor launch only.

The local runtime remains useful as the rehearsal surface:

- `technolit_distribution_packet.stage = agent_burn_ready`
- `technolit_distribution_packet.tokenized_agent_mode = hourly_buyback_burn_parked`
- `technolit_treasury_bridge_packet.stage = burn_support_ready`
- `hold_door_comedia_packet.stage = bleeding`
- `hold_door_comedia_packet.caption_line = hold... door... hold. door.`

So the local side is ready.
What remains is using these assets on a fresh coin created with tokenized-agent enabled from minute zero.

## Pump Side

Use the current official Pump tokenized-agent posture:

- tokenized-agent mode automates hourly buyback and burn
- the creator sets the fixed percentage of controlled assets used for buyback
- supported receipt assets are currently `SOL`, `USDC`, `USDT`, and `USD1`
- unused agent-deposit assets can be claimed by the creator

Official references:

- `https://pump.fun/docs/tokenized-agent-disclaimer`
- `https://pump.fun/create`

## Recommended Easy-Mode Settings

Start conservative:

- tokenized agent: `ON`
- buyback percentage: `10%` to start
- initial seed: small `SOL` only
- external top-up posture: optional
- public framing: buyback/burn support only

This keeps the lane honest and easy to monitor before escalating it.

## Upload Artifact

Use this file as the first markdown artifact:

- [skills.md](/D:/End-Game/champion_councl/docs/pump/techlit/skills.md)

It matches current Techlit posture:

- buyback/burn only
- no payout promises
- Hold Door in the report/culture lane

## Creator Checklist

1. Start a fresh Pump coin creation flow for `Techlit`.
2. Confirm `Tokenized agent` is enabled before finishing creation.
3. Set the initial buyback percentage to `10%`.
4. Upload the local [skills.md](/D:/End-Game/champion_councl/docs/pump/techlit/skills.md).
5. Finish creation only after those settings are visibly on.
6. Once the new coin shows `Agent settings`, seed it with a tiny `0.01 SOL` test.
7. Watch the first hourly burn pulse before increasing any support.

## Important Boundary

This repo can prepare the posture and the upload artifact.

The old `Technolit` mint is no longer the target for this setup. This file now exists to keep the `Techlit` launch from repeating the same creation-time mistake.
