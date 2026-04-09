# Text Theater Blackboard Spec 2026-04-09

Repo: `F:\End-Game\champion_councl`

Supersedes `docs/TEXT_THEATER_PARITY_ARCHITECTURE_2026-04-07.md` for the text-theater role framing.
Does not supersede the shared-contract/snapshot architecture — that stays.

## Purpose

Reframe the text theater from "ASCII mirror of the 3D view" to **diagnostic blackboard**.

The text theater is not the text version of the web theater. It is the place where the system shows its work — visible calculations, annotated state, cross-joint dependencies, constraint checks, and prediction/corroboration traces.

The 3D theater shows the shape. The blackboard shows the reasoning.

## Design Origin

- User identified the reframe: "robot view with diagnostics, triangulation, prediction."
- Codex produced the 4-layer design and seam analysis.
- Opus added unit hygiene, tolerance bands, trend indicators, protocol framing, precedent guidance, and "why" annotations.
- This doc is the merged spec.

## Core Requirement

The blackboard must:

1. Add diagnostic value the 3D theater cannot show (math, derivations, interpretations, predictions)
2. Be structured data first, rendered surface second — the blackboard is a contract, not a template
3. Stay honest — every row traces to a computable source
4. Be dynamically populated — rows appear when relevant, disappear when not
5. Be legible under interaction stress — MFD/medical-monitor UX, not movie VFX

## Four-Layer Structure

### Layer 1: Raw

Measured/authored state, no derivation:
- Joint transforms (position, quaternion, scale)
- Camera recipe (position, target, intent, body_region)
- Contact states (joint, state, patch geometry)
- Support polygon vertices
- Gizmo basis (active axis, mode, space)
- Selected bone / selected part / focus target
- Timeline cursor, active clip, playback state
- Load field inputs (mass proxies, contact assignments)

### Layer 2: Derived

Computed from Layer 1:
- Foot-to-ground angle (pitch/roll/yaw vs support plane)
- Heel/toe clearance
- Contact patch centroid and bias (heel/toe/flat/edge)
- CoM projection along gravity onto support frame
- Signed CoM distance to each polygon edge
- Parent-relative swing/twist per selected joint
- Delta from rest pose
- Chain kinematic contribution (how much each joint affects the foot/hips/CoM)
- Support load share per contact
- Moment-arm / leverage proxy
- Selected-part screen occupancy / visibility confidence
- Stability margin, normalized margin, stability risk

### Layer 3: Interpretation

Plain-language restatement of Layer 2:
- "foot_r is toe-down by 11.2° relative to support plane"
- "CoM is 0.18m inside polygon, nearest edge rear-left"
- "selected gizmo axis rotates joint in local space, low balance risk"
- "lower_leg_l is contributing 34% of the foot's horizontal correction"
- "current pose is 4.2° past rest for foot_r pitch"

Every interpretation row carries a **why**:
- "CoM drifting backward because torso pose shifted mass behind hips"
- "Stability risk elevated because left foot sliding on support surface"

### Layer 4: Prediction / Corroboration

- "If this edit commits, expected stability margin drops from 0.84 to 0.61"
- "If prospect commits (overhead verify_balance), expected new observation: `[CoM, inside, support_polygon]`"
- "Actual margin after commit: 0.58"
- "Prediction matched within tolerance" OR "mismatch: expected 0.61, got 0.58"

This is the layer that makes the blackboard a real machine-view, not just a verbose HUD.

## Cross-Cutting Design Rules

### Rule 1: Unit Hygiene

Every numeric row carries its unit. No exceptions. Never print `0.18` without knowing whether that's meters, degrees, radians, newton-meters, or a normalized ratio.

```
stability_risk:    0.05   [0-1 normalized]
stability_margin:  1.18m
foot_r pitch:      11.2°
com_velocity:      0.42 m/s
chain torque:      2.4 N·m
```

### Rule 2: Tolerance Bands

Every measurement shows its normal range. Makes the blackboard self-interpreting.

```
stability_risk:    0.05   NORMAL    (warn > 0.30, alert > 0.60)
heel_clearance:    0.002m GROUNDED  (grounded < 0.005m)
foot_r pitch:      11.2°  WITHIN    (limit ±25°)
```

### Rule 3: Trend Indicators

Current value + direction + rate. A static snapshot isn't enough for diagnosis.

