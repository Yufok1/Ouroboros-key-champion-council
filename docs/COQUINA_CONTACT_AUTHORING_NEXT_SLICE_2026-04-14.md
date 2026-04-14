# Coquina Contact Authoring Next Slice 2026-04-14

Repo: `F:\End-Game\champion_councl`

Purpose:

- re-anchor the local Coquina lane on the smallest honest implementation step
- reduce scope from broad body/contact ambitions to persisted hands-and-feet authoring
- separate what already exists from what still needs to be built

## Bottom Line

The next Coquina step inside `champion_councl` is not a new contact system.

It is:

1. keep the existing builder/scaffold/workbench/contact substrate
2. reduce authored contact scope to:
   - `hand_l`
   - `hand_r`
   - `foot_l`
   - `foot_r`
3. promote transient `workbench_stage_contact` intent into a persisted authored-contact contract
4. surface that authored contract through the existing text-theater / blackboard / snapshot lanes

This is the shortest path back to Coquina body authoring without inventing a parallel model.

## Preflight

Do not start this slice on a fused mixed working tree.

Current repo reality includes unrelated mid-flight edits in:

- `static/main.js`
- `scripts/text_theater.py`
- `server.py`
- help registry files
- weather/query/procurement docs

This authored-contact slice should land as its own clean lane.

Operational rule:

1. checkpoint, commit, or otherwise isolate unrelated work first
2. then cut the authored-contact persistence slice as one legible change set

If this lane is welded together with unrelated weather/help/query edits, future trajectory reports will not be able to classify failures cleanly.

## What Is Already Real

### 1. Coquina doctrine already supports extension through existing seams

Verified in:

- `docs/COQUINA_PROCEDURAL_SYSTEM_SPEC.md`
- `docs/COQUINA_DATA_CONTRACTS_2026-03-24.md`
- `docs/COQUINA_BODY_AUTHORING_CONTRACTS.md`

Relevant rules:

- no parallel runtime model
- no second skeleton truth
- no second affordance system
- no second palette or render/material lane
- Coquina emits into the existing substrate

### 2. Humanoid scaffold truth already includes hands and feet

Verified in `static/main.js`:

- `_ENV_RIG_FAMILY_REGISTRY`
- `_ENV_SCAFFOLD_SLOT_REGISTRY`

For `humanoid_biped`, current scaffold/canonical truth already contains:

- `hand_l`
- `hand_r`
- `foot_l`
- `foot_r`

This means a reduced hands/feet-first lane is source-native, not a compromise invented after the fact.

### 3. Contact families already include hands and feet

Verified in `static/main.js`:

- contact target families include feet and hands
- `_envBuilderControllerContactFamiliesForBones(...)`
- controller registry already knows leg and arm chains

Verified in live text theater / snapshot:

- `foot_r` currently reads as supporting
- `hand_l` and `hand_r` already appear as real contact rows
- the blackboard/query-work lane already treats these as visible evidence

### 4. `workbench_stage_contact` is a real staging helper

Verified in `static/main.js`:

- `_envNormalizeWorkbenchStageContactSpec(...)`
- `_envWorkbenchStageContact(...)`
- `_envMountedWorkbenchSurfaceState(...)`

Current staging already provides:

- normalized target ids
- blocked / clear / success outcomes
- stage reports
- live sync
- theater session saves
- workbench snapshot exposure

### 5. Text theater already exposes the contact truth

Verified in `scripts/text_theater.py`:

- contacts section
- local embodiment contact lines
- workbench and contact summary surfaces

This means the read-side consumer work is already seeded.

## What Is Still Missing

The missing piece is not observation.

The missing piece is authored persistence.

Current source truth:

- `workbench_stage_contact` writes to `_envBuilderInteraction.support_contact_targets`
- the stage report is stored in `_envBuilderInteraction.support_contact_stage_report`
- mounted workbench state exposes those values
- text-theater snapshot carries them through `workbench.support_contact_targets` and `workbench.support_contact_stage`

But:

- `_envBuilderBlueprint(...)` does not store authored contact intent
- `workbench_save_blueprint` therefore cannot persist authored contact targets
- `workbench_load_blueprint` cannot restore them as authored body state

So the current feature is:

- a transient workbench staging helper

and not yet:

- a real Coquina body-authoring contract

## Authority Clarification

Authored contacts are not observed contact truth.

They are:

- authoring intent
- blueprint persistence
- staging guidance

They are not:

- runtime observation truth
- physics promise
- controller authority

When authored contacts and observed contacts disagree, that disagreement is evidence for the operator and the blackboard. It must not be silently auto-reconciled.

