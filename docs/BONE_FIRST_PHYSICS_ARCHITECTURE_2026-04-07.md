# Bone-First Physics Architecture 2026-04-07

Repo: `F:\End-Game\champion_councl`

Purpose:

- lock the current R&D direction for balance/load/contact work
- keep mechanics truth on bones/joints/contact patches
- prevent scaffold or future skin from becoming the authority for physics
- define the next honest execution order for carpenter-level, weight innerlay, counterbalance, and fine contact mechanics

## Core Conclusion

The right ownership model is:

1. bones/joints/contact graph own mechanics truth
2. scaffold can carry that truth when visible
3. future skin can borrow or simplify that truth for product-facing theaters

Not:

- scaffold owns physics
- skin owns physics
- text theater invents a second fake body model

The repo already leans this way.

The intended authoring order in [`docs/CHARACTER_EMBODIMENT_SPEC.md`](/F:/End-Game/champion_councl/docs/CHARACTER_EMBODIMENT_SPEC.md#L131) is:

1. skeleton truth
2. scaffold projection
3. body shell / Coquina atom population
4. surface and palette treatment
5. runtime animation/export validation

That is the right doctrine for the next lane too.

## What Already Exists

### 1. Bone-Linked Mass / Load Substrate

The current browser-side mechanics lane already computes:

- support truth
- projected center of mass
- support polygon
- stability margin / risk
- per-segment load/support scores

Key anchors:

- support plane / support record: [`static/main.js:2201`](/F:/End-Game/champion_councl/static/main.js#L2201)
- foot contact patch synthesis: [`static/main.js:2255`](/F:/End-Game/champion_councl/static/main.js#L2255)
- mass proxies from scaffold slots / bones: [`static/main.js:2507`](/F:/End-Game/champion_councl/static/main.js#L2507)
- load field computation: [`static/main.js:2547`](/F:/End-Game/champion_councl/static/main.js#L2547)
- contact/support classification: [`static/main.js:2791`](/F:/End-Game/champion_councl/static/main.js#L2791)
- motion diagnostics export: [`static/main.js:2815`](/F:/End-Game/champion_councl/static/main.js#L2815)
- mounted workbench surface export: [`static/main.js:28220`](/F:/End-Game/champion_councl/static/main.js#L28220)

This is already close to the right mechanics substrate. The main limitation is not "missing physics." The main limitation is that support seeding is still feet-first.

### 2. Contact Families Already Exist In Identity Space

The solver target list already knows about:

- feet
- knees
- hands
- head

Anchor:

- contact family targets: [`static/main.js:2169`](/F:/End-Game/champion_councl/static/main.js#L2169)

Support classification already marks feet, hands, and knees as potentially supporting:

- [`static/main.js:2856`](/F:/End-Game/champion_councl/static/main.js#L2856)

But only feet currently get real patch geometry and real load seeding:

- foot-only patch builder: [`static/main.js:2255`](/F:/End-Game/champion_councl/static/main.js#L2255)
- foot-only support filter: [`static/main.js:2562`](/F:/End-Game/champion_councl/static/main.js#L2562)

That is the next real substrate seam.

### 3. Visual Bone/Joint Carriers Already Exist

The codebase already has places to carry bone-native diagnostics:

- selected-bone CSS2D label: [`static/main.js:46347`](/F:/End-Game/champion_councl/static/main.js#L46347)
- per-bone joint overlays: [`static/main.js:46391`](/F:/End-Game/champion_councl/static/main.js#L46391)
- builder selection / joint/scaffold highlight fan-out: [`static/main.js:46771`](/F:/End-Game/champion_councl/static/main.js#L46771)
- text-theater embodiment model: [`scripts/text_theater.py:1069`](/F:/End-Game/champion_councl/scripts/text_theater.py#L1069)
- text-theater bone tree: [`scripts/text_theater.py:2510`](/F:/End-Game/champion_councl/scripts/text_theater.py#L2510)

### 4. The Existing Load Visual Is Explicitly Dormant

This is important. The current code deliberately disabled the first scaffold-tint idea:

- `_envBuilderLoadFieldVisualSpec(...)` returns `null` at [`static/main.js:46657`](/F:/End-Game/champion_councl/static/main.js#L46657)
- `load_field.overlay_visible` stays false at [`static/main.js:2754`](/F:/End-Game/champion_councl/static/main.js#L2754)

That was the correct move. The first pass looked like toy plastic and hid the actual mechanics.

## Research Signals

These sources do not dictate implementation directly, but they do sharpen the architecture.

### 1. Segment Masses Should Stay Joint-Centered

Paolo de Leva's 1996 segment-parameter adjustment remains relevant because it explicitly re-references segment mass and COM estimates to joint centers rather than remote bony landmarks.

Sources:

- PubMed: https://pubmed.ncbi.nlm.nih.gov/8872282/
- ScienceDirect: https://www.sciencedirect.com/science/article/pii/0021929095001786

Implication:

- keep segment mass and COM ownership on canonical joints / bone-linked proxies
- refine proxy densities and COM offsets there first
- do not move authority to scaffold shell color or skin vertices

### 2. Upright Balance Is Multi-Joint, Not Just Ankle Pendulum

Kilby et al. show that postural control is multivariate and that ankle-only / single-link models are too simplistic; more joints become active as stance gets harder.

Source:

- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC4431684/

Implication:

- carpenter-level and stability cannot be a foot-only or ankle-only widget
- the diagnostic lane should explicitly track ankle, knee, hip, spine, chest, neck participation
- "counterbalance" belongs in the load graph, not in a cosmetic overlay

### 3. Trunk Orientation Meaningfully Changes Limb Kinetics

Trunk inclination materially changes stance-limb joint moments during gait initiation.

Source:

- PubMed: https://pubmed.ncbi.nlm.nih.gov/23383128/

Implication:

- torso/chest/spine are not passive decorations in the balance model
- future counterbalance diagnostics should expose trunk-led compensation and moment redistribution

### 4. Foot Contact Is Not One Flat Block

Recent plantar-pressure work shows center of pressure alone is not enough, contact can be spatially complex, and heel/metatarsal sub-regions contribute separately.

Source:

- PMC: https://pmc.ncbi.nlm.nih.gov/articles/PMC10300506/

Implication:

- a single block-foot patch is not sufficient long-term
- foot contact should split into subregions at least conceptually:
  - heel
  - medial metatarsal
  - central metatarsal
  - lateral edge / toe region when available

### 5. Whole-Body / Multi-Contact Reasoning Needs Stance Combinations

Multi-contact planning/control work in humanoid robotics treats tasks in terms of changing stance combinations and point/surface contacts, not only footed locomotion.

Source:

- ScienceDirect: https://www.sciencedirect.com/science/article/pii/S0921889023000878

Implication:

- `supportingContacts` should become a generic contact-combination substrate
- contact types should include both point-like and surface-like support
- the future sequence is stance-before-motion and contact-before-surface-render, which matches the current repo better than a skin-first approach

### 6. Movement Semantics Still Matter

LIMS/Laban-Bartenieff remains useful because it keeps "how the body is moving" legible through Body / Effort / Space / Shape instead of only raw coordinates.

Source:

- LIMS: https://labaninstitute.org/about-lims/

Implication:

- the mechanics substrate should remain quantitative
- the report/manifest layer can later attach qualitative labels without becoming fake

### 7. Future Motion Reference Packs Still Have Good External Substrate

These are not immediate physics dependencies, but they remain strong future sources for comparison/reference lanes:

- BABEL: frame-aligned overlapping action labels  
  https://babel.is.tue.mpg.de/
- AIST++: dance sequences with root trajectories and music alignment  
  https://google.github.io/aistplusplus_dataset/
- AMASS: unified skeletal/body representation across many mocap sets  
  https://amass.is.tue.mpg.de/index.html

## Recommended Ownership Model

### Layer 1: Mechanics Truth

Authoritative data:

- canonical joints
- bone hierarchy
- contact patches
- support combinations
- segment mass proxies
- projected COM
- stability margin / risk
- counterbalance / leverage proxies

This layer should stay browser-truth and text-theater-truth.

### Layer 2: Diagnostic Bone Overlay

This is the first visual return lane.

The first visible load/stability overlay should live on the bones / joint helpers:

- grayscale by default
- white / light gray for stable support-bearing structure
- darker gray for passive / unloaded structure
- colored alert accents only when something is actually wrong or intentionally selected

This is where the carpenter-level system belongs first.

### Layer 3: Scaffold Carrier

Scaffold remains optional and secondary:

- can echo load/contact truth when visible
- must stay visually neutral by default
- must not become the authority for physics

### Layer 4: Skin / Product Surface

Future Coquina / body shell / surface treatment can:

- simplify the diagnostic language
- hide development-only meters
- render a cleaner product-facing look

But the skin should borrow from mechanics truth, not define it.

## Carpenter-Level System

This should not be a floating UI ornament.

It should be a per-bone gravity/support instrument.

### Minimum Honest Signals

For each important bone or chain:

- local up axis versus gravity
- local support axis versus support normal
- projected segment COM versus supporting contact column
- chain tilt relative to parent and global vertical

### First Bones That Matter

- feet
- lower legs
- upper legs
- hips
- spine
- chest
- neck / head
- shoulders / upper arms later

### First Output Form

- tiny bone-side level glyphs on helper joints
- grayscale load band along bone axis
- selected-bone readout in CSS2D label / text theater panel
- chain summary for:
  - left support stack
  - right support stack
  - torso stack

### What The Level Should Mean

Not "perfectly horizontal."

Instead:

- how aligned the local segment is with the support task it is currently serving
- whether the chain is stacked, compensating, or collapsing

Example:

- shank in planted stance: level describes plumb/support alignment
- spine in step / brace: level describes compensatory tilt and whether that compensation is controlled or risky

## Weight / Stability Innerlay

### Keep It Bone-Native

The innerlay should be attached to bone-linked geometry / helpers first.

Recommended first encoding:

- `load_share`: brightness
- `stress`: darker edge or denser hatch
- `mode`: support / passive / swing / unsupported as label and subtle accent
- `stability_risk`: chain-side accent, not full-body paint

### Suggested Visual Rule

- bones default to white/gray depth treatment
- orange/gold reserved for explicit authoring states:
  - primary
  - selected
  - hover
- red only for actual danger / overload / outside support
- scaffold remains muted

This lines up with the user's request better than the current warm-tinted body language.

## Contact Generalization

### `supportingFeet` Must Become `supportingContacts`

That means:

1. replace the foot-only filter in [`static/main.js:2562`](/F:/End-Game/champion_councl/static/main.js#L2562)
2. replace foot-only support keys with generic contact ids
3. keep left/right foot summaries as derived humanoid conveniences, not the core storage format

### Contact Patch Families

The next honest patch builders should be:

- foot sole
- knee pad / tibial front patch
- palm / hand heel patch
- forearm brace patch
- elbow point/strip patch
- hip / side patch
- back / scapular strip
- chest / sternum pad
- head patch only as last-resort collision/support family

Not every family needs high fidelity immediately.

The first honest jump is:

1. foot
2. knee
3. hand / palm
4. forearm / elbow

### Patch Shape Doctrine

Use analog approximations, not full rigid-body physics:

- point contact
- line/strip contact
- rectangular or oval surface patch
- optional multi-region patch

That is sufficient for support/load reasoning and aligns with the current browser architecture.

## Counterbalance / Leverage / Weight Shift

Keep this quasi-static and analog first.

Do not turn the repo into a fake general-purpose physics engine.

### First Honest Metrics

- segment support score
- segment stress score
- dominant support side
- chain tilt
- COM offset from support hull
- contact-to-COM moment arm proxy
- trunk compensation proxy
- brace engagement state

### Useful Derived Signals

- left/right support asymmetry
- upper/lower body counter-rotation
- compensating chain map:
  - ankle
  - knee
  - hip
  - spine
  - chest
- leverage demand estimate at:
  - ankle
  - knee
  - hip
  - shoulder / wrist later

Inference:

- a practical first counterbalance field can be derived from existing mass proxies plus contact columns, without solving a full rigid-body inverse-dynamics stack

## Fine Joint Mechanics

### Hands

Hands should not stay symbolic forever.

The first honest hand support model is:

- palm center
- thumb-side edge
- little-finger-side edge
- fingertip cluster later if needed

This supports:

- bracing against wall/floor
- crawling / rising
- object-contact preparation later

### Feet

Feet should evolve from one block to multiple functional regions:

- heel
- metatarsal center
- medial forefoot
- lateral forefoot
- toe region

This is the clean bridge from current builder support patches to future proc-gen feet and more realistic gait/brace reasoning.

### Elbows / Knees

Treat these first as limited brace contacts, not dexterous contacts:

- patch geometry
- support normal
- compression state
- slip / overload risk

## Text Theater Implication

The text theater should not own mechanics, but it should become the best corroboration surface for them.

That means:

- bone tree should show load mode / stress / support state
- embodiment pane should show chain summaries and contact-family state
- balance pane should expand from foot support into generic support combinations
- later manifests should show when counterbalance shifted from ankle-led to hip/spine-led

Current text-theater ingestion already has the right seam:

- workbench motion/load into snapshot: [`static/main.js:28959`](/F:/End-Game/champion_councl/static/main.js#L28959)
- contact patch render consumption: [`scripts/text_theater.py:1481`](/F:/End-Game/champion_councl/scripts/text_theater.py#L1481)

## Recommended Execution Order

This is the clean next sequence.

### Phase 0: Keep The Current Runtime Honest

- keep watch on the miniature/runtime-scale bug family
- do not hide floor/support contradictions
- keep mounted-body corroboration active

### Phase 1: Bone-First Visual Return

Implement the first visible carpenter-level / load innerlay on bones only.

Scope:

- revive `_envBuilderLoadFieldVisualSpec(...)`, but route the first pass to bone/joint helpers instead of scaffold tint
- convert default diagnostic palette to white/gray depth language
- keep scaffold neutral

### Phase 2: `supportingFeet` -> `supportingContacts`

Generalize support seeding and support load storage.

Scope:

- generic contact ids
- generic contact patch builders
- keep foot summaries as derived convenience values for humanoid reports

### Phase 3: Counterbalance / Leverage Metrics

Add chain-level compensation and moment-arm proxies.

Scope:

- trunk compensation
- left/right asymmetry
- joint leverage demand
- brace contribution

### Phase 4: Fine Distal Mechanics

Split feet and hands into subregions and smarter contact families.

### Phase 5: Product Simplification

Later:

- skin-facing simplified overlays
- cleaner product theaters
- optional hidden dev capsule over the same substrate

## Immediate Implementation Guidance

If implementation resumes from this doc, the first patch should not be `supportingContacts` yet.

The first patch should be:

1. bone-first carpenter-level / weight innerlay
2. grayscale bone palette
3. keep scaffold neutral
4. export the same diagnostics cleanly into text theater

Reason:

- it uses current truthful mechanics immediately
- it avoids overclaiming contact generalization before the substrate is ready
- it gives a better operator surface for the next deeper contact work

## Bottom Line

The system should keep doing analog mechanics:

- xyz axes
- mass proxies
- contact patches
- support columns
- chain tilts
- leverage / counterbalance estimates

That is more honest, more legible, and better matched to the current repo than pretending to have a full general-purpose physics engine.

Bones should own the truth.

Scaffold can carry it.

Skin can beautify it.