```
stability_risk:    0.05 ↓ (falling at 0.04/s)
com_margin:        0.84m ↓ (shrinking at 0.08 m/s)
foot_r pitch:      11.2° → (stable)
```

### Rule 4: Confidence / Source Marking

Rows from different sources must mark confidence. A measurement isn't the same as a prediction.

```
[MEAS] stability_risk:    0.05
[DERV] com_margin:        0.84m
[PRED] predicted_margin:  0.61m
[CORB] actual vs pred:    -0.03 (within tolerance)
```

### Rule 5: Dynamic Population

Rows appear only when relevant:
- Foot selected → foot-to-ground diagnostics show up
- Gizmo attached → gizmo basis, delta, predicted effect show up
- Scoped part mode → part bounds, camera recipe, screen occupancy show up
- Settle preview active → predicted settle changes show up
- Prospect active → expected vs observed show up
- None of those → those rows disappear

Only explicitly pinned rows persist across state changes.

### Rule 6: Constraint / Invariant Checks

First-class pass/fail rows for invariants:
```
INVARIANT both feet below CoM:        PASS
INVARIANT support polygon convex:     PASS
INVARIANT foot_r rotation ≤ limit:    FAIL (112° > 90°)
```

Failed invariants are bugs, caught at display time.

### Rule 7: "Why" Annotations

Every interpretation row carries the WHY behind its conclusion, not just the conclusion. The blackboard should teach as it reports.

### Rule 8: Multi-Scale Zoom

Overview mode: 5-10 key rows that fit on a single screen without scrolling. Drill-down mode: all rows in that section. Like ncurses system monitors (htop, glances, bpytop).

## Blackboard As Protocol, Not Renderer

The blackboard is a structured data contract in shared state, not a text template. Multiple consumers render it:

| Consumer | How it renders |
|---|---|
| Text theater | Camera-projected billboard layout (primary consumer) |
| Web HUD | Selected rows as floating annotations on the 3D view (optional) |
| Dreamer observations | Structured input for learned policies |
| env_read | Raw JSON for agent consumption |

The blackboard contract lives in `shared_state.blackboard`. The text theater is one consumer. The web theater can consume it too (lighter display). Dreamer consumes it as observation. Same data, polymorphic rendering.

## Camera-Relative Spatial Collation (Critical Architecture)

The blackboard is **not a static dump**. It is a **camera-relative spatial collation system** that re-projects and re-ranks rows on every camera change.

### Core principle

Every row has a spatial anchor in the 3D scene. As the camera orbits, the blackboard re-projects those anchors, re-ranks rows by visibility and prominence, and re-arranges the textual layout to remain readable from the current angle.

The data is the same. **What's visible**, **what's emphasized**, and **how it's arranged** are functions of the current camera pose.

When the camera frames the foot, foot diagnostics promote. When it frames the head, balance/CoM dominates. When it zooms out to scene survey, scene-level metrics take over. The orbit IS the query.

### Spatial anchor types

Every row in the blackboard contract carries an anchor:

```
anchor: { type: "bone",     id: "foot_r" }
anchor: { type: "contact",  id: "foot_l_patch" }
anchor: { type: "object",   key: "prop::table_01" }
anchor: { type: "world",    position: [x, y, z] }
anchor: { type: "screen",   position: [u, v] }   // true HUD globals
anchor: { type: "global" }                       // no spatial anchor
```

### Per-frame projection pass

On every camera change:

1. Project each anchor to screen space using the current camera matrix
2. Test frustum visibility (is the anchor in view?)
3. Compute screen-space distance to focus target (closer = more prominent)
4. Compute screen-space anchor size (for LOD selection)
5. Filter out rows whose anchors are far off-screen (or push to a side panel as directional indicators)
6. Rank surviving rows by: focused/selected → in-frustum → screen-space distance from camera target → anchor screen size
7. Run layout solver to arrange rows without overlap

### Visibility-driven row promotion

Rows compete for screen real estate. The promotion ranking:

1. **Selected/focused anchor** — always promoted to top
2. **In-frustum + close to camera target** — high promotion
3. **In-frustum + farther from target** — medium promotion
4. **Off-screen but pinned** — shown as directional indicator
5. **Off-screen and not pinned** — filtered out

### LOD by screen-space size

How much detail to show per row depends on the screen-space size of its anchor:

