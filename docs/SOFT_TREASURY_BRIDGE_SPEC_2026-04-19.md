# Soft Treasury Bridge Spec 2026-04-19

## Purpose

Define the first honest money bridge between the Technolit meme-coin surface and SOL settlement without promising direct redemption.

The bridge is:

- attention and routing on Pump
- treasury accumulation in SOL
- snapshot-based settlement
- operator-controlled release
- proof-first receipts

## Thesis

The meme coin is the speculation and coordination shell.

SOL is the treasury settlement rail.

The bridge between them is not a hard exchange promise. It is a policy-and-proof system:

- creator fees collect into treasury posture
- epochs freeze on cadence
- settlement is computed from frozen state
- release happens only after review and proof

## Runtime Packet

`output_state.technolit_treasury_bridge_packet`

Core fields:

- `bridge_id = soft_treasury_bridge_v1`
- `settlement_asset = SOL`
- `treasury_mode = creator_fee_treasury`
- `treasury_wallet_mode = single_treasury_sink | multiwallet_router`
- `settlement_style = snapshot_then_manual_release`
- `redemption_mode = none`
- `reference_ratio_mode = informational_only`
- `reserve_floor_mode = shield_epoch_floor`
- `stage`
- `next_contract`
- `source_policy_id`
- `epoch_clock`
- `public_line`
- `summary`
- `signals`
- `issues`

## Stages

### `treasury_seed_only`

The bridge exists conceptually, but routing/settlement is not yet ready.

### `treasury_routing_pending`

Creator-fee routing is not yet locked into the treasury sink.

### `treasury_manual_ready`

Treasury routing is locked and the next honest move is a holder snapshot.

### `treasury_receipt_ready`

Agent receipt surfaces are available and the bridge can feed proof-bearing settlement artifacts.

## What It Must Not Claim

- not direct redemption
- not guaranteed price support
- not shareholder rights
- not automatic yield
- not irreversible automation without review

## Next Contracts

1. `holder_snapshot_packet`
2. `settlement_epoch_packet`
3. `approval_release_packet`
4. `Hold Door Report`

## Public Line

`Pump carries attention. SOL carries settlement. Snapshot the epoch, verify the proof spine, then release manually.`
