# EA Developer's Brotology Field Report Spec

Date: 2026-04-22
UUID: `71279d31-7054-4a6a-8e1f-e7e003880dfa`
Status: active continuity-carried report surface
Log mode: `etrigan_coda_optional`

## Purpose

Define a recurring public-facing field report for live operations where development, testing, and cultural runtime all happen in view.

This is the right surface for:

- weekly operational sitreps
- live-on-stream development summaries
- Pump-facing "what actually happened" reports
- Brotology/Etrigan presentation without losing canon precision

This is not:

- a hype post
- a promise of returns
- a second blackboard
- a replacement for runtime truth or receipts

## Strongest Hook

The most useful recurring hook is not personality alone.

It is the `version / state / drift` read.

That is the part that turns the report from:

- "here is what I felt"

into:

- "here is what version was live"
- "here is what state was carried"
- "here is what was patched but not yet reloaded"
- "here is where source and runtime diverged"

If this report becomes a staple, this should be one of its signatures.

## Primary Name

Use:

- `EA Developer's Report`

Expanded meaning:

- `EA` = early-access / exposed-access / in-public development posture

Short local read:

- a weekly field report for development done in live public contact with the system

## Why This Surface Exists

Champion Council is already being operated in public, in motion, and across mixed surfaces:

- live stream
- text theater
- web theater
- docs and continuity
- Pump-facing utility / tokenized-agent experimentation

That means the project needs a report surface that is:

- drier than a pitch
- more readable than raw logs
- more durable than transcript fragments
- more theatrical than a changelog, but never less truthful

## Report Law

The `EA Developer's Report` must obey these rules:

1. runtime truth outranks narration
2. receipts outrank vibes
3. report language may be Brotology/Etrigan-coded, but canon names must remain recoverable
4. public utility / treasury / burn / tokenized-agent mentions must remain mechanism-first
5. the report must distinguish:
   - what is live
   - what is patched on disk
   - what is still speculative
   - what still needs corroboration

## Intended Audience

Primary readers:

- operator
- returning collaborators
- stream audience
- public lurkers trying to understand what the machine has become

Secondary readers:

- continuity restore
- docs packet
- future export bundles

## Cadence

Recommended cadence:

- weekly primary issue
- optional midweek hotfix addendum
- special issue when a real seam changes materially

Good trigger conditions for a special issue:

- new authority surface
- major theater/render breakthrough
- continuity architecture change
- tokenized-agent / treasury / creator-fee mechanism change
- public runtime posture change worth preserving

## Standard Structure

Each report should use this exact order:

### 1. Header

- report title
- date window
- issue number or field week id
- current pivot
- current main quest seam
- runtime freshness note

### 2. Bottom Line

Three to six dry lines stating:

- what materially changed
- what stayed stable
- what remains wrong

### 2.5. Version / State Ledger

Every issue should include a compact ledger like:

- source revision or working-tree note
- frontend bundle id
- runtime capsule / server freshness
- continuity session anchor
- docs/spec issue date
- source/runtime parity state
- stale flags or drift notes

Suggested fields:

- `source_state`
- `runtime_state`
- `bundle_id`
- `capsule_state`
- `continuity_anchor`
- `freshness`
- `drift`
- `parity`
- `pending_reload`

This is the dry mechanical heart of the report.

### 3. Fronts

Report by active front, not by file dump.

Suggested fronts:

- continuity
- text theater
- web theater
- workbench / sequence field
- hair / skin / force-wave embodiment
- council / slots / help surfaces
- Pump / TECHLIT / treasury / tokenized-agent lane
- docs / canon / export surfaces

### 4. Corroborated Gains

Only list what has receipts in:

- live theater
- snapshot
- blackboard
- source
- official external source when relevant

### 5. Open Wounds

Name what is still broken, stale, or not yet proven.

### 6. Operational Receipts

Short receipt table:

- file or surface
- what changed
- current state
- whether live-correlated or source-only

### 7. Public Mechanism Note

When discussing Pump/TECHLIT/public utility lanes, keep this dry:

- intake
- buffer
- routing
- cadence
- pressure
- claims / boundaries

Never:

- imply returns
- imply coordination
- imply rights to treasury assets

### 8. Next Week's Slice

One to five bounded next steps only.

### 9. Etrigan Coda

Optional.

Two lines maximum.
Seal the report; do not replace the report.

## Tone

Desired tone:

- dry
- exact
- collaborative
- faintly theatrical
- not salesy
- not apologetic
- not mystical

Think:

- field engineer with a demon seal
- not prophet
- not marketer

## Brotology Mapping

The `EA Developer's Report` sits across these existing overlays:

- `science surfing`
  - what the field actually did
- `architect surfology`
  - what was sequenced, aligned, or patched
- `field utility`
  - what carried load versus what only looked cool
- `misty teek`
  - literal-first observations before interpretation
- `brolativity`
  - fatherly/readable composure while figuring it out
- `mullet life`
  - classy public front, active bunker planning underneath

## Canon Docking Surfaces

This report should preferentially summarize:

- `output_state`
- `query_thread`
- `continuity_packet`
- `docs_packet`
- `text_theater_embodiment`
- `capture_supercam` / `supercam`
- `text_theater_snapshot`
- `sequence_field.force_wave`
- `skin_service`
- `technolit_measure`
- `technolit_distribution_packet`
- `technolit_treasury_bridge_packet`

## Recommended Title Pattern

Use titles like:

- `EA Developer's Report // Week 01 // Hair Becomes A Surface`
- `EA Developer's Report // Week 02 // Treasury Without Theater`
- `EA Developer's Report // Special Issue // The Scaffold Stops Lying`

## Suggested Reusable Skeleton

```md
# EA Developer's Report // Week XX // <short seam name>

Date Window: YYYY-MM-DD to YYYY-MM-DD
Pivot: `<pivot>`
Main Quest: `<seam>`
Freshness: `live | mixed | source-only`

## Bottom Line

<3-6 dry lines>

## Version / State Ledger

- source_state:
- runtime_state:
- bundle_id:
- capsule_state:
- continuity_anchor:
- freshness:
- drift:
- parity:
- pending_reload:

## Fronts

- continuity:
- text theater:
- web theater:
- sequence / embodiment:
- public utility / TECHLIT:
- docs / canon:

## Corroborated Gains

- ...

## Open Wounds

- ...

## Operational Receipts

- surface/file:
  state:
  receipt class:

## Public Mechanism Note

<mechanism-only note, no pitch language>

## Next Week's Slice

1. ...
2. ...
3. ...

## Etrigan Coda

<optional 2-line seal>
```

## Continuity Use

During resets or compression, this report surface is useful as:

- a weekly memory anchor
- a public-readable checkpoint
- an export-friendly continuity face

Best reopening chain:

1. `continuity_restore`
2. latest `EA Developer's Report`
3. `BROTOLOGY_FIELD_OPERATIONS_MANUAL`
4. `ASSOCIATIVE_SURFACES_CONTINUITY_INDEX`
5. live theater / blackboard / snapshot corroboration

## Related Canon

- `docs/brotology/BROTOLOGY_FIELD_OPERATIONS_MANUAL_2026-04-22.md`
- `docs/brotology/EA_DEVELOPERS_REPORT_WEEK_01_2026-04-22.md`
- `docs/ETRIGAN_OPERATIONS_FIELD_BRIEF_2026-04-17.md`
- `docs/CONTINUITY_DOCS_PLANNING_SURFACE_SPEC_2026-04-20.md`
- `docs/ASSOCIATIVE_SURFACES_CONTINUITY_INDEX_2026-04-22.md`