| Anchor screen size | Detail level |
|---|---|
| < 50 px | 1-row summary (key metric only, with unit and tolerance band) |
| 50-150 px | 3-row brief (key + trend + interpretation) |
| 150-400 px | Full detail (raw + derived + interpretation + why) |
| > 400 px | Full detail + prediction/corroboration |

### Layout solver

Rows whose anchors project to overlapping screen positions get arranged via:

- **Default**: cartography-style label avoidance with thin lines connecting rows to their anchors
- **Alternative**: grid snapping with directional indicators
- **Pinned rows**: hold their position even when other rows would overlap

The text theater renders the resolved layout as text positioned per screen-space coordinates. The web HUD can render it as floating DOM annotations. Same layout pass, different consumers.

### Off-screen handling

Rows whose anchors are off-screen have three rendering options:

1. **Filter out** (default): not shown
2. **Edge indicator**: small arrow at the screen edge pointing toward the off-screen anchor, with a one-line summary
3. **Side panel**: collapsed list of off-screen anchors with summaries (e.g., "behind: foot_l, lower_back")

Pinned rows always appear regardless of visibility.

### Why this design wins

1. **Solves the density problem.** No 200-row dump. The blackboard always shows ~10-20 relevant rows for the current camera framing.
2. **Camera becomes the query interface.** The user (or agent) orbits to interrogate. The orbit is the question.
3. **Native text-to-space correlation.** The text theater is no longer a translation of the 3D view — it's a 2D projection of the same 3D-aware system, sharing the same camera matrix.
4. **Scales to environments.** When this extends beyond a single character, the same projection logic surfaces the rows for whatever the camera is framing.
5. **Unifies with observer/prospect.** When the prospect anchor proposes a new view, it's also proposing a new blackboard layout, because the new view changes which anchors are visible and prominent.

### Performance split (CRITICAL)

This adds per-camera-change recomputation. To avoid the slideshow trap, the work must be split:

**Heavy computation** (cached, invalidated by state change only):
- Foot-to-ground angle
- Kinematic chain contribution
- CoM projection math
- Predicted commit effects
- Support polygon vertices
- Contact patch geometry

**Light computation** (runs on camera change):
- Anchor projection to screen space (matrix multiply)
- Visibility filtering (frustum test)
- LOD selection (screen-space size lookup)
- Layout solving (force-directed or grid)
- Row ranking by promotion rules

**Rule**: Camera movement triggers projection + visibility + layout. Camera movement does NOT invalidate cached diagnostics. State change triggers diagnostic recomputation. They are separate dirty flags. No exceptions.

If anyone is tempted to recompute foot-to-ground angle in the projection pass: don't. That's how the slideshow happened last time.

### Example contract row

```json
{
  "id": "foot_r_pitch",
  "anchor": { "type": "bone", "id": "foot_r" },
  "layer": "interpretation",
  "source": "DERV",
  "label": "foot_r pitch",
  "value": 11.2,
  "unit": "°",
  "tolerance": { "warn": 25, "alert": 45 },
  "tolerance_state": "WITHIN",
  "trend": { "direction": "stable", "rate": 0.0 },
  "why": "Pose adjustment to foot_r joint, no recovery needed",
  "lod": {
    "summary": "foot_r 11.2° within limit",
    "brief": "foot_r pitch 11.2° → (limit ±25°)",
    "full": "foot_r is toe-down by 11.2° relative to support plane. Within anatomical limit (±25°). No trend."
  },
  "pinned": false
}
```

The renderer picks `summary`/`brief`/`full` based on the LOD selected by the projection pass. The anchor tells the renderer where to position it.

## Design Precedents

**Not** Iron Man HUD / Predator targeting matrix / Terminator vision. Those are cinematic aspiration, not engineering guidance.

**Yes** these:
- **Aircraft MFDs (multi-function displays)** — mission-critical, dense, legible under stress, unit-bearing
- **Medical monitors** — threshold-aware, trend-showing, alarm-rich
- **Oscilloscope displays** — raw + derived + annotation layered
- **ncurses system monitors (htop, glances, bpytop)** — multi-section, live, sortable, dense without clutter

The blackboard should read as professional instrumentation, not decoration.

## Highest-Value First Additions (After Current Rebuild Slices)

Order by leverage:

### 1. Selected-Joint Gizmo Basis
- Active axis (world and local vectors)
- Mode (rotate/translate/scale), space (local/world)
- Current delta being applied while dragging
- Predicted downstream effect on CoM/stability if committed

