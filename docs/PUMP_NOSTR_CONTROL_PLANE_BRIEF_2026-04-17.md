# Pump / Nostr Control Plane Brief

Date: 2026-04-17

## Purpose

Define the highest-leverage, most realistic bridge between:

- `pump.fun` as the external coin / creator / fee / audience surface
- `Champion Council` as the orchestration runtime
- `Nostr` as the social, identity, reputation, and coordination substrate

This brief is intentionally narrow:

- no fake "we control pump itself" framing
- no invented second authority plane
- no "yield machine" product fiction
- no custody-first architecture

The goal is a creator-operated control plane that can sit as close as possible to Pump's public and creator-facing surfaces while remaining realistic, composable, and legally safer than a managed-finance product.

## Current Truth

### 1. The current `champion_councl` web runtime has a Nostr shell, not a full Nostr backend

What exists now in this repo:

- `static/main.js` has a full Community tab surface with:
  - chat
  - DMs
  - marketplace
  - badges
  - polls
  - DVM jobs
  - voice rooms / live chat
- `static/vscode-shim.js` intercepts those commands in standalone browser mode

What does **not** exist now in this repo:

- real relay-backed Nostr publishing / fetching in standalone web mode
- real DM persistence
- real room / presence persistence
- real gist auth / backing in standalone web mode

In standalone web mode, most of those commands are currently:

- routed to placeholder MCP calls
- returned as empty defaults
- or acknowledged as local no-ops

This means the social surfaces are visibly present, but the standalone substrate underneath them is still partial.

### 2. The old VS Code extension branch contains the real Nostr substrate

The abandoned extension branch at:

- `F:\End-Game\vscode-extension`

already contains the real implementation family:

- relay-backed Nostr service
- DMs
- profile and privacy state
- marketplace document publishing
- gist-backed versioning
- reputation tracking
- DID / VC helpers
- badges
- polls
- NIP-90 jobs
- NIP-53 room model / signaling

That branch is the source-of-truth substrate for real Nostr behavior.

### 3. Pump should be treated as an external execution surface, not an internal subsystem

Pump is not ours.

We should not frame the system as:

- "rewriting Pump"
- "controlling pool math"
- "replacing Pump's token mechanics"

We should frame it as:

- observing Pump
- binding creator identity to external Pump surfaces
- coordinating social / policy / workflow automation around Pump
- optionally routing creator-owned downstream actions after creator fees arrive in creator-controlled wallets

## What Pump Gives Us

Treat these as the external observable / operable surfaces:

- creator identity
- coin identity
- coin metadata / links / public narrative
- chat / comments / community attention
- creator-fee destination and fee-policy context
- public market activity and holder-facing visibility

Do **not** assume there is an official, supported Pump CLI unless verified from official Pump documentation.

At the time of this brief:

- official Pump docs clearly expose terms, fees, and product articles
- a public official CLI/API surface was not confirmed from official docs during this pass

So the design should assume:

- public web / creator surfaces
- documented fees / terms
- public chain data
- user-operated workflows around those surfaces

and **not** require a privileged Pump-native automation API to be useful.

## What Nostr Gives Us

Nostr is the clean substrate for:

- creator identity
- audience/community presence
- signed announcements
- reputation accumulation
- room coordination
- marketplace publication
- automation job dispatch

This is why the best bridge is not "Pump replacement".
It is:

- `Pump external state`
- `Nostr social/control state`
- `Champion Council orchestration state`

with clear seams between them.

## The Right Product Framing

The best framing is:

- `Pump coin` = market-facing object
- `Nostr layer` = social / trust / coordination mirror
- `Champion Council` = creator operations engine

That means Champion Council should become:

- the spider on the web
- not the web itself

The web is the external market + social field.
The spider is the runtime that:

- watches
- scores
- announces
- gates
- coordinates
- sequences

without pretending to own the substrate it rides on.

## Zaps Are Not Swaps

This is a critical boundary.

Nostr zaps are:

- Lightning payments
- social payments
- signaling / reward / access primitives

They are **not** token swaps.

What zaps are good for:

- tipping
- access gating
- room admission
- workflow execution fees
- spam deterrence
- reputation reinforcement
- creator support

What zaps are not good for:

- pretending to be a token exchange rail
- serving as a disguised swap engine
- representing meme-coin settlement logic

So the clean interpretation is:

- use zaps as a `payment / access / signal rail`
- do not market them as coin swap mechanics

## Highest-Leverage Build Target

Build a `Pump Creator Control Plane`.

