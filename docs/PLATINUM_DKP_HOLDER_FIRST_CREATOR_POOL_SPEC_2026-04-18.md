# Platinum DKP Holder-First Creator-Pool Spec

Date: 2026-04-18

## Purpose

Operationalize a simple, adjustable creator-pool system where:

- trades generate intake
- holding is the stronger incentive
- verified contribution can compete for extra capture
- stronger lanes can protect weaker lanes without changing the top-level doctrine

This is a policy/spec document first.
It is not yet a runtime automation mandate.

## Read Together With

- `docs/MEME_COIN_HOLDER_FIRST_CONTINUITY_EVAL_2026-04-18.md`
- `docs/REACTIVE_COIN_STREAM_TRAJECTORY_2026-04-18.md`
- `docs/PUMP_NOSTR_CONTROL_PLANE_BRIEF_2026-04-17.md`
- `docs/PUMP_BAG_HOLDER_OPERATIONS_MVP_2026-04-17.md`

## One-Sentence Definition

`Trade flow fills the creator pool; a holder-first raid-split system routes that pool into body, raid, shield, and forge ledgers on a fixed macro charter and adjustable micro rules.`

## Non-Negotiable Rules

1. Trades are intake, not the primary beneficiary class.
2. Holding must beat churn over time.
3. Raw activity is not rewardable by default.
4. Reward useful state transitions, not motion alone.
5. Keep the top-level split simple enough to explain in one screen.
6. Preserve creator/operator/build capacity instead of starving the system.
7. Use strong lanes to protect weak lanes through explicit policy, not ad hoc emotion.
8. Do not frame the system publicly as a yield promise or managed-profit machine.

## Core Entities

### 1. Intake

Any value routed into the system from:

- creator-fee receipts
- raid-entry or premium-action fees
- workflow execution fees
- sponsorship or external revenue
- future approved revenue surfaces

### 2. Epoch

The minimum accounting window.

Recommended first version:

- continuous intake accumulation
- daily snapshot for qualification and scoring
- weekly settlement for distributions
- monthly policy review

### 3. Qualified Holder

A wallet that passes:

- wallet binding
- minimum balance threshold
- minimum hold-age threshold
- anti-snipe window
- anti-sybil / anti-farm checks

### 4. Raid Window

A bounded competition window where verified contributors earn additional capture from the same pool.

### 5. Recovery Candidate

A previously qualified holder/operator/builder who:

- had real prior standing
- experienced a real wipeout or loss event
- passes cooldown and integrity checks

## The Minimal Denominational Architecture

All intake is first represented as one macro pool and then split into four immutable top-level ledgers.

Use `10,000 bps` as the accounting base so the public doctrine stays stable while sub-rules can evolve.

## The Four Macro Ledgers

### 1. `Body`

Purpose:

- passive capture for qualified holders
- make holding worth more than churn
- keep the body funded even if users are not specialists

This is the main holder-benefit lane.

### 2. `Raid`

Purpose:

- reward verified contribution
- create competitive specialist emergence
- operationalize `Platinum DKP` instead of raw spam jackpots

This is the active competition lane.

### 3. `Shield`

Purpose:

- reserve floor
- recovery lane
- anti-collapse buffer

This is the protection lane.

### 4. `Forge`

Purpose:

- creator operations
- moderation and operator execution
- builder incentives
- experimental/novelty budget

This is the steering and production lane.

## Recommended Holder-First Baseline Split

The first honest preset should be:

- `Body` = 45%
- `Raid` = 20%
- `Shield` = 20%
- `Forge` = 15%

Why this split:

- holder body stays clearly first
- active contributors still have a meaningful competitive lane
- reserve/recovery is large enough to matter
- creator/operator/build capacity remains funded

This is a starting charter, not sacred law.
The important thing is that the four-ledger model stays stable even if percentages are tuned later.

## Why Four Ledgers Instead Of More

Four is the smallest stable set that preserves intention:

