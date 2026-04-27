# Brotology Platform Layering Policy

Date: 2026-04-23
Status: active continuity policy
Mode: `etrigan`

## Purpose

Map the Brotology theory onto the actual operational surfaces so we can keep up with growth without pretending that:

- the beginner guide
- the docs folder
- the Hugging Face Space
- and the private self-deploy/runtime machinery

are all the same thing.

They are not the same thing.
They should not change at the same rate.

## Bottom Line

The clean split is:

- `beginner guide` = cold primer
- `brotology docs folder` = doctrine and transfer floor
- `private HF Space` = hot furnace / live platform
- `private repo state` = machinery, deployment, and checkpoint substrate

If we let those layers collapse into one another, the system becomes unreadable fast.

## The Four Layers

### 1. Cold Primer Layer

This is the slow-changing public doctrine surface.

Primary artifacts:

- `BROTOLOGY_BEGINNERS_GUIDE_2026-04-23.md`
- public `Brotology-field-guide` repo

Purpose:

- explain what Brotology is
- hold the branch taxonomy steady
- preserve the canon/culture boundary for new readers
- onboard strangers without requiring live runtime context

Change posture:

- slow
- deliberate
- only when the underlying doctrine actually changes

This is not where live product churn should show up.

### 2. Doctrine / Transfer Floor

This is the working docs layer.

Primary artifacts:

- `BROTOLOGY_FIELD_OPERATIONS_MANUAL_2026-04-22.md`
- `BROTOLOGISTS_LOG_2026-04-23.md`
- `OPERATIONAL_SURFACE_2026-04-23.md`
- this policy doc

Purpose:

- translate theory into working operator language
- hold active mappings and corrections
- carry cultural residue without letting it overwrite canon
- prepare material before it moves upward to public doctrine or downward into runtime

Change posture:

- medium speed
- continuity-driven
- allowed to absorb new phrasing, corrections, and framing

This is the compost layer, not the public homepage and not the live server.

### 3. Hot Furnace / Live Platform

This is the private HF Space.

Primary surfaces:

- `static/index.html`
- `/panel`
- `server.py`
- `static/main.js`
- `scripts/text_theater.py`
- live MCP/runtime behavior

Purpose:

- be the actual platform
- run councils, tools, memory, workflows, and environment surfaces
- expose the operator capsule live
- host the evolving field-operations platformer behavior

Change posture:

- fast
- experimental
- operational
- instrumented

This layer is allowed to move constantly as long as:

- `query_thread` remains visible
- `output_state` remains the orienting crane
- `entry_gate` remains real
- `workspace_packet` stays honest about what is being changed

The furnace is where the team reorganizes around the fire.
That does not mean the fire gets to rewrite the glossary every night.

### 4. Private Machinery / Checkpoint Substrate

This is the full `champion_councl` workspace and its checkpoint/deploy history.

Purpose:

- hold the whole private system
- carry proprietary machinery
- preserve release receipts and recovery lanes
- support deliberate pushes to private HF/GitHub surfaces

Change posture:

- continuous internally
- checkpointed before publish/deploy
- audited before outbound pushes

This layer may contain things that do not belong in the public guide or even in the private Space deploy surface.

## Exposure Alignment

The right question is not:

- are the ideas mine

The right question is:

- which layer is the public allowed to access
- which layer is the public allowed to inspect
- which layer is the public allowed to clone
- which layer is the public allowed to infer from the live experience

That is an exposure-alignment problem, not an authorship problem.

The working split is:

- `public access` = the experience, demo, behavior, outputs, and selected doctrine
- `protected access` = the running facility surface is public, but the source stays hidden
- `private access` = continuity substrate, checkpoints, personal ideation residue, prompt/doctrine repair lanes, and machinery that should not be cloned or casually mined

This means the facility can still be your idea all the way through while only some strata are exposed.

Public does not have to mean:

- raw notebook exhaust
- continuity residue
- private planning trench
- checkpoint history
- every prompt, patch, or proprietary implementation lane

The cleaner law is:

- publish the effect
- constrain the mechanism
- preserve the private residue unless there is a deliberate reason to surface it

## Hugging Face `protected` / `BROTECTED`

For Spaces, the strongest current fit is often `protected`:

- app access = public
- repo source = hidden
- cloning = blocked

That is the correct middle state when the goal is public access to the platform experience without turning the entire repository into an open quarry.

It is still not magic. `Protected` hides source, not live browser-visible payloads. If the app itself exposes docs, debug panes, continuity surfaces, downloadable assets, or private operator state, then those are public in practice.

So the operational rule is:

- `public` if the source itself is intentionally open
- `protected` if the experience should be public but the source should remain closed
- `private` if neither the app nor the repo should be publicly reachable

## Public Hardening

