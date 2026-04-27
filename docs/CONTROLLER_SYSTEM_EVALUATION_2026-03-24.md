# Controller System Evaluation

Date: 2026-03-24
Baseline: `e730edb`
Scope: Evaluate proven open-source control/camera/controller systems against the current Champion Council runtime, with emphasis on reuse over reinvention.

## Baseline Constraints

Champion Council is not starting from a blank game project.

Current runtime facts:

- Browser-native Three.js runtime, not React Three Fiber.
- Frontend is a plain script bundle rooted in [static/main.js](F:\End-Game\champion_councl\static\main.js).
- Panel loads global/vendored scripts directly in [static/panel.html](F:\End-Game\champion_councl\static\panel.html:11907).
- Existing camera/editor layer already uses `OrbitControls` and `TransformControls` in [static/main.js](F:\End-Game\champion_councl\static\main.js:29711) and [static/main.js](F:\End-Game\champion_councl\static\main.js:29518).
- Existing physics seam already uses Rapier via direct ESM import in [static/main.js](F:\End-Game\champion_councl\static\main.js:21507).
- Camera rigging already has a runtime seam in [static/main.js](F:\End-Game\champion_councl\static\main.js:26952).
- Current roadmap still expects `v132` player presence on top of the restored runtime in [CHAMPION_COUNCIL_ROADMAP_2026-03-24.md](F:\End-Game\champion_councl\docs\CHAMPION_COUNCIL_ROADMAP_2026-03-24.md:115) and [CODEX_V132_SCOPE_BRIEF.md](F:\End-Game\champion_councl\docs\CODEX_V132_SCOPE_BRIEF.md:21).

Implication:

- The preferred solution builds on the existing Three.js + Rapier runtime.
- A renderer or engine swap is allowed only if we deliberately decide that browser-native embodiment is the wrong constraint.
- We should avoid adding a second control/runtime model that competes with the current scene, camera, and physics layers.

## What We Need

There are two different problems:

1. Camera/input control
- Orbit, drag-look, first-person, third-person, pointer behavior, keyboard/gamepad input mapping, attach/detach behavior, editor coexistence.

2. Embodied character control
- Capsule/body movement, collision, floor support, slope behavior, moving platforms, jump, spawn/recovery, traversal policy.

These should not be treated as the same library decision.

## Systems Evaluated

### 1. Three.js built-in controls

Relevant official controls:

- `OrbitControls`
- `PointerLockControls`
- `FirstPersonControls`

Assessment:

- `OrbitControls` is proven and already present locally.
- `PointerLockControls` is a camera control only. It is not a character controller and does not solve collision, grounding, spawn, or world physics.
- `FirstPersonControls` is also camera-centric and does not provide a world/body model.

Strengths:

- Zero renderer pivot
- Official Three.js path
- Easy to integrate into the current global-script runtime

Weaknesses:

- These are camera/input helpers, not full gameplay traversal systems.
- They do not solve the hard part of embodiment.
- They do not provide a robust answer for editor/player coexistence by themselves.

Decision:

- Keep `OrbitControls` only as the current editor/navigation baseline.
- Do not try to force Three.js built-in controls into a full character-controller role.

### 2. `camera-controls` by yomotsu

Source:

- Repo: https://github.com/yomotsu/camera-controls
- Docs: https://yomotsu.github.io/camera-controls/

What the source/docs show:

- Plain Three.js support, not R3F-only.
- `connect()` / attach-detach support.
- configurable user input maps
- built-in support for collision-aware camera behavior via `colliderMeshes`
- first-person, third-person, pointer-lock, keyboard, and input-config examples

Fit to this repo:

- Excellent fit for the current browser-native Three.js runtime.
- Replaces ad hoc camera/input behavior without replacing the renderer, scene model, or physics stack.
- Can coexist with existing scene/camera seams if adopted carefully.
- Distribution is practical for this repo: dist artifacts are published and can be vendored into `/static` without introducing a full frontend bundler.

Strengths:

- Proven camera system
- Configurable input mapping
- Explicit attach/detach lifecycle
- Works directly with Three.js scenes and DOM elements
- Strong example coverage

Weaknesses:

- Camera/input layer only
- Not a body/controller/locomotion system
- Does not solve capsule physics or movement policy on its own

Decision:

- Best immediate adoption candidate for the camera/input layer.
- Strong recommendation: replace custom camera/input logic with `camera-controls` rather than continuing to hand-roll it.

### 3. `ecctrl` by pmndrs

Source:

- Repo: https://github.com/pmndrs/ecctrl

What the source/docs show:

- Built on `react-three-fiber` and `react-three-rapier`
- Floating rigidbody capsule controller
- Small-obstacle traversal
- moving/rotating platform support
- extensive tunable props for camera distance, collision, turn speed, jump velocity, sprint, and modes
- supports click-to-move / point-to-move and first-person-like setups

Fit to this repo:

- Architecturally strong as a reference implementation.
- Poor direct fit as a drop-in, because Champion Council is not R3F.
- Adopting it directly would effectively mean introducing a second frontend/runtime paradigm.

Strengths:

- Best web-native reference found for Rapier-backed third-person character control
- Real movement/body/controller semantics, not just camera semantics
- Good configuration surface

Weaknesses:

- Tied to R3F + react-three-rapier
- Not a natural fit for the current plain-JS `static/main.js` runtime
- Direct adoption would increase runtime complexity and redundancy

Decision:

- Do not adopt directly into the current runtime.
- Use as a source/reference model if we decide to port a proven body-controller pattern into the existing runtime.
- If a future R3F lane is intentionally introduced, re-evaluate.

### 4. Babylon.js camera/input system

Source:

- Camera input docs: https://grideasy.github.io/tutorials/Customizing_Camera_Inputs

What the docs show:

- camera `attachControl()` / `detachControl()`
- composable input manager
- ability to add, remove, disable, and replace camera input modules
- custom input plugin path

Fit to this repo:

- Excellent architecture for input modularity.
- Poor fit to the current runtime because it requires a renderer/framework pivot, not a local substitution.

Strengths:

- Very good input architecture
- Cleaner camera/input modularity than raw Three.js built-ins

Weaknesses:

- Requires migrating away from the current Three.js theater runtime
- Does not satisfy the "build on top of what we already have" rule

Decision:

- Good reference for architecture
- Not the right adoption path for the current codebase

### 5. Godot `CharacterBody3D`

Source:

- Docs: https://docs.godotengine.org/en/4.1/classes/class_characterbody3d.html

What the docs show:

- dedicated character-body node
- floor snap support
- floor/wall/ceiling state queries
- motion-mode semantics
- `move_and_slide()`-style embodied movement model

Fit to this repo:

- Strongest overall embodiment solution if the long-term priority becomes game-grade traversal over browser-native continuity.
- Weak fit to the current short-term requirement because it is an engine pivot, not a runtime extension.

Strengths:

- Mature embodiment model
- Strong floor/wall/slope handling
- Better long-term answer for full games than ad hoc browser controllers

Weaknesses:

- Requires moving embodiment into Godot
- Breaks the current "one browser-native runtime" approach
- Higher migration cost

Decision:

- Keep as the strongest long-term engine option if browser-native gameplay becomes the wrong constraint.
- Do not pivot here for `v132`.

## Conclusion

There is not one single proven open-source package that cleanly solves everything for this repo as it exists today.

The strongest non-redundant stack is:

1. `camera-controls` for camera/input
2. existing Three.js scene/runtime for rendering/editor/theater
3. existing Rapier seam for physics
4. a future embodied traversal layer derived from a proven source such as `ecctrl`, not invented from scratch

That means:

- We should stop writing custom camera/input behavior.
- We should adopt a proven camera/input library.
- We should not pretend camera controls and character-body traversal are the same problem.
- We should not directly adopt an R3F controller into a non-R3F runtime.

## Recommended Decision

### Recommended now

Adopt `camera-controls` into the current Three.js runtime as the canonical camera/input layer.

Why:

- it fits the current runtime
- it is proven
- it reduces custom input/camera code immediately
- it does not create a second scene/runtime model

### Recommended next

Do not resume custom player/controller implementation until one of these is chosen explicitly:

1. Browser-native path
- Use `camera-controls` for camera/input
- Port only the minimum embodied traversal concepts from a proven Rapier controller source such as `ecctrl`
- Treat that as a bounded adaptation task, not a freeform invention task

2. Engine pivot path
- Move future embodiment/gameplay traversal into Godot
- Keep browser-native Three.js as the operator/theater/runtime surface

### Not recommended

- continuing to hand-roll camera and input behavior
- forcing `PointerLockControls` or `FirstPersonControls` to act like a full gameplay controller
- introducing R3F just for controller adoption without a deliberate runtime strategy
- pivoting to Babylon.js just to get a better input manager

## Practical Adoption Order

1. Replace `OrbitControls`-centric custom camera interaction with `camera-controls`
2. Keep editor selection/transform tools separate from active traversal mode
3. Define controller profiles at the architecture level only after the camera/input layer is stable
4. Revisit embodied traversal as a separate decision

## Repo Fit Summary

Best fit:

- `camera-controls`

Best reference, not direct adoption:

- `ecctrl`

Best full-engine embodiment option:

- Godot `CharacterBody3D`

Do not use as the core answer:

- raw Three.js built-in control helpers alone

## Primary Sources

- Three.js OrbitControls docs: https://threejs.org/docs/pages/OrbitControls.html
- Three.js PointerLockControls docs: https://threejs.org/docs/examples/en/controls/PointerLockControls.html
- Three.js FirstPersonControls docs: https://threejs.org/docs/examples/en/controls/FirstPersonControls.html
- camera-controls repo: https://github.com/yomotsu/camera-controls
- camera-controls docs: https://yomotsu.github.io/camera-controls/
- camera-controls dist artifacts: https://cdn.jsdelivr.net/npm/camera-controls/
- ecctrl repo: https://github.com/pmndrs/ecctrl
- Babylon camera input docs: https://grideasy.github.io/tutorials/Customizing_Camera_Inputs
- Godot CharacterBody3D docs: https://docs.godotengine.org/en/4.1/classes/class_characterbody3d.html