- `Body` answers "who benefits from holding?"
- `Raid` answers "how do active specialists win more?"
- `Shield` answers "how do strong systems protect weak ones?"
- `Forge` answers "who keeps the machine running and evolving?"

Do **not** add a fifth macro ledger until one of these demonstrably cannot carry its purpose.

## Sub-Buckets Inside Each Ledger

Sub-buckets may change without changing the macro charter.

That is the whole point of the design.

### `Body` sub-buckets

- base holder share
- long-hold multiplier share
- loyalty / integrity share

### `Raid` sub-buckets

- common raid distribution
- jackpot distribution
- carry-over pot

### `Shield` sub-buckets

- reserve floor
- recovery / resurrection buffer
- emergency repair buffer

### `Forge` sub-buckets

- creator operations
- moderator/operator execution
- builder grants or bounties
- experimental / novelty probes

## Holder Qualification

The holder system must bias toward static, real bags rather than last-second stuffing.

### Minimum rules

- minimum qualifying balance
- average balance over the snapshot window, not only end-of-window balance
- minimum hold age before full eligibility
- cooldown for newly entered wallets
- exclusion or penalty for obvious sybil clusters

### Recommended holder weight

Use a whale-softened weight such as:

`holder_weight = sqrt(avg_balance_units) * age_multiplier * integrity_multiplier`

Why:

- `sqrt(...)` reduces whale domination
- `age_multiplier` rewards actual hold duration
- `integrity_multiplier` lets the system discount bad actors

### Example age tiers

- `< 7d` = `0.60`
- `7-30d` = `1.00`
- `30-90d` = `1.20`
- `90d+` = `1.40`

These are tunable, but the structure should remain.

## Body Distribution

The `Body` ledger pays qualified holders on the weekly settlement clock.

### Suggested payout rule

Each qualified holder receives:

`body_payout = Body_epoch_pool * holder_weight / sum(holder_weight)`

### Guardrails

- cap per-wallet share if concentration becomes dangerous
- apply anti-snipe reductions for newly qualified wallets
- unclaimed amounts roll forward into the next `Body` epoch

## Raid / PDKP Distribution

The raid lane is where competition lives.
It must be competitive, but not reward churn or fake motion.

## Raid Roles

Recommended role families:

- holder
- builder
- operator
- scout
- amplifier
- stabilizer

Each role should score different actions.
Do not force all contribution through one leaderboard.

## Net Raid Score

Use:

`net_raid_score = verified_contribution_points + negentropy_bonus - entropy_debt`

Where:

- `verified_contribution_points` = action value that can be evidenced
- `negentropy_bonus` = stabilization, truth-telling, recovery, anti-chaos work
- `entropy_debt` = spam, churn-farming, panic amplification, wash behavior, sybil tactics

## Raid Bucket Split

Within the `Raid` ledger, start with:

- `common raid pool` = 60%
- `jackpot pool` = 25%
- `carry pool` = 15%

### Common raid pool

Distributed pro rata among all positive-score participants:

`raid_common_payout = common_raid_pool * participant_net_score / sum(positive_net_scores)`

### Jackpot pool

Paid to the top verified contributors by rank or category, with caps.

Do not make it:

- winner takes all
- pure "most clicks wins"
- pure trade-volume contest

### Carry pool

Rolls into the next raid window to preserve anticipation and deepen seasons.

## Recovery / Resurrection Lane

This lives inside `Shield`.

The purpose is not refunding reckless loss.
The purpose is controlled re-entry for proven participants.

### Qualification

- prior qualified-holder or contributor status
- evidence of real previous standing
- real drawdown / wipeout threshold
- cooldown elapsed
- no recent exploit flags

### Recovery asset form

Prefer:

- locked re-entry allocation
- vested credits
- non-transferable participation credits

Avoid:

- instant liquid refund
- uncapped repeated rescue

### First recovery rule

One claim per season/window unless explicitly overridden by creator policy.

## Shield Logic

The `Shield` ledger is where "the strong protect the weak" becomes concrete.

## Minimum reserve doctrine

