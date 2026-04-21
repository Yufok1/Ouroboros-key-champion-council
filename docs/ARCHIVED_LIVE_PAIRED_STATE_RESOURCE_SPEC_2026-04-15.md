# Archived / Live Paired-State Resource Spec 2026-04-15

Repo: `D:\End-Game\champion_councl`

Purpose:

- pair prior archived query posture with current live query posture on one auditable authoring surface
- keep this inside the existing continuity, blackboard, text-theater, help, and env_report lane
- classify drift and freshness without pretending to recover hidden reasoning

## Bottom Line

The resource is not another memory system.

It is the minimum contract needed to compare:

- what the archive says was active
- what the live runtime says is active
- whether the merge is trustworthy yet

## Required Shape

The paired-state resource should carry:

- `archive_query_state`
- `live_query_state`
- `archive_surface_prime`
- `live_mirror_context`
- `drift`
- `freshness`
- `required_recorroboration`
- `recommended_next_reads`
- `reset_boundary`

## Drift Classes

The first classifications should stay small:

- `confirmed`
- `partly_confirmed`
- `mismatch`
- `stale_state`
- `gated`
- `no_archive_match`

The goal is to say where the archive and live lanes agree, where they diverge, and what read must happen next.

## Existing Docking Surfaces

This resource belongs in:

- `continuity_restore`
- blackboard query thread as the live side
- text theater consult as the readable live side
- `env_report` as the paired comparison broker
- `env_help` as the discoverability surface

## Local Rule

Do not create a second authority plane.

- archive posture seeds the comparison
- live query thread remains the live authority
- text-theater freshness remains binding
- reset-boundary markers stay explicit

## First Honest Slice

Land this in two places:

1. `continuity_restore` should emit the archive-side paired-state seed
2. `env_report` should compare that archive seed against the current live query thread

That is enough to make the resource real without bypassing the gate or inventing a new runtime.