Before a public-facing release, the runtime should not merely hide secrets. It should actively disable clone-grade and operator-only surfaces.

Minimum public hardening posture:

- block MCP ingress and external tool transports
- block continuity/archive recovery lanes
- block FelixBag and file-workspace browsing/editing lanes
- block checkpoint, persistence, cache, export, and restart controls
- keep public access focused on demo behavior rather than private transport
- redact `entry_gate`, `docs_packet`, `workspace_packet`, `continuity_packet`, and `misunderstanding_box` from browser-visible output carriers

Short law:

- public sees the effect
- protected source hides the machinery
- hardening disables the operator trapdoors instead of trusting strangers not to click them

## The Mapping To Brotology Branches

### Science Surfing

Most alive in:

- hot furnace / live platform

Why:

- measurement while moving
- support/contact truth
- route and pressure reads

Canonical docks:

- `pan_probe`
- `balance`
- contact surfaces
- `range_gate`
- `reach_envelope`

### Architect Surfology

Most alive in:

- doctrine / transfer floor
- hot furnace / live platform

Why:

- sequence, route, force carriage, runtime structure

Canonical docks:

- `query_thread`
- `output_state`
- `trajectory_correlator`
- `sequence_field.force_wave`

### Field Utility

Most alive in:

- doctrine / transfer floor
- private machinery / checkpoint substrate

Why:

- decide what is load-bearing
- decide what ships
- decide what is decorative, archival, local, or deployable

Canonical docks:

- `docs_packet`
- `workspace_packet`
- `continuity_packet`
- `misunderstanding_box`
- `watch_board`

### Dark-Field Caution Lanes

Most alive in:

- all layers

Why:

- this is the branch that stops the layers from lying about one another

Current risks:

- public guide absorbing live-runtime churn
- lore terms impersonating runtime surfaces
- private deploy accidentally becoming public doctrine
- `self_deploy/` being assumed present in Space when `.gitignore` currently excludes it

### Derived Fringe Fields

Most alive in:

- doctrine / transfer floor
- selective public framing
- selective live UX/theater polish

Why:

- these help posture and legibility
- they should not become hidden controllers

## The Thumb Rule

Every layer needs a dumb rule that still grows things.

Here, it is:

- cold primer changes slowly
- doctrine layer translates
- hot furnace experiments
- private machinery checkpoints before outbound travel

If a thing is changing every day, it is probably furnace material.
If a stranger should be able to read it in six months, it is probably primer material.

## How Material Moves Between Layers

### Furnace -> Doctrine

When a live runtime behavior produces a real repeated insight:

1. verify it on live surfaces
2. name the seam
3. map it to canon
4. write the doctrine note

### Doctrine -> Primer

When a doctrine note stabilizes and remains true across resets:

1. trim it
2. remove local noise
3. keep the canon/culture boundary explicit
4. publish it to the guide/public repo

### Machinery -> Furnace

When private code or config changes are actually meant to affect the Space:

1. checkpoint locally
2. inspect `.gitignore` / deployment boundaries
3. verify what the Space will really receive
4. push deliberately

## The Current Private-Space Reality

As of this pass:

- `origin` points to `https://huggingface.co/spaces/tostido/Champion_Council_private`
- the root Space app is the live HF furnace
- `.gitignore` explicitly excludes `self_deploy/`

So if the desired end state is:

`mother fucking brotologists field operations champion council platformer`

the honest first implementation route is:

- evolve the root private Space app into that platform surface

not:

- assume `self_deploy/` is already part of the deploy payload

If we want curated `self_deploy/` material in the Space later, we must reopen that gate on purpose.

## Update Policy

### Beginner Guide

Update only when:

- branch taxonomy changes
- canon/culture boundary changes
- core explanatory doctrine changes

### Docs Folder

Update whenever:

- a mapping sharpens
- a correction lands
- a new operator-facing concept stabilizes
- a public/release/deploy policy needs to be recorded

### Private HF Space

Update whenever:

- runtime/platform behavior changes
- UX/theater changes
- tools/help/surfaces change
- the field-operations platformer gets more literal

### Private Repo Checkpoints

Checkpoint whenever:

- deployment direction changes
- large theory packets land
- platform boundaries change
- before outbound push

## One-Paragraph Read

The beginner guide is the cold primer and should stay comparatively stable. The Brotology docs folder is the doctrine and transfer floor where new mappings, corrections, and cultural residue are metabolized. The private HF Space is the hot live furnace where the actual field-operations platform keeps changing. The private repo is the checkpoint substrate under all of it. We keep up by letting each layer change at the speed appropriate to its job instead of demanding that the glossary, the docs, the runtime, and the deployment machinery all mutate in lockstep.

## Closing Rule

Do not ask the furnace to be a textbook.
Do not ask the textbook to be a furnace.
Use the transfer floor to keep them in correspondence.
