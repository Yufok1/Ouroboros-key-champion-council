# Pump Bag-Holder Operations MVP

Date: 2026-04-17

## Goal

Define the smallest useful `bag-holder club` product that:

- is aligned to Pump creator / coin operations
- uses Champion Council's existing strengths
- uses Nostr as the social substrate
- avoids turning into a vague gossip machine
- avoids a giant feature pile

This is the `hit the ground running` version.

## The Core Question

If someone holds the coin, what do they actually get?

Not:

- random private chatter
- vague alpha theater
- "secret backroom" vibes with no productive output

They should get:

- earlier signal
- tighter coordination
- better context
- higher-trust communication
- taskable community infrastructure

That is the useful club.

## Product Thesis

The coin-holder club should be a `creator operations + community coordination` system.

The holder is not paying for "access to rumors".
The holder is getting access to:

- structured information
- priority rooms
- coordinated campaigns
- workflow-backed tools
- operator-grade visibility

The real value is:

- turning a coin community into a functioning operations surface

## First-Class Aims

These are the most important aims for Pump-based meme-coin operations.

### 1. Holder Alignment

Holders need one place to understand:

- what the creator is doing
- what the coin is trying to do
- what is active right now
- what the current policy / status / campaign is

This is a control-plane problem, not a "post more content" problem.

### 2. Moderator / Operator Coordination

A live meme coin needs a private operator surface for:

- moderation
- spam / scam filtering
- scheduling
- room management
- content sequencing
- creator handoff

This is where the private rooms matter.
Not for gossip, for operations.

### 3. Signal Compression

Communities drown in noise.

The useful club gives holders:

- filtered summaries
- priority notices
- reputation-weighted announcements
- escalation channels

Champion Council is especially strong here because it already has:

- workflow execution
- memory
- observe / feed surfaces
- ranking / marketplace patterns

### 4. Paid / Proven Access

Some surfaces should not be open to everyone.

The system should support:

- bag-based access
- zap-based access
- badge / role-based access
- temporary campaign access

This is where the holder club becomes real instead of cosmetic.

## The MVP Offer

The first real product should include only five surfaces.

### Surface 1: Creator Board

A signed board for the coin with:

- creator status
- current campaign
- active policy
- links / official references
- disclosure timeline

This is the public authority surface.

### Surface 2: Holder Room

A coin-specific room for holders with:

- announcements
- structured live chat
- pinned operational updates
- event / campaign threads

This is not a general social feed.
It is a coin operations room.

### Surface 3: Operator Room

A private room for creator + moderators + trusted operators with:

- moderation notes
- task routing
- escalation queue
- campaign sequencing
- incident handling

This is the "behind the scenes" room, but for doing work.

### Surface 4: Holder Reputation / Roles

A minimal role system with:

- verified creator
- operator
- moderator
- high-signal holder
- supporter

Roles should be driven by:

- creator assignment
- reputation
- badges
- access policy

### Surface 5: Workflow Actions

The club should expose a few real actions:

- publish update
- open campaign room
- assign moderator
- issue badge
- run summary workflow
- trigger alert / call-to-action

That makes the club operational instead of performative.

## What Holders Should Actually Be Able To Do

At MVP, holders should be able to:

- enter the holder room if they meet access policy
- read creator disclosures and active campaign context
- receive structured alerts
- participate in voice/chat rooms
- vote in polls
- earn badges / roles
- submit requests or jobs

At MVP, holders should **not** be promised:

- trading alpha
- price guarantees
- insider orchestration
- coordinated market manipulation
- yield or rewards promises

## What Operators Should Actually Be Able To Do

Operators should be able to:

- publish coin policy and updates
- segment public vs holder-only vs operator-only communications
- coordinate moderators
- monitor room health
- issue badges and role changes
- queue workflows for summaries, alerts, and campaigns

## Access Model

The most important technical question is:

how do we decide who is "in"?

We should support three access modes, in this order:

### Mode 1: Manual allowlist / role assignment

Fastest to ship.

- creator or operator assigns access
- useful immediately
- no on-chain verification required

### Mode 2: Zap gate

Simple, already aligned to Nostr.

- pay to enter
- pay to trigger certain workflows
- pay to support campaigns

This is not bag-based, but it is easy to operationalize.

### Mode 3: Bag verification

This is the desired "club by bag" model, but it requires a real proof surface.

That means:

- wallet binding
- balance check
- threshold rule
- refresh / expiry semantics

This is valuable, but it is not free.
It should be a dedicated phase, not a hand-wave.

## Most Valuable Existing Capabilities

Champion Council already has more relevant tooling than it may seem.

The most useful existing families for this product are:

### 1. Community / Nostr UI surfaces

Already present in current runtime:

- chat
- DMs
- voice rooms
- polls
- badges
- marketplace
- DVM jobs

### 2. Workflow engine

Already ideal for:

- summaries
- alerts
- moderation routines
- campaign setup
- creator announcement sequencing

### 3. Memory and document surfaces

Use for:

- policy records
- incident logs
- campaign notes
- runbooks
- room histories

### 4. Reputation / Web3 identity from old extension branch

Already present there:

- Nostr identity
- DID / VC helpers
- reputation chain
- badge issuance

That is a major asset.

## Best MVP Sequence

This is the recommended order.

### Phase A: Make standalone social real

Port or reconstruct:

- DMs
- rooms
- room presence
- live room chat
- profile / privacy persistence

Without this, the club is cosmetic.

### Phase B: Ship the coin operations board

Add:

- coin record
- creator binding
- policy record
- campaign record
- disclosure feed

This gives the room a spine.

### Phase C: Add role and gate policy

Add:

- creator
- operator
- moderator
- supporter
- holder

with:

- manual assignment first
- zap gate second
- bag verification third

### Phase D: Wire workflows

Add workflows for:

- summary generation
- alert generation
- room opening
- campaign state updates
- badge issuance

## What Not To Build First

Do not build these first:

- giant all-purpose social network
- "intel engine" for trash talking other coins
- holder reward mechanics
- token swap abstractions
- treasury automation with implied investment expectations
- massive on-chain integration surface before access logic is even stable

Those are onion layers, not the core.

## Hard Product Definition

If the MVP works, the one-sentence definition is:

`A Nostr-backed operations club for a Pump coin, where creator, holders, and operators coordinate through structured rooms, roles, disclosures, and workflow actions.`

That is clear.
That is buildable.
That is more valuable than "private meme-coin gossip chat."

## Recommended Immediate Build Cut

If only one concrete thing gets built next, it should be:

`coin operations board + holder room + operator room + role gating`

That is the first whole product slice.

Everything else can layer around it later.
