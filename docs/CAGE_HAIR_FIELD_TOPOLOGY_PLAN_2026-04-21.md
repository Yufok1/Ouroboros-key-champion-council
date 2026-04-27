# Cage Hair Field Topology Plan 2026-04-21

Purpose:

- convert the current Cage hair lane from macro visual flair into a real field/topology substrate
- keep it continuity-shaped and queryable on the same `sequence_field -> force_wave` spine
- ground the next implementation slice in actual hair mechanics instead of vibes

## Honest Current State

Right now the live runtime is not doing true strand mechanics.

It is doing:

- four scaffold carrier slots: `hair_cap`, `hair_side_l`, `hair_side_r`, `hair_back`
- force-wave-driven lift/sweep/turbulence
- a blonde Super Saiyan equilibrium baseline
- a response continuum from gravity-led realism to audio-reactive flare
- a first-class `sequence_field.force_wave.hair_reactivity.topology` packet in source
- text-theater render hooks for `HAIR-TOPO` / `hair_topology`
- a web-theater scaffold consumer that reads topology gains

That is useful, but it is still a macro-clump proxy.
It is not yet a proper groom, strand chain, or rod bundle model.

## Continuity Resume 2026-04-21

Fresh continuity and live-theater corroboration resumed the active seam as:

- sequence: `The Cage / Cage Break`
- force: `Vitruvian Dance Mobilization System / saiyan`
- live hair lane: `flare_crown`
- live punch lane: `bursting`
- live acoustic lane: `percussive`
- pointer seam: `Selection Orientation / bone:character_runtime::mounted_primary:chest / operative_memory_alignment`

Source now has the planned topology packet and consumer path:

- `static/main.js` builds `_envTextTheaterCageHairTopology(...)`
- `sequence_field.force_wave.hair_reactivity.topology` carries the topology gains
- text theater has `HAIR-TOPO` and `hair_topology` lines
- the 3D scaffold pass reads `root_lock_gain`, `tip_flex_gain`, `radial_spread_gain`, `gravity_follow_gain`, `camera_answer_gain`, `acoustic_shiver_gain`, `friction_heat_gain`, `humidity_gain`, `surface_charge_gain`, and `damage_gain`

The remaining honest gap is visibility and fidelity, not the existence of the topology contract:

- some compact live reads still show only `hair: flare_crown / lift / sweep / tint`
- topology should be made easier to query from the blackboard / embodiment surfaces
- the current renderer remains a macro-clump proxy, not strand/rod simulation

## Science Read

### 1. Hair shape is bundle physics, not just gravity

Goldstein, Warren, and Ball model hair bundles as elastic fibers with intrinsic curvature under gravity, tension, and orientational disorder.
The important implication is that hairstyle shape is an envelope or equation-of-state problem, not just a per-strand droop problem.

Use:

- elasticity
- gravity
- bundle pressure
- orientational disorder

Reference:

- `Shape of a ponytail and the statistical physics of hair fiber bundles`
  https://pubmed.ncbi.nlm.nih.gov/22401258/

### 2. Hair friction is anisotropic and operationally important

Recent tribology work says hair friction changes with morphology, damage, humidity, cleanliness, and the cuticle direction.
The cuticle geometry makes rootward vs tipward interaction behave differently, and thermal / chemical / mechanical weathering increases friction.

That means hair should not be treated as a frictionless visual appendage.
It should have:

- root/tip directional bias
- surface wear state
- humidity sensitivity
- inter-clump contact effects

References:

- `Understanding and controlling the friction of human hair`
  https://www.sciencedirect.com/science/article/pii/S0001868625001915
- `Friction Dynamics of Straight, Curly, and Wavy Hair`
  https://pubmed.ncbi.nlm.nih.gov/38692901/

### 3. Hair mechanics are humidity and temperature sensitive

