# Dual Theater Parity Sitrep 2026-04-08

Repo: `F:\End-Game\champion_councl`

Scope:

- current browser/text-theater parity lane only
- builder workbench full-body plus isolated part/adjacent/chain views
- no Coquina or facial-lane expansion here

## Current Position

The project is no longer in the old "text theater is broadly laggy and structurally downstream" state.

The live browser and text lanes now share enough truthful contract that scoped part work, turntable/manual camera sync, and builder-stage guide behavior can be debugged as one parity system instead of as unrelated symptoms.

The current lane is:

1. close remaining browser/text parity gaps at the source or contract boundary
2. turn those validations into repeatable operator/agent playbooks
3. use the dual theaters as a comparative instrument for future system building

## What Was Closed In This Pass

### 1. Scoped stage guide was using the wrong source

The scoped workbench guide in the browser was still being built from the full-body workbench box.

That polluted both surfaces:

- the web guide/pad stayed oversized in scoped part modes
- the exported text snapshot inherited the same wrong board

This is now corrected in `static/main.js` by deriving scoped guide floor, pad, frame, and camera fit from the selected display surface instead of the whole builder body.

### 1.5. Scoped authoring boards now normalize from the active part-view recipe

Even after the scoped guide started using the right selected surface, non-body scopes were still inheriting wildly different board sizes because the guide scale was being derived straight from raw chain dimensions.

That made different isolated chains feel like different stages instead of one consistent authoring board.

This is now corrected in `static/main.js` by normalizing scoped guide sizing from the active scoped part-view recipe distance instead of only from raw scope bounds.

### 2. Text renderer was collapsing limb scaffold cylinders into bone-looking lines

In full-body perspective views, large scaffold limb radii were still projecting down to tiny stamp sizes.

The source packet was already correct in body mode.

The renderer policy was the remaining liar.

This is now corrected in `scripts/text_theater.py` by using larger scaffold stamp thresholds for large exported limb radii.

### 3. Ellipsoid shell noise was reduced without destroying structure

The old shell-point noise was removed.

The ellipsoid cross-brace ring was restored so the head/torso volumes still read structurally instead of becoming flat or ambiguous.

## Instrumentation Added

`scripts/eval_isolation_scopes.py` is now the main comparative harness for this lane.

It now records, per scenario:

- selected bone
- display scope
- browser stage guide
- selected part surface
- part camera recipes
- browser-visible scaffold slots
- text-rendered scaffold slots
- missing scaffold deltas
- floor/grid/guide counts from the text render model

This means parity faults can now be classified quickly as:

- browser export fault
- text renderer fault
- stale mirror/snapshot fault

instead of only by manual impression.

## Current Verified Truths

From the latest recorded comparative sweep:

- in `body` scope, browser-visible limb scaffold slots and text-rendered limb scaffold slots match
- in scoped chain modes, the text renderer now matches the browser-exported visible scaffold set for the active scoped chain
- scoped guide sizes are now materially smaller than full-body guide sizes instead of inheriting the giant full-body workbench board
- scoped part/chain boards are now being normalized from the same staged framing path the browser uses for `Frame Selected`, rather than from a second parallel sizing heuristic

That does **not** mean parity is "done forever."

It means the lane is now stable enough to use as a comparative build instrument.

## Important Remaining Truths

### 1. Text theater still does not consume a single final browser-authored post-stage display contract

It is closer than before, but still partially reconstructive.

That means future unknown parity bugs can still appear where:

- the browser is rendering from one resolved staged truth
- the text lane is rendering from a reduced snapshot view of that truth

The long-term shortcut is still:

- emit one browser-authored display-surface contract after scope, staging, and guide resolution
- let both renderers consume that

### 2. Environment scene parity is still not complete

The current lane is strongest on builder/workbench embodiment truth.

The generic environment scene layer is still more partial and should be treated as an explicit next contract-expansion task, not as "already solved because character parity improved."

### 3. The dual theaters are now useful enough to become an operating method

This is the inflection point.

The dual theaters can now support:

- browser/text comparative verification
- source vs renderer fault isolation
- staged part/chain proc-gen prep work
- future annotation and innerlay work

## Recommended Immediate Next Moves

1. checkpoint the current parity milestone
2. keep using `scripts/eval_isolation_scopes.py` as the comparative harness
3. extend `env_help` with a dual-theater isolation review playbook
4. refresh the live browser page and rerun the isolation sweep so the new scoped-board normalization is measured from live state, not only from source
5. continue closing remaining parity defects from the browser export or renderer policy layer, not by ad hoc symptom fixes
6. after the current parity lane is stable enough, move toward:
   - selective annotations
   - innerlay/load-field visualization
   - broader environment scene parity

## Bottom Line

The dual theaters are now past the point of being a novelty or a fragile debugging sidecar.

They are becoming a real comparative instrument.

That changes the value of the lane:

- less "fix the text theater because it is cool"
- more "use the paired surfaces to build and verify the next systems better"
