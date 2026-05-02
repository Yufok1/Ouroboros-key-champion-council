# Input Replay Data

## Status

Implemented package surface.

Schema:

```text
middle_passage_replay_packet.v1
```

Purpose:

Preserve the input data and assumptions needed to rerun a package output.

Replay data exists so a future operator, organism finder, Champion Council review, or Holo Deck replay can ask:

- what went in?
- what assumptions were used?
- what was produced?
- did the same inputs produce the same generalized output?
- what remains uncertain?

## Contract

Replay data is not original evidence.

Replay data is not proof of remains.

Replay data is a receipt-backed rerun path.

Replay data is not a button.

Replay data is not a control receipt.

CLI commands are control actuators that create or rerun artifacts. The generated packet is review material; it only becomes receipt-backed when a provenance layer records the packet, hashes, and lineage.

Safe path:

```text
source row -> normalized voyage -> model assumptions -> generalized output -> replay packet -> provenance receipt -> later rerun
```

Unsafe path:

```text
replay packet -> treated as new source evidence -> public claim
```

## CLI

Write replay data while creating a synthetic-safe sample:

```bash
middle-passage sample --output sample.geojson --replay-output sample.replay.json
```

Write replay data while modeling deposits:

```bash
middle-passage model-deposits --voyages voyages.csv --output zones.geojson --replay-output zones.replay.json
```

Replay a saved packet:

```bash
middle-passage replay --input zones.replay.json --output zones.replayed.geojson
```

This command starts a rerun.

The command itself is not a receipt.

The rerun output and refreshed packet may be receipted afterward.

Refresh replay data while replaying:

```bash
middle-passage replay --input zones.replay.json --output zones.replayed.geojson --replay-output zones.refreshed.replay.json
```

## Packet Contents

The replay packet carries:

- schema name
- status
- claim language
- sensitivity posture
- corridor
- normalized voyage rows
- generated zone metadata
- input hash
- output hash
- packet hash

It intentionally does not carry:

- authority to publish
- exact protected conclusions
- descendant/community approval
- legal or archaeological review
- any claim that a location is confirmed

## Holo Deck Use

Holo Deck can use replay packets as safe staged inputs.

It may show:

- input row
- assumptions
- generated generalized zone
- uncertainty
- sensitivity label
- rerun result

It must show that replay is a reenactment of the package method, not the historical event itself.

It must also show whether a frame is live state, replay, simulation, or review.

## Organism Finder Use

Convergence Engine organisms may inspect replay packets to:

- compare assumptions
- detect missing fields
- propose safer wording
- flag sensitivity risk
- suggest documentation gaps

They must not convert replay data into discovery claims.

## Champion Council Use

Champion Council should treat replay packets as review artifacts.

It can route them by:

- sensitivity
- source completeness
- assumption drift
- output stability
- required reviewers

Any public release remains gated by Source HOLD.