Maintain a reserve floor measured in settlement epochs.

Recommended first target:

- `reserve_cover_target = 4 epochs`

Meaning:

- keep enough in `Shield` to cover four normal settlement cycles before freer spending is allowed

## Overflow rule

If `Shield` is above target:

- overflow may route back into `Body` or `Raid`

Recommended first overflow:

- 50% to `Body`
- 50% to `Raid`

## Under-target rule

If `Shield` is below target:

- reduce discretionary `Forge` release first
- then reduce `Raid jackpot` before reducing `Body`

That preserves:

- the passive holder body
- system survivability

before protecting spectacle or experimentation.

## Forge Logic

`Forge` is the lane that keeps the project alive enough to deserve holder loyalty.

Without it, the system collapses into inert dividend talk.

## Recommended internal split

Inside `Forge`, start with:

- creator operations = 40%
- moderator/operator execution = 25%
- builder grants/bounties = 25%
- experimental probes = 10%

This gives the creator room to steer while still funding the rest of the machine.

## Interval Design

Keep the clocks simple.

### Continuous

- intake accumulation
- event logging
- score accumulation

### Daily

- qualification snapshot
- holder-weight update
- raid-score checkpoint

### Weekly

- macro settlement
- `Body` payout
- `Raid` payout
- `Forge` release
- `Shield` review

### Monthly

- percentage review
- policy update
- role-score retuning
- rescue/recovery policy review

## Runtime Bridge To `Technolit Reactor`

The runtime already carries useful read-model seeds for this spec.

### Existing useful fields

- `creator_rewards_unclaimed_sol`
- `creator_distribution_receiver_count`
- `creator_distribution_edit_remaining`
- `top10_holder_pct`
- `dev_holding_pct`
- `snipers_pct`
- `insiders_pct`
- `fresh_buys_count`
- `fresh_holding_pct`
- `recent_side_bias`
- `flow_posture`
- `distribution_posture`
- `burn_gate`

### Immediate interpretation

- `creator_rewards_unclaimed_sol` = current intake backlog / available source material
- `fresh_holding_pct` = early retention strength
- `fresh_buys_count` + `recent_side_bias` = flow pressure
- `top10_holder_pct` / `snipers_pct` / `insiders_pct` = concentration and extraction risk
- `creator_distribution_receiver_count` = how distributed the current creator-side routing already is

### Proposed later derived fields

Do not add these to runtime blindly first.
But this is the correct future read model:

- `body_pool_balance`
- `raid_pool_balance`
- `shield_pool_balance`
- `forge_pool_balance`
- `qualified_holder_count`
- `holder_capture_rate`
- `raid_participant_count`
- `jackpot_carry_balance`
- `reserve_cover_epochs`
- `recovery_buffer_balance`
- `entropy_pressure`
- `negentropy_credit`
- `last_epoch_settlement_ts`

## Public Explanation Language

The clean public line is:

`Trade activity feeds the pool. Holding and verified contribution decide how the pool gets captured.`

Avoid saying:

- guaranteed rewards
- passive yield
- price support
- profit sharing

Prefer saying:

- creator-directed distribution policy
- holder-first routing
- contribution-based seasonal capture
- reserve and recovery protections

## First Implementation Order

1. Ship the policy/spec surface first.
2. Define the holder qualification snapshot contract.
3. Define raid role buckets and score evidence rules.
4. Add a manual settlement ledger before any automation.
5. Only then add Reactor-facing derived fields.
6. Only after that consider public stream dramatization of the payouts.

## What Is Deliberately Deferred

- single-token access/fork gate
- direct on-chain automation
- continuous auto-payouts
- price-support or treasury theatrics
- complex novelty lanes beyond the four-ledger model

## Bottom Line

This spec preserves the strongest recovered idea in a stable form:

- trades feed the machine
- holders are empowered
- active specialists can compete
- reserve protects the organism
- creator and operators remain funded

And it does it with one simple macro charter that can be tuned later without losing the original intention.