Human hair stiffness changes with humidity, temperature, and strain rate.
That means weather / heat / friction should not just recolor the hair surface; they should alter how strongly hair follows gravity, spreads radially, and damps motion.

Reference:

- `Structure and mechanical behavior of human hair`
  https://pubmed.ncbi.nlm.nih.gov/28183593/

### 4. Realistic digital hair needs rods, contact, and inverse preservation

Modern hair simulation work models hair as discrete elastic rods with frictional contact.
Inverse modeling exists specifically because a styled groom will sag incorrectly if the simulator does not preserve the intended shape under force.

That means the Saiyan problem is not "make it point up."
It is:

- preserve the authored topology
- let force answer through that topology
- avoid immediate sag-collapse when simulation starts

References:

- `Interactive Hair Simulation on the GPU using ADMM`
  https://research.nvidia.com/labs/prl/admm_hair/
- `Inverse Dynamic Hair Modeling with Frictional Contact`
  https://elan.inrialpes.fr/people/bertails/Papiers/inverseDynamicHairModeling.html

## Dragon Ball Corroboration 2026-04-21

There is not one exact official sentence that fully explains the Super Saiyan anti-gravity hair look.

The strongest honest read is a stack:

1. production simplification
2. dramatic silhouette
3. in-universe body-change trigger

### 1. Production simplification

Reporting on comments from Weekly Shonen Jump editor-in-chief Hiroyuki Nakano says Toriyama left the hair unfilled in the original black-and-white manga to reduce the weekly workload of filling black hair.

Operational implication:

- the look was born as a high-readability power silhouette
- it was never meant to begin from natural grooming realism

### 2. Dramatic silhouette

Toriyama interview reporting says Super Saiyan needed to read as a sudden massive power jump, not a subtle buff.
Separate reporting on Toriyama's first-transformation drawing says the eyes were explicitly keyed to Bruce Lee's intimidating glare.

Operational implication:

- the form should feel severe, iconic, and immediately legible
- the crown silhouette is the primary read
- realism belongs in secondary motion, not in silhouette collapse

### 3. In-universe body-change trigger

Official Dragon Ball site material consistently describes Super Saiyan as:

- hair turns gold
- hair stands straight up
- power rises sharply

Toriyama's later Q&A explanation adds a biological trigger:

- enough `S-Cells`
- then an anger/pressure trigger
- then a body change

Operational implication:

- the hair should read as an energy-state deformation
- not as ordinary hair merely being blown upward
- charge and topology should lead; gravity should answer second

## Operational Read For This Project

The current topology plan already points at the right target:

- `root_lock_gain` high
- `radial_spread_gain` high
- `surface_charge_gain` high
- `gravity_follow_gain` non-zero but subordinate
- `tip_flex_gain` present so the ends stay alive

So the rendering target is:

- crown-locked charged bundle
- cartoon-first silhouette
- realistic secondary drag / rebound / tip flex

Not:

- realistic droop with a few spikes
- or a physics-first groom that accidentally resembles Saiyan hair

## Source Notes

- Dragon Ball Official, Goten character showcase:
  https://en.dragon-ball-official.com/news/01_1226.html
- Dragon Ball Official, Hiroyuki Nakazawa on reproducing Toriyama's Super Saiyan look in 3D:
  https://en.dragon-ball-official.com/news/01_411.html
- Dragon Ball Official, 1991 Super Saiyan cover draft archive:
  https://en.dragon-ball-official.com/news/01_4154.html
- Blond-hair production rationale reported from Hiroyuki Nakano:
  https://kotaku.com/the-reason-why-super-saiyan-hair-is-blond-1823914178
  https://www.denofgeek.com/culture/dragon-ball-why-super-saiyan-hair-is-blond/
- Bruce Lee eye-line reference:
  https://www.slashfilm.com/931545/a-defining-feature-of-dragon-ball-z-was-directly-inspired-by-bruce-lee/
