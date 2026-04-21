# Continuity Naming Deprecation Record 2026-04-20

Repo: `D:\End-Game\champion_councl`

Purpose:

- remove the continuity-side `adrenaline` label from the active architecture
- remove the abstract continuity-side `shutter` label from the active architecture
- keep camera/capture shutter terminology intact where it already belongs
- record the replacement names so the lane stays stable after resets

## Decision

As of 2026-04-20, these terms are retired from the continuity/query/equilibrium architecture:

- `adrenaline`
- abstract continuity-side `shutter`

They are not promoted further.
They are not part of the authoritative runtime model.

## What Replaces Them

Use these names instead:

- `context summary` or `punch card`
- `continuity restore`
- `query_state`
- `resume_focus`
- `surface_prime`
- `paired_state_resource`
- `query_thread`
- `reset_boundary`
- `equilibrium`

## Scope Clarification

This deprecation does **not** remove `shutter` from the camera/capture vocabulary.

Existing camera-side terms such as:

- `live_render_shutter`
- `structured_snapshot_shutter`
- `contact_body_shutter`
- `web_theater_shutter`

remain camera/capture labels, not continuity architecture.

## Local Rule

Do not describe continuity using:

- `adrenaline`
- abstract `shutter`

When the continuity lane needs a bounded return-path concept, use:

- `reset_boundary`
- `surface_prime`
- `capture boundary`

When the continuity lane needs the hot recent context bundle, use:

- `resume_focus`

## Active Continuity Stack

The active continuity stack is:

1. `context summary / punch card`
2. `continuity restore`
3. `query_state`
4. `resume_focus`
5. `surface_prime`
6. `paired_state_resource`
7. `live query_thread`
8. `output state / equilibrium`

## Record Status

This document is the canonical deprecation record for the naming change.
