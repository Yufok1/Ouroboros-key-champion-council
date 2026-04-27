# Text Theater Research Synthesis 2026-04-07

## STATUS: HISTORICAL 2026-04-10

This doc references the now-removed settle workflow.
Settle was deleted on 2026-04-10; preserve this file as historical reference
only and do not use its settle-specific guidance as active doctrine.

Repo: `F:\End-Game\champion_councl`

Purpose:

- distill the recent deep-research pass into durable architectural guidance
- separate primary-source-backed signals from speculative or inflated claims
- map the strongest external ideas onto Champion Council's actual text-theater and workbench architecture

## Bottom Line

The strongest conclusion survives the research pass:

- text theater should be treated as an agent operating instrument over a live 3D runtime
- it should be attached to the command lane, not maintained as a second bespoke feature surface
- the correct scaling mechanism is a primitive-first canonical snapshot, not per-feature renderer work

The most important research-backed design choice is not "make prettier ASCII."

It is:

- make the text surface structured, truthful, current, and cheap enough to consult on every relevant operation

## What Holds Up Under Verification

### 1. ASCII/Text Rendering Is Useful, But Not Sufficient By Itself

Primary source:

- ASCIIEval (OpenReview / ICLR 2026): https://openreview.net/forum?id=qg7zOTPtg6

Verified signal:

- LLMs can extract meaningful visual semantics from text-rendered forms
- performance is real but imperfect
- longer / more complex text-visual forms can degrade reliability

Implication for Champion Council:

- text-theater `current_full` is worth having
- but it should not be the only carrier of truth
- every view should also expose machine-readable structure and compact semantic summaries

Practical rule:

- pair `current_full` with `current_compact` and `snapshot`
- do not rely on ASCII alone for correctness-critical logic

### 2. Structured Spatial Representations Matter More Than Raw Coordinates

Primary source:

- FloorplanQA (OpenReview): https://openreview.net/forum?id=HjCEvsXbNV

Verified signal:

- structured JSON/XML spatial descriptions reveal meaningful LLM reasoning gaps
- models can answer shallow spatial queries but still fail on physical consistency and constrained placement

Implication for Champion Council:

- raw transforms are not enough
- a structured spatial contract is required
- the text-theater snapshot should expose relations and primitives, not only coordinates

Practical rule:

- add a token-optimized scene/embodiment primitive contract
- make "truth classes" explicit rather than inferred from styling

### 3. Long-Horizon Spatial Reasoning Benefits From Frequent Regrounding

Primary source:

- SnorkelSpatial (Snorkel AI): https://snorkel.ai/blog/introducing-snorkelspatial/

Verified signal:

- spatial reasoning degrades as action sequences get longer
- the benchmark is 2D and diagnostic, but the memory/sequence effect is directly relevant

Implication for Champion Council:

- the agent should not depend on stale internal reconstruction of the scene after many theater mutations
- current view should be attached to relevant tool results so orientation is re-established frequently

Practical rule:

- `current` should be returned by default for theater-affecting commands
- `before_after` should be used for meaningful mutations

### 4. Scene Graph / Language Memory Is The Right Abstraction Family

Primary sources / official project references:

- SG-Nav summary + project link surfaced in search: https://www.catalyzex.com/paper/sg-nav-online-3d-scene-graph-prompting-for
- LagMemo paper page: https://huggingface.co/papers/2510.24118

Verified signal:

- online 3D scene graphs and language-grounded 3D memory materially improve navigation/planning
- verification / re-perception loops matter

Inference for Champion Council:

- a lightweight scene graph / primitive-memory layer is the right long-term parity substrate
- text theater should consume that shared structure rather than bespoke hard-coded render categories

Practical rule:

- build a token-optimized 3DSG / primitive export into `text_theater_snapshot`
- use it as shared memory for both single-agent and multi-agent operation

### 5. Agent Debugging Surfaces Need Stepwise State Inspection

Primary source:

- AgentStepper paper page: https://huggingface.co/papers/2602.06593

Verified signal:

- agent debugging becomes far easier when trajectories and intermediate state are inspectable, not hidden

Implication for Champion Council:

- the command-attached text-theater view is not a novelty layer
- it is the spatial equivalent of a debugging/inspection surface

Practical rule:

- attach current paired theater state directly to relevant tool results
- later add compare/baseline support for mutations

## What To Treat More Carefully

These themes are directionally useful but should not be allowed to over-drive the design without stronger local evidence:

- claims of absolute novelty
- remote-native / ultra-low-bandwidth bridge as a near-term priority
- a pure "shape-based ASCII renderer" arms race
- turning the text theater into a full-blown general-purpose UI product before the operator loop is solved

In other words:

- the text theater is strategically important
- but the moat is not ASCII art alone
- the moat is a truthful command-attached symbolic mirror over a live creative runtime

## Highest-Leverage Systems To Build

### 1. Command-Attached Current View

Every environment/workbench/character command that affects the theater should return:

- `current_full`
- `current_compact`
- `snapshot`
- `freshness`

This is the single highest-leverage improvement.

### 2. Primitive-First Canonical Snapshot

Extend `text_theater_snapshot` with generic primitives such as:

- point
- segment / polyline
- patch / polygon
- box
- ellipsoid / sphere
- capsule / limb
- bounds / marker / label

And explicit truth classes such as:

- bone
- scaffold
- skin_proxy
- support
- contact
- scene_object
- debug
- selection

### 3. Settle / Assert Logic Gate

The text theater should expose precondition truth clearly enough that commands can refuse invalid continuation when needed.

The first concrete version is now the source-implemented `workbench_assert_balance` gate.

### 4. Semantic Timeline Manifest

The current clip/timeline lane needs a text manifest that makes sequence review cheap:

- clip ids
- timing
- diagnostics
- anomalies
- settle risk / balance events

### 5. Shared Context / Blackboard

For multi-agent operation, the right shared surface is a transactional symbolic layer over the same canonical snapshot.

This should be built after the single-agent command-attached observation loop is solid.

## Recommended Sequence

1. fix the upstream sync-classification seams so the observation loop stays cheap
2. attach `current` text-theater state to relevant command results
3. add compare / baseline support for mutations
4. add primitive-first snapshot export
5. build semantic timeline/anomaly manifests
6. build transactional shared context for multi-agent work

## Conclusion

The research does not change the core strategy.

It sharpens it:

- the system should not chase renderer-specific complexity first
- it should build a truthful symbolic observation contract over the same live browser runtime
- the agent should receive that contract automatically through the tool/result path

That is the design with the highest leverage, the lowest maintenance burden, and the best chance of scaling to proc-gen, skins, scenes, and future unknown content.

## Live Verification 2026-04-07

The command-attached observation model is now live-verified after refresh:

- `env_control("workbench_assert_balance")` returned:
  - `current_compact`
  - `current_full`
  - `snapshot`
  - `freshness`
- the same command proved the first settle/assert gate is live, with:
  - `ASSERT: PASS`
  - `support_phase = double_support`
  - `stability_risk = 0.0529`
  - `supporting foot_l, foot_r`
- `env_control("character_get_animation_state")` also returned attached observation, confirming the path is not mutation-only

That sharpens the research-backed sequence to:

1. keep the attached current-view lane as the default operator instrument
2. fix the remaining sync-classification seam so camera-only partials stay cheap
3. move payload policy from "everything full" toward disciplined observation modes
4. then extend primitive-first coverage for proc-gen / skin / scene futures