## Recommended Scope Reduction

Do not start with:

- knees
- elbows
- forearms
- hips
- torso/back/head contact families

Do not start with:

- generalized multi-contact physics
- ragdoll
- fall/catch behavior
- full parkour contact routing

Start with authored contact points only for:

1. `foot_l`
2. `foot_r`
3. `hand_l`
4. `hand_r`

Why this reduction is correct:

- these joints already exist in canonical rig/scaffold truth
- they already exist in the contact and controller families
- they are semantically legible
- they are enough to express the first useful body-authoring intentions
- knees/elbows are mostly transitional until a later higher-fidelity motion/control lane is ready

## The Smallest Honest Build

### Slice A. Define a persisted authored-contact block

Add a builder-subject / blueprint level contact-authoring block using existing canonical joint ids.

Minimal shape:

```json
{
  "authored_contacts": [
    { "joint": "foot_r", "role": "plant", "enabled": true },
    { "joint": "hand_l", "role": "brace", "enabled": true }
  ]
}
```

Rules:

- only canonical joint ids
- v1 allowed joints are hands and feet only
- `role` is authoring intent, not physics or controller contract
- v1 role enum is closed:
  - `plant`
  - `brace`
- no second contact naming system
- no second checkpoint store
- invalid rows normalize out

Normalized v1 row shape:

```json
{
  "joint": "foot_r",
  "role": "plant",
  "enabled": true
}
```

### Slice B. Make `workbench_stage_contact` operate as preview/edit surface

Keep `workbench_stage_contact`, but treat it as:

- preview of authored contact intent
- staging/editor helper
- validation surface

not as the only place the intent lives

Important:

- staged contacts are not the same as authored contacts
- edits in staging may diverge from the authored set
- that divergence should be shown explicitly, not hidden

### Slice C. Persist authored contacts in blueprint save/load

Wire the authored-contact block through:

- `_envBuilderBlueprint(...)`
- builder normalize/load path
- `workbench_save_blueprint`
- `workbench_load_blueprint`

This is the step that turns contact staging into body authoring.

Load behavior rule:

- loading a blueprint restores the authored-contact block
- loading does **not** auto-stage those contacts into `_envBuilderInteraction.support_contact_targets`
- staging remains a separate explicit operator action

This preserves operator-owned state transitions and avoids hidden runtime mutation on load.

### Slice D. Surface authored contacts in text theater and blackboard

Use existing surfaces only:

- snapshot `workbench`
- snapshot `blackboard`
- text-theater embodiment/contacts/workbench sections
- consult/blackboard query-work when contact authoring is the active objective

Do not build a new mirror or separate authoring plane.
Do not add a new top-level snapshot section.

## What To Defer

Defer until after hands/feet authored persistence is working:

- knee/elbow authored contacts
- contact subregions
- generalized support/load redistribution for all families
- automatic route/controller generation from authored contacts
- Dreamer/PAN interaction policies over authored contacts
- Coquina mutation/speciation/replay behavior over authored contacts

Those are real later lanes, but they are not the first slice.

Also defer:

- any attempt to infer route targets from authored contacts
- any authored contact pose payload
- any world-space contact-point storage

## Practical Build Order

1. isolate unrelated weather/help/query work so this lands as a clean slice
2. add an authored-contact normalizer and validator
3. add authored-contact storage to builder subject / blueprint
4. persist through save/load with old-blueprint default = `[]`
5. keep blueprint load populate-only; do not auto-stage
6. wire `workbench_stage_contact` as preview/edit/validation against the authored set
7. surface authored vs staged vs observed through existing text-theater / blackboard / snapshot paths
8. only then decide whether contact-point authoring needs a dedicated Coquina-facing command layer

## Non-Negotiable Guardrails

1. No second skeleton truth.
2. No second contact naming system.
3. No second render/debug plane.
4. No foot-only core storage format.
   - feet may remain convenient derived summaries
   - core authored storage should be generic by canonical joint id
5. No knees/elbows in v1 authored persistence.
6. Blackboard remains the visible worksheet, not the contact authority.
7. No auto-stage on blueprint load.
8. No world-space contact coordinates in the blueprint.
9. No authored pose data inside authored contacts.
10. No new top-level snapshot key for authored contacts.

## Conclusion

The shortest honest path toward Coquina body authoring is:

- hands and feet only
- persisted authored-contact intent
- existing builder/workbench/text-theater surfaces only
- authored vs staged vs observed kept visibly distinct

That gets the project back onto a real authoring lane without reopening broad physics or motion-control scope.