This is the golden-goose cut because it aligns with systems already present in the extension substrate and avoids the highest-risk financial-product behavior.

### Core functions

1. `creator identity binding`

- bind a Pump creator / coin identity to:
  - Nostr pubkey
  - DID
  - profile metadata
  - public policy record

2. `creator policy publishing`

- publish signed policy statements for:
  - fee usage
  - treasury posture
  - buyback stance
  - creator commitments
  - disclosure and update history

3. `reputation and trust`

- score creator behavior over time
- issue badges / verifiable reputation artifacts
- track delivery consistency, disclosure cadence, moderation quality, and community trust

4. `community coordination`

- coin-specific rooms
- coin-specific DM clusters / operator channels
- voice rooms
- live announcements
- task routing for moderators / operators / creators

5. `workflow marketplace / jobs`

- let creators publish reusable ops workflows
- let communities request services / automations
- use NIP-90 style job semantics where appropriate

6. `payment and access rail`

- zaps for:
  - room admission
  - premium alerts
  - workflow execution charges
  - creator support
  - anti-spam commitment

## What To Port First

Do not port everything from the old extension at once.

Port the smallest complete family that turns the current standalone Community tab from ornamental to real.

### Phase 1: Real social substrate in standalone runtime

Port or reconstitute these behaviors from the old extension substrate:

- identity
- profile
- privacy settings
- DM store / fetch / send
- room list / create / join / leave
- room live chat
- room presence

This is the minimum real backend social layer.

### Phase 2: Marketplace and creator publication

Bring over:

- publish document
- fetch workflows / listings
- gist-backed source/version metadata
- reputation-informed ranking

This gives the social layer productive purpose.

### Phase 3: Pump creator binding

Add new runtime tools / records for:

- creator pubkey <-> coin binding
- coin policy records
- disclosure feed
- creator ops rooms

### Phase 4: Payment/access enforcement

Use zaps as:

- paywall
- admission ticket
- anti-spam toll
- workflow fee

not as token settlement.

## Recommended MCP Tool Family

The first realistic Pump-oriented MCP tools should be:

- `pump_creator_bind`
  - bind Pump coin / creator metadata to Nostr identity and local records

- `pump_creator_policy_put`
  - store or publish signed creator policy records

- `pump_creator_policy_get`
  - read current creator policy and disclosure state

- `pump_creator_signal_log`
  - append creator announcements / status / events

- `pump_room_open`
  - create coin-specific room metadata in the Nostr social layer

- `pump_room_policy_sync`
  - project creator policy into room metadata / access policy

- `pump_reputation_score`
  - score creator / operator behavior from disclosed actions and observed signals

- `pump_reputation_attest`
  - issue badge / VC / attestation artifacts from that score

- `pump_workflow_publish`
  - publish creator or mod workflows to the marketplace

- `pump_workflow_execute`
  - run operational automations against the creator control plane

- `pump_zap_gate_check`
  - verify whether a zap-based access or fee rule is satisfied

- `pump_zap_gate_issue`
  - generate the policy / invoice requirements for entry or execution

## Legal-Safer Zone

The safer operating band is:

- identity
- disclosure
- reputation
- moderation
- rooms
- workflow automation
- payments for access or service

The more dangerous band is:

- managed expectations of profit
- pooled funds
- yield promises
- price-support promises
- custody
- "we run the token's economics for holders" framing

This brief assumes the former, not the latter.

## Specific Repo Consequence

For this repo, the practical implication is:

- the Community tab should stop pretending to be fully backed when in standalone mode
- the old extension's real Nostr substrate should be treated as the donor branch
- the Pump-oriented layer should be a new MCP/runtime family on top of that substrate
- zaps should be payment/access infrastructure, not pseudo-swaps

## Recommended Immediate Sequence

1. Port the minimal real Nostr social substrate into standalone runtime:
   - DMs
   - rooms
   - room presence
   - room live chat
   - privacy/profile persistence

2. Restore real marketplace publication/import semantics:
   - publish
   - fetch
   - gist metadata
   - ranking

3. Add Pump creator binding and creator policy tools.

4. Add zap-gated access and workflow execution.

5. Only after that, consider richer Pump-facing observability or automation adapters.

## Final Position

The right move is not:

- "build a meme coin backend"

The right move is:

- build a Nostr-backed creator operating system that can sit tightly around Pump's existing creator and community surfaces

If we do that correctly, Champion Council becomes:

- the creator console
- the policy ledger
- the moderation and room engine
- the workflow marketplace
- the trust and disclosure layer

and Pump remains:

- the external coin and market surface we orbit and operationalize around.
