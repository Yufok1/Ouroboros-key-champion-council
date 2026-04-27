# Settlement Snapshot Provenance Spine 2026-04-19

## Purpose

Distill the honest next proof architecture for high-value Technolit settlement.

Target:

- snapshot-based settlement
- CASCADE-backed provenance
- replayable receipts
- optional IPFS archive transport
- no second truth plane

This document is source-guided against the currently implemented repo seams.

## Current Truth

### 1. CASCADE is already the provenance authority

Confirmed locally:

- `cascade_chain` manages merkle-linked provenance chains
- `cascade_record` manages tape/log style receipts
- `verify_integrity` and `verify_hash` already exist as integrity tools

Meaning:

- the repo does not need a brand-new provenance system
- it needs a disciplined place to attach provenance to settlement snapshots

### 2. The coin lane already has a live policy packet

Confirmed locally:

- `output_state.technolit_distribution_packet`
- server-side normalization
- text-theater rendering of that packet

Meaning:

- live routing posture already exists
- settlement proof should dock to that packet rather than inventing a parallel coin brain

### 3. Snapshot surfaces exist, but the generic settlement snapshot contract does not

Confirmed locally:

- `branch_snapshot` exists as a live browser/runtime command
- text-theater snapshot exists
- continuity packet and paired-state report already recover archived/live posture

Not yet implemented:

- `holder_snapshot_packet`
- `settlement_epoch_packet`
- `release_packet`
- generic `shutter_packet` fields such as `shutter_close`, `shutter_open`, `latched_hold_id`, `resume_mode`

Meaning:

- there is real snapshot substrate
- there is not yet a formal settlement-proof spine

### 4. IPFS is present only as a narrow transport seam

Confirmed locally:

- `ipfs://` URL resolution exists in `static/main.js`
- a browser-side `ipfsPin` message flow exists for voice-note capture

Not yet confirmed locally:

- generalized IPFS pinning for settlement bundles
- IPFS as the archive transport for report/receipt packages
- chain-to-IPFS linkage for settlement epochs

Meaning:

- IPFS is not the current truth source
- it is a candidate archive/distribution transport once the snapshot and provenance contracts are real

## Boundary Rules

### 1. Equilibrium is not the ledger

`equilibrium` should arbitrate readiness, strain, watch posture, and settlement pressure.

It should not directly determine payout truth.

Clean role:

- signal that a settlement lane is stable enough to freeze
- carry settlement pressure / posture
- help select when to snapshot

### 2. CASCADE is the proof spine, not the decision-maker

CASCADE should record:

- snapshot creation
- weighting inputs
- epoch ledger result
- operator approval
- delivery release
- post-release verification

CASCADE should not:

- compute holder weight policy by itself
- replace the settlement ledger
- replace text theater or output state as the live readable surface

### 3. IPFS is archive transport, not authority

If reconnected, IPFS should hold immutable bundles:

- frozen snapshot bundle
- receipt bundle
- Hold Door delivery bundle
- visualization bundle

IPFS should not:

- replace the live runtime
- replace CASCADE merkle identity
- become the only source of current truth

### 4. Provenance must be selective, not sprayed everywhere

Do not wire provenance as ambient noise on every surface.

Target only authority-bearing seams:

- settlement snapshot creation
- ledger computation
- hold approval / release gate
- epoch finalization
- delivery receipt publication
- archive export

## Recommended Spine

### Layer 1. Live Runtime

Current authorities:

- `output_state`
- `equilibrium`
- `technolit_measure`
- `technolit_distribution_packet`
- text-theater snapshot / blackboard / consult

Purpose:

- read the current live coin posture
- decide whether the system is stable enough to freeze an epoch

### Layer 2. Freeze / Snapshot

Needed next packet:

- `holder_snapshot_packet`

Minimum fields:

- `epoch_id`
- `snapshot_ts`
- `coin_id`
- `policy_id`
- `source_revision`
- `creator_fee_balance`
- `macro_split_bps`
- `qualification_window`
- `wallet_rows`
- `integrity_notes`
- `operator_note`

This is the first settlement authority object.

### Layer 3. Ledger

Needed next packet:

- `settlement_epoch_packet`

Minimum fields:

- `epoch_id`
- `snapshot_hash`
- `weight_formula_id`
- `lane_allocations`
- `qualified_wallet_count`
- `reserve_state`
- `exclusions`
- `manual_adjustments`
- `operator_approval_state`
- `release_mode`

This is the money truth.

### Layer 4. Provenance

Use CASCADE here:

1. `cascade_chain(create_chain)` for the epoch
2. `cascade_chain(add_record)` for:
   - snapshot packet
   - ledger packet
   - approval packet
   - release packet
3. `cascade_chain(finalize)` to get the merkle root
4. `cascade_chain(verify)` before release

Also use `cascade_record` in parallel:

- `tape_write` for raw epoch events
- `log_kleene` for compact operational facts
- `log_interpretive` for human-readable settlement commentary

This gives:

- replayable tape
- merkle-authenticated chain
- compact operator-facing logs

### Layer 5. Archive / Distribution

If IPFS is reconnected, pin the immutable bundle after finalization:

- snapshot packet JSON
- settlement packet JSON
- merkle root / verification result
- human-readable Hold Door report asset
- optional visualization assets

Then link that archive back into CASCADE:

- `cascade_chain(link_external)` with the IPFS root / CID

That gives:

- CASCADE = proof identity
- IPFS = distribution/archive transport

### Layer 6. Delivery

Public-facing artifacts:

- `Technolit Certificate`
- `Hold Door Report`

The report should be rendered from the frozen settlement packet, not from live drift.

Meaning:

- cute culture layer stays universal
- individualized report stays deterministic and auditable

## Minimal Next Build Order

1. `holder_snapshot_packet`
2. `settlement_epoch_packet`
3. `approval_release_packet`
4. CASCADE epoch-chain helper around those packets
5. optional IPFS bundle export + `link_external`
6. `Hold Door Report` renderer over the frozen packet

## What This Should Not Become

- not a second authority plane over live runtime
- not provenance spam on every harmless UI mutation
- not IPFS-first truth
- not equilibrium deciding payouts by itself
- not delivery assets generated from unfrozen live state

## Clean Thesis

For billion-scale thinking, the right shape is:

- live runtime decides when the posture is stable enough
- snapshot freezes the economic state
- ledger computes the epoch truth
- CASCADE proves the chain of custody
- IPFS optionally carries the immutable bundle
- Hold Door delivers the human-readable receipt

That is the honest high-value spine already latent in this repo.
