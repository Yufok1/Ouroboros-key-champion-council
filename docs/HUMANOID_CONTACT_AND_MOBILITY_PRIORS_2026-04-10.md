# Humanoid Contact And Mobility Priors 2026-04-10

Purpose: seed the upcoming body-plan mechanics manifest and transition sequencer with defensible priors instead of ad hoc values.

This is not a complete human biomechanics atlas. It is a build-facing seed set for:
- joint mechanics metadata
- contact-capable body regions
- transition phase templates
- support-topology expectations

The rule is simple:
- use literature and model priors as a starting point
- keep them configurable per body plan
- never treat them as universal truths for every body, rig, or task

## What We Already Have

The current repo already contains the seed mechanics layer in [static/main.js](F:/End-Game/champion_councl/static/main.js):
- `_envBuilderPoseMechanicsSpec(...)`
- `_envBuilderClampPoseMechanics(...)`

The missing step is promotion:
- move from a small switch-based reference/clamp helper
- to a real body-plan mechanics manifest consumed by controllers and transition phases

## What The Sources Already Give Us

### 1. Lower-body joint structure is already modeled well in OpenSim

OpenSim's Gait 2392 / 2354 models are a strong seed reference for a humanoid mechanics manifest:
- 23 degrees of freedom
- lower-extremity joint definitions
- planar knee model
- explicit foot and toe segments
- realistic segment reference frames

Sources:
- https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53086215/Gait%2B2392%2Band%2B2354%2BModels
- https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53086030

Build implication:
- use OpenSim-style joint type assignments as the starting body-plan schema
- hip = ball-and-socket
- knee = primarily hinge / sagittal-plane dominant
- ankle / foot complex = bounded compound joint
- toe / forefoot = separate contact-capable region

### 2. Kneeling is not just "put the knee down"

Kneeling and hyperflexion literature reinforces the exact problem we hit in the live workbench:
- kneeling depends on flexion depth
- single-stance and double-stance kneeling are mechanically different
- anterior knee loading changes materially with kneel type
- kneeling has meaningful contact-pressure and kinematic consequences

Sources:
- https://pubmed.ncbi.nlm.nih.gov/24900891/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC4040370/
- https://pubmed.ncbi.nlm.nih.gov/21419536/

Useful build priors:
- `half_kneel` and `double_kneel` should be separate topology families
- knee contact should not be treated as a cosmetic end pose
- knee-down maneuvers must preserve realistic foot support or escalate to hand/forearm brace
- the rear foot in half-kneel should usually be ball-of-foot biased, not arbitrarily flat against the shin

### 3. Daily-living tasks already decompose into phases

Sit-to-stand and stair locomotion literature gives us phase structure directly, which maps well to the sequencer we already want:
- sit-to-stand can be decomposed into phases
- alternative stair patterns change knee loading materially
- movement strategy changes load distribution and support demand

Sources:
- https://pubmed.ncbi.nlm.nih.gov/34087893/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC8183776/
- https://pubmed.ncbi.nlm.nih.gov/17986909/

Build implication:
- treat maneuvers as phase sequences, not one-shot end poses
- use task-specific support-transfer templates rather than shortest-path interpolation

### 4. Multi-contact crawling / beyond-feet motion is already a legitimate locomotion family

Human crawling literature supports interlimb coordination as a structured behavior rather than a pose accident.

Sources:
- https://pubmed.ncbi.nlm.nih.gov/19036860/

Build implication:
- hands, forearms, knees, and feet should all be first-class contact families
- failed kneel candidates should be allowed to reclassify into crawl / tripod / scramble families
- do not globally kill a pose because it failed one intended topology

## Recommended Manifest Fields

The next mechanics manifest should carry, per joint or contact-capable region:

- `joint_type`
  - `hinge`
  - `ball`
  - `compound`
- `preferred_bend_axis`
- `x_min` / `x_max`
- `y_min` / `y_max`
- `z_min` / `z_max`
- `soft_limit`
- `clearance_group`
- `contact_family`
- `transition_phases_allowed`

### Contact families to encode early

For humanoid biped:
- `foot`
- `ball_of_foot`
- `heel`
- `knee`
- `hand`
- `forearm`
- `elbow`
- later: `hip_side`, `shoulder_side`, `back`

Important note:
- `ball_of_foot` should be treated as a distinct contact bias/state even if the scaffold foot mesh is simplified
- we already expose per-contact bias labels in the live witness surface, so the data shape is there

## Recommended Transition Templates

These should become phase templates for the transition sequencer:

### Half kneel
- unload moving leg
- swing clear
- approach knee contact
- establish knee contact
- transfer support
- stabilize

Expected topology:
- kneeling knee + opposite foot
- optional hand escalation if balance truth rejects the two-point solution

### Double kneel
- unload both legs in sequence or symmetric descent
- lower both knees
- reduce forefoot dependence
- stabilize over bilateral knee support or knee+foot mixed support

### Sit-to-stand / stand-to-sit
- preload
- forward trunk shift
- rise / lower
- transfer support
- stabilize

### Stair / step transfer
- unload
- lead-foot placement
- controlled lowering / raising
- load transfer
- stabilize

### Crawl / tripod / scramble
- alternate leader/anchor sets
- hand-first or knee-first contact acquisition
- support redistribution
- stabilize or advance

## What To Encode As Rules Right Away

These should become explicit guardrails in controller/sequencer logic:

- knees and elbows should not hyperextend
- spine extension/flexion/twist should stay bounded
- foot contact mode matters
  - flat plant
  - ball-of-foot bias
  - heel bias
- contact acquisition should be corridor-aware
  - no floor tunneling
  - no torso tunneling
  - no impossible ankle folding to fake a contact
- a maneuver may fail one topology and still be valid for another
  - example: failed `half_kneel_l` may be a valid `tripod_brace_l`

## How To Use This In The Current Slice

Immediate repo-facing use:

1. Promote `_envBuilderPoseMechanicsSpec(...)` into a manifest-backed helper.
2. Add the new metadata fields without breaking existing callers.
3. Seed the first humanoid manifest with:
   - OpenSim-style joint typing
   - existing repo angle limits
   - conservative contact-family labels
4. Use the task priors above to define early phase templates for:
   - `half_kneel_l`
   - `half_kneel_r`
   - `double_kneel`
   - `tripod_brace_l`
   - `tripod_brace_r`
5. Feed phase results into the existing `route_report` contract.

## Practical Conclusion

The project does not need to guess from zero.

We already have:
- a live load/contact/balance witness surface
- a seed mechanics spec in source
- a batch-pose mutation lane
- grouped/controller topology work

And the literature gives us enough to seed:
- joint classes
- task phases
- contact-family expectations
- a more defensible kneel/crawl/transfer sequencer

That is enough to make the next mechanics slice faster, cleaner, and less arbitrary.
