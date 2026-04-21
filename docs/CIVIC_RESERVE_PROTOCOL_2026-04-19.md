# Civic Reserve Protocol 2026-04-19

## Purpose

Define a lawful, disciplined way for the Technolit / Hold Door treasury lane to support the United States, public-good infrastructure, and government-compatible crypto adoption without crossing into bribery, gratuities, or vague patriotic theater.

This is not legal advice.

It is an operating protocol.

## Core Position

The goal is not:

- to "pay them off"
- to buy access
- to influence official acts
- to create a secret side-door between treasury and government actors

The goal is:

- to fund public-good aligned infrastructure
- to operate legibly inside U.S. rules
- to strengthen boring civic capacity
- to make the treasury visibly cooperative with the broader ecosystem

## Hard Boundary

Never give anything of value to a public official in order to influence an official act.

Never build a "thing they can't refuse" lane.

Never use the treasury to create a quid pro quo with any federal, state, or local official.

That includes:

- direct bribes
- disguised "gratuities"
- consulting side-payments
- donation-for-access schemes
- regulatory favoritism requests tied to money

## Allowed Civic Lanes

### 1. Tax and compliance first

The first civic lane is boring:

- taxes
- recordkeeping
- accurate reporting
- reserve for obligations

This is the minimum lawful contribution to public order.

### 2. Unconditional Treasury donation

If the project wants a patriotic reserve lane, it may route funds through official U.S. Treasury donation channels.

This must be:

- unconditional
- non-political
- non-influence-seeking
- documented

Examples:

- gift to the United States
- gift to reduce debt held by the public

### 3. Civic-tech public goods

A better long-term lane is to fund tools that make crypto, reporting, safety, provenance, and public visibility easier for everyone.

Examples:

- open-source proof / audit tooling
- public documentation
- educational surfaces
- safer reporting / recordkeeping systems
- public-interest visualizations

### 4. Formal government interfaces only

If the project ever works with government directly, do it through ordinary channels:

- procurement
- grants
- public applications
- published eligibility and award processes
- registered entities if required

No special side arrangements.

## Preferred Treasury Split

If the treasury becomes meaningfully valuable, add a civic reserve lane.

Suggested posture:

- `Body` = holders / continuity
- `Raid` = contribution / campaign
- `Shield` = reserve / safety / threat
- `Forge` = building / experimentation
- `Civic Reserve` = taxes / compliance / public-good / unconditional civic contribution

Keep Civic Reserve separate from personal draw.

## Holder Vote Lane

Yes, a donation fund can exist.

But the safest version is not:

- open-ended holder control over all treasury money
- free-form suggestions to "send funds to government"
- direct transfers to unverified recipients

The safest version is:

- a bounded `Civic Reserve`
- an advisory holder vote
- a pre-vetted whitelist of official destinations
- operator verification before release

### Recommended governance posture

Treat holder voting as:

- advisory
- ceremonial
- directional

Not as:

- a binding legal right
- a redemption right
- a claim on treasury funds

### Why

This keeps the lane:

- legible
- low-chaos
- harder to abuse
- compatible with official government intake realities

## Whitelisted Destination Types

### Tier 1: simple federal lanes

- `Treasury general gift`
- `Treasury debt reduction gift`

These are the cleanest because they are official, unconditional, and easy to verify.

### Tier 2: official agency donation lanes with explicit acceptance

Examples include certain National Park Service donation channels where parks state they can accept direct gifts and, in some cases, earmark them to specific programs or projects.

Use only destinations that clearly state:

- the agency or park accepts donations directly
- how to make the donation
- whether specific project/program designation is allowed

### Tier 3: official nonprofit partners where appropriate

If an agency strongly relies on an official philanthropic partner, that can be a valid lane, but it is not the same thing as a direct government deposit.

Use this tier only when the distinction is made explicit in the report.

## What The Reserve May Fund

Allowed:

- tax reserve
- accounting / compliance / legal review
- benefits-safe structuring and reporting
- unconditional donations to official government channels
- public-interest crypto tooling
- official grant / procurement application costs if lawful and necessary

Not allowed:

- influence buying
- payments to officials
- favors in exchange for access
- campaign-style steering unless separately lawful and handled outside this protocol

## Report Surface

If this lane exists, it should be visible.

Use a reportable packet such as:

- `civic_reserve_packet`

Fields:

- `policy_id`
- `reserve_bps`
- `funding_scope`
- `allowed_uses`
- `forbidden_uses`
- `current_balance`
- `committed_balance`
- `disbursed_balance`
- `issuance_refs`
- `public_line`

Human-facing render:

- `Civic Reserve Notice`
- `Official Hold Door Civic Report`

Optional governance fields:

- `vote_window_id`
- `whitelist_version`
- `advisory_winner`
- `operator_validated_destination`
- `execution_rail`
- `release_status`

## Execution Rule

Even if the vote is on-chain or token-holder-facing, the actual release should remain:

- off-chain verified
- manually approved
- sent only through the official payment/donation route for that destination

In practice this usually means:

- not direct SOL to a government wallet
- first convert as needed
- then complete the payment using the destination's official accepted rail

## Example Safe Flow

1. Allocate `Civic Reserve` for the epoch.
2. Publish a whitelist of valid destinations.
3. Holders cast an advisory vote.
4. Operator verifies the winning destination is still valid and lawful.
5. Release through the official channel.
6. Publish:
   - destination
   - amount
   - payment rail
   - receipt/proof reference
   - `Hold Door Civic Report`

## Solana / USD Reality

For actual government-facing payment lanes, expect ordinary official payment rails to dominate.

That means:

- do not assume government agencies want direct meme-coin flows
- do not assume direct SOL acceptance
- expect USD-form donation / payment rails where required

Crypto may remain:

- the project treasury medium
- the measurement / reporting surface
- the proof / transparency surface

But official payment completion may still need:

- bank transfer
- card / ACH
- Pay.gov
- other ordinary rails

## SSDI Safety Overlay

If the operator is on SSDI or other benefits:

- civic generosity does not erase work-activity issues
- later donation does not substitute for reporting
- personal draw and active work still need separate handling

The reserve should therefore default to:

- treasury-controlled
- manually released
- documented
- separate from personal living funds

## Recommended Short-Term Posture

1. No influence lane.
2. No "bribe but make it utilitarian" lane.
3. Add a `Civic Reserve` as a declared percentage or discretionary bucket.
4. Keep the reserve treasury-controlled.
5. Use it first for taxes, compliance, and public-good tooling.
6. If donating to government, use official unconditional channels only.
7. Publish the reserve through owned surfaces and receipts.

## Sources

- DOJ bribery / public officials: https://www.justice.gov/usao/eousa/foia_reading_room/usam/title9/crm02041.htm
- DOJ government integrity: https://www.justice.gov/jm/jm-9-85000-protection-government-integrity
- Treasury gifts to the U.S.: https://fiscal.treasury.gov/public/gifts-to-government.html
- Treasury gifts to reduce debt: https://www.treasurydirect.gov/government/public-debt-reports/gifts/
- NPS donate page: https://www.nps.gov/getinvolved/donate.htm
- Grants.gov eligibility: https://grants.gov/learn-grants/grant-eligibility.html

## Bottom Line

If Technolit wants to "work for America," the clean version is:

- stay lawful
- stay legible
- pay taxes
- build public goods
- use unconditional official channels where appropriate
- never confuse civic contribution with influence buying

That is stronger, safer, and more durable than any shortcut.