- Toriyama Q&A on `S-Cells` and body-change trigger:
  https://comicbook.com/anime/2017/12/02/dragon-ball-goku-first-super-saiyan/

## Operational Conclusion

The Saiyan anti-gravity read should be treated as a crown-locked charged bundle topology.

It is not just "hair goes up."

It is:

- high root lock at the crown
- radial clump spread around a dominant axis
- controlled negative space between clumps
- tips with more flex than roots
- gravity still present, but partially resisted
- field / camera / audio able to bias the envelope
- friction / heat / humidity changing how stiff, noisy, or collapsed the bundle becomes

## Proposed Runtime Model

Put this under:

- `sequence_field.force_wave.hair_reactivity.topology`

Minimum fields:

- `carrier_mode`
  - `macro_clump_proxy`
  - later `strand_chain_proxy`
  - later `rod_bundle`
- `root_lock_profile`
  - `crown_locked`
- `virtual_clump_count`
- `silhouette`
  - `crown_sweep`
  - `windswept_spike`
  - `radial_crown_spike`
- `strata`
  - `crown_spines`
  - `temple_flares`
  - `rear_sweep`
- `root_lock_gain`
- `tip_flex_gain`
- `radial_spread_gain`
- `gravity_follow_gain`
- `camera_answer_gain`
- `acoustic_shiver_gain`
- `friction_heat_gain`
- `humidity_gain`
- `surface_charge_gain`
- `damage_gain`

## Interpretation

- `root_lock_gain` preserves the authored silhouette against sag
- `tip_flex_gain` keeps the ends alive and reactive
- `radial_spread_gain` drives the "over 9000" crown flare
- `gravity_follow_gain` pulls the system back toward realism
- `camera_answer_gain` lets the hair answer lens movement and spectacle direction
- `acoustic_shiver_gain` makes the hair answer rhythm / pressure / contact bursts
- `friction_heat_gain` makes the bundle rougher, louder, and less free-sliding
- `humidity_gain` makes the bundle swell, soften, frizz, or collapse depending on the mode
- `surface_charge_gain` is the cleanest route for anti-gravity flare
- `damage_gain` captures thermal / frictional weathering and roughness

## Why This Fits The Cage

The Cage already treats force as a shared wave inherited by secondary consumers.

Hair should therefore not get its own random motion engine.
It should inherit the same phase wave while preserving its own topology:

- body = primary carrier
- hair = charged crown bundle
- aura = pressure field
- punch trails = directional burst
- text theater = query surface

## Why This Fits Continuity

This belongs on the continuity spine because it is:

- bounded
- queryable
- recoverable
- shared across text theater and web theater
- interpretable by Tinkerbell/Pan/oracle consumers

It should not become a detached graphics toy.

## Next Implementation Slice

1. Make compact embodiment / blackboard surfaces expose the topology line consistently, so the operator and agent do not need raw snapshot archaeology.
2. Add a focused query row for `hair_reactivity.topology` with silhouette, clumps, root lock, tip flex, radial spread, charge, humidity, heat, and damage.
3. Keep `hair_reactivity.topology` downstream of `force_wave`; do not let hair become an authority plane over support/contact/balance.
4. Later replace macro carriers with multi-segment clump chains.
5. After that, port audio-reactive mappings from the existing matrix-rain reactor into the same topology fields.
6. Later graduate from `macro_clump_proxy` toward `strand_chain_proxy` or `rod_bundle` only after the query surfaces stay readable.

## Cultural Read

Hair should not be hard-coded as one universal norm.
Operationally, hair is a visible social/identity signal and should be treated as a configurable silhouette language.

For this system, the useful layer is not stereotype.
It is morphology classes that can be loaded respectfully as different embodiment contracts:

- disciplined / ceremonial
- athletic / aerodynamic
- charged / ecstatic
- ornate / performative
- weathered / feral

The Saiyan lane is one charged/performative topology, not the whole ontology of hair.