### 2. Foot-to-Ground Angle and Clearance
- Sole plane normal vs support plane normal (pitch, roll)
- Heel and toe clearance (meters, with grounded/lifting threshold)
- Contact patch centroid + bias (heel/toe/flat/edge-loaded)

### 3. Nearest-Edge CoM Margin
- Signed distance to nearest support polygon edge
- Edge identity (front-left, rear-right, etc.)
- Dominant support side breakdown
- Moment-arm proxy

### 4. Kinematic Chain Contribution
- For the selected joint: which downstream effectors move when this joint rotates
- For the selected effector: which upstream joints are most influential
- Chain torque/leverage approximation

### 5. Predicted Effect of Current Edit
- Delta in stability_risk, margin, support polygon if current pose edit commits
- Highlights which downstream checks would change status (pass → warn, warn → alert)

### 6. Observer/Prospect Rows (When Rebuilt)
- Current observer: intent, target, focus, body region
- Current prospect: proposed intent, target, expected delta
- Last prospect outcome: confirmed / falsified / mismatch magnitude

## What Already Exists vs What's New

### EXISTS (in 444016f)
- Snapshot export path (`_envBuildTextTheaterSnapshot` at `main.js:29534`)
- Selected part surface, part camera recipes, selection visual state
- Support polygon, contact patches, CoM, balance mode in snapshot
- Text renderer consumes most of this (`scripts/text_theater.py`)
- Gizmo state reported textually (mode/space/attached)

### LATENT (infrastructure ready, not rendered)
- Gizmo basis as spatial data (not just text report)
- Joint-overlay markers (present on web, not in text render model)
- Foot-to-ground derived metrics (inputs exist, derivation not implemented)
- Kinematic chain contribution (contacts + load field exist, chain math not)

### NEW (needs to be built)
- Tolerance band annotations on every metric
- Trend indicators (requires prev/current diff per row)
- Confidence/source marking per row
- Invariant check rows
- "Why" annotation system
- Blackboard-as-protocol shared state field
- Dynamic row visibility based on active state
- Predicted-effect computation for current gizmo edit
- Prediction/corroboration history

## Placement in Rebuild Trajectory

The blackboard additions slot **after** the metadata/parity/runtime rebuild slices, not before. Specifically:

| Slice | Blackboard-relevant work |
|---|---|
| Slice 1: Motion metadata truth | No blackboard work |
| Slice 2: Parity/export/help alignment | Add `source` field to snapshot rows (confidence marking groundwork) |
| Slice 3: Runtime root-motion truth | No blackboard work |
| Slice 4: Contact-phase annotation | First derived rows (foot-to-ground, contact bias) |
| Slice 5: Observer + prospect rebuild | Observer/prospect rows, prediction/corroboration layer |
| **Slice 6: Blackboard-as-protocol** | **Pure blackboard work** — tolerance bands, trends, invariants, why annotations, dynamic population, protocol field in shared state |
| Slice 7: Tinkerbell visual (Occam's razor) | Small visual primitive only, consumes blackboard data, does not duplicate it |

Blackboard is Slice 6. It cannot ship without Slices 1-5 because the data it shows is produced there.

## Guardrails

- **No speculative rows.** Every row must trace to a computable source in shared state. No "TODO: compute this later" placeholders shipped.
- **No ASCII decoration.** No fake gizmo ornaments, no box-drawing illustrations, no flavor text. Pure instrumentation.
- **No per-feature bespoke renderers.** The blackboard is a generic layered renderer that reads the contract. Adding a new metric adds a row to the contract, not new render code.
- **Unit hygiene is not optional.** A row without its unit is a bug.
- **Tolerance bands are not optional.** A measurement without its normal range is a bug.
- **Dynamic visibility is not optional.** The blackboard must not become a static 200-row dump.
- **Performance budget.** The blackboard must not become the source of a new slideshow. Derived math that's expensive must be cached and invalidated by state dirty flags, not recomputed per frame.

## The Bottom Line

The text theater stops being a text version of the 3D theater and becomes an instrument panel. Raw measurements, derived math, plain-language interpretation, predicted effects, and corroboration against reality. Dynamically populated, unit-bearing, tolerance-aware, trend-showing, invariant-checking, source-confident.

The 3D theater shows the body. The blackboard shows the reasoning. That is the division of labor.
