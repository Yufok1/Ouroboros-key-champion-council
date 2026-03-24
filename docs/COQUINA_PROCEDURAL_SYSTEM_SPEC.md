# Coquina Procedural System Spec

Status: Draft (tightened 2026-03-24)
Date: 2026-03-24
Author: Opus (advisory architect), synthesized from Codex 5.4 research + existing architecture doc
Baseline commit: `24ace01`
Supersedes: `docs/PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md` (retained as historical design reference)

## Purpose

Define the canonical architecture for Champion Council's next-generation procedural environment system.

This system replaces the removed cave-first generator (v129u–v131b). It is not a patch on that system. It is a new foundation built on the lessons from that branch and from external research into procedural modeling, perceptual color systems, compositional scene models, and dependency-aware generation pipelines.

## Core Thesis

Procedural generation is not one algorithm. It is five cooperating systems:

1. **Coquina atoms** — reusable geometry packs for multiplicative composition
2. **Structural grammar** — rule-driven hierarchy for macro form
3. **Aspectation grammar** — detail layers affixed onto blank hulls
4. **Palette evolution** — perceptual color as a first-class generative system
5. **Observer audit loop** — score, diff, revise, re-run downstream only

Each system is independently addressable, checkpointable, and composable. The "whole" and the "granulations of the whole" are both first-class entities.

## Governing Principles

### 1. Evolving systems, not static snapshots

Every generation stage produces a checkpoint. Every checkpoint is:

- a fully self-contained, renderable world state (not just a delta)
- the seed for a new evolution branch
- replayable from the original seed + transform chain
- materializable as a standalone snapshot without replaying the full chain

The system supports both "replay from seed" and "materialize snapshot" modes.

### 2. Separation of concerns

Silhouette/mass, thematic articulation, surface detail, and color evolution are never fused into one pass. Each layer can be edited, swapped, or regenerated independently.

### 3. No parallel scene model

The generator emits normal scene objects into the existing runtime substrate (`prop`, `zone`, `tile`, `substrate`, `marker`). Generated worlds use the same object contract, the same live mirror, the same observer system as hand-authored scenes.

### 4. Theme-neutral architecture

No single biome, setting, or game mode may dictate the system's ontology. Cave, city, bayou, moon surface, ship deck — all are content expressed through the same compositional grammar. If a concept requires special-casing at the architecture level, the architecture is wrong.

### 5. Multiplicative, not additive

Small atom libraries should produce large expressive ranges through combination, not through asset count. 50 well-tagged pieces composed through grammar rules should outperform 500 hand-placed assets.

## System 1: Coquina Atoms

### What they are

Small packs of 3D geometries designed for multiplicative visual composition. Each atom is a reusable piece that connects, stacks, flanks, or fills according to its metadata.

Atoms come in three classes with different contracts:

- **Solid hull atoms**: Volumetric structural forms — slabs, pillars, blocks, cliffs, boulders, terraces. Closed/manifold geometry that defines mass and silhouette.
- **Surface hull atoms**: Open-surface blanks — facade sheets, wall planes, panel fields, floor plates, roof canopies. Not manifold, but declare consistent normals, support policy, and attachment rules.
- **Affix atoms**: Smaller forms designed to attach to hull surfaces — trims, ornament bands, braces, window frames, vent grills.

All three classes use the same base schema, but hull atoms (solid and surface) have stricter guarantees (see Hull Contract below).

### Hull Contract (required for all hull-class atoms)

**Both solid and surface hulls must declare:**

1. **Axis-aligned bounding box** at rest — the atom's natural orientation places its longest axis along a canonical direction (X, Y, or Z). `natural_orientation` declares which.
2. **At least one support surface** — the face(s) the hull rests on. Floor hulls support on bottom. Wall hulls support on bottom or back.
3. **At least one attachment surface** — the face(s) that accept affix layers. A hull with zero attachment surfaces is a dead end for the aspectation grammar.
4. **Scale envelope** — `scale_class` plus `bbox_meters` (axis-aligned extents in meters). The grammar uses this to reason about fit without loading geometry.
5. **Affordance slots** — `detail_affordances` is required, not optional. Each slot names a type and a surface direction:
   - `trim_top`, `trim_bottom`, `trim_edge` — linear affix strips
   - `opening_grid` — window/door/arch cutout positions
   - `decal_face` — projected surface detail zone
   - `scatter_base` — floor-level scatter zone
   - `rib_line` — vertical/horizontal structural rib attachment

**Additional requirements by hull subclass:**

| Requirement | Solid hull | Surface hull |
|-------------|-----------|--------------|
| Topology | Closed manifold — no open edges, no non-manifold geometry | Open surface — consistent face normals required, non-manifold edges allowed |
| `hull_subclass` | `"solid"` | `"surface"` |
| Backface policy | Backface culling safe | Must declare `backface: "cull"` or `"render"` — grammar needs to know if rear is visible |
| Thickness | Implicit (closed volume) | Must declare `thickness_mm` — zero for true planes, nonzero for thin shells |
| Support model | Rests on support surfaces | Must declare `support_mode: "gravity"` (rests) or `"mounted"` (attaches to backing structure) |

Surface hulls are first-class carriers. A facade sheet with `backface: "cull"`, `support_mode: "mounted"`, and `thickness_mm: 0` is a valid blank that accepts trims, openings, and decals on its front face.

If a hull atom fails to declare the required fields for its subclass, it is rejected at tagging time and cannot participate in grammar-driven placement.

### Atom schema

Each atom carries more than geometry. It carries semantic and physical priors:

```json
{
  "id": "wall_slab_rough_01",
  "atom_class": "hull",
  "hull_subclass": "solid",
  "source": "asset",
  "asset_pack_id": "modular-stone-kit",
  "asset_id": "wall-slab-rough",
  "roles": ["wall", "boundary", "structural"],
  "families": ["historical", "sanctuary", "fortress"],
  "scale_class": "local",
  "bbox_meters": [4.0, 3.0, 0.5],
  "natural_orientation": "vertical",
  "support_surfaces": ["bottom"],
  "attachment_surfaces": ["front", "back", "top"],
  "connectors": ["wall_adjacent", "corner_join", "gate_flank"],
  "repeatability": "tileable",
  "palette_family": "cool_stone",
  "palette_role": "dominant",
  "tint_mode": "multiply",
  "detail_affordances": ["trim_top", "trim_bottom", "decal_face", "rib_line"],
  "theme_affinity": ["medieval", "ruin", "sanctuary"],
  "placement_hints": {
    "min_spacing": 0,
    "snap_grid": 2.0,
    "prefer_edge": true,
    "avoid_water": false,
    "floor_only": false
  }
}
```

### Key metadata fields

| Field | Purpose |
|-------|---------|
| `atom_class` | `hull` or `affix` — determines which contract applies |
| `hull_subclass` | `solid` (closed manifold) or `surface` (open blank) — hull atoms only |
| `roles` | What structural/semantic function this atom serves |
| `scale_class` | micro / local / district / landmark — controls placement priority |
| `bbox_meters` | Axis-aligned extents [X, Y, Z] in meters — required for hulls |
| `natural_orientation` | How the atom wants to sit in the world |
| `support_surfaces` | Which faces need to rest on something |
| `attachment_surfaces` | Which faces accept affixed detail |
| `connectors` | Socket types for adjacency solving |
| `repeatability` | tileable / unique / mirrored — controls instancing strategy |
| `detail_affordances` | What kinds of affix layers this atom accepts (required for hulls) |
| `theme_affinity` | Which world families this atom belongs to |
| `backface` | `cull` or `render` — surface hulls only, declares rear-face visibility |
| `thickness_mm` | Shell thickness in mm (0 = true plane) — surface hulls only |
| `support_mode` | `gravity` (rests on support) or `mounted` (attaches to backing) — surface hulls only |

### Atom sources

- Existing GLB asset packs (4,771+ CC0 models) — tagged and promoted to atoms
- Constructive substrate recipes (extrude, lathe, tube, heightmap, composite) — already in the runtime
- Future: custom kit pieces authored specifically for the coquina system

### Constraint solving for composition

For local adjacency and grid-filling, use **Wave Function Collapse** (WFC):

- Define adjacency rules via connector metadata on atoms
- Run constraint propagation to fill grids/regions
- JS implementations: `kchapelier/wavefunctioncollapse`, `LingDong-/ndwfc` (Three.js + web workers)
- WFC handles local coherence; it does not replace grammar-driven macro structure

**Hard scope rule — WFC is allowed for:**
- Filling interior grids within a single grammar-placed district
- Completing adjacency patterns between hull atoms of the same scale class
- Selecting affix variations along a hull surface strip

**WFC is NOT allowed for:**
- Macro layout (world → districts)
- District-to-district adjacency or connectivity
- Cross-district structure (roads, rivers, sight lines)

These scope prohibitions are hard constraints, not advisory. If WFC is invoked at a prohibited scope, the generation pipeline must reject the request and fall back to grammar-driven placement.

**Tile-set budget:** The maximum input tile set size for a single WFC pass is a runtime-tunable parameter per world profile (default: 50 atoms in v1). This is a performance/quality knob, not an architectural law — profiles for dense urban environments may raise it, sparse wilderness profiles may lower it.

**Key lesson from external research:** WFC is excellent for local completion and constrained detail fill. It is not a substitute for hierarchical structure. Use it inside districts, not across them.

## System 2: Structural Grammar

### What it is

A rule system that produces large-scale scene hierarchy. Top-down decomposition from world → districts → structures → components.

### How it works

Inspired by **CGA Shape Grammars** (ETH Zurich, Müller et al.) but simplified for runtime evaluation:

- A JSON rule tree describes how to decompose a scene region
- Rules are 2-3 levels deep (not full CGA depth)
- Each rule selects atom types, placement patterns, and density parameters
- Rules are parameterized by world family, seed, and district role

### Rule schema (simplified)

```json
{
  "rule_id": "district_harbor",
  "role": "harbor",
  "children": [
    { "rule": "place_anchor", "atom_role": "dock", "count": [1, 3], "position": "water_edge" },
    { "rule": "place_boundary", "atom_role": "wall", "side": "inland" },
    { "rule": "scatter_fill", "atom_roles": ["crate", "barrel", "rope_coil"], "density": "medium" },
    { "rule": "place_landmark", "atom_role": "lighthouse", "count": [0, 1], "position": "promontory" }
  ]
}
```

### Generation stages (from existing architecture doc, preserved)

| Stage | Scope | Method |
|-------|-------|--------|
| A. World family selection | Profile, seed, archetype | Parameter selection |
| B. Environmental scaffold | Strata, terrain, water, ridges | World profile + noise |
| C. District graph | Semantic regions | Rule-driven layout |
| D. Structural placement | Major atoms (walls, gates, towers) | Grammar rules, anchor-first |
| E. Dressing pass | Medium/small detail | WFC fill + scatter |
| F. Appearance pass | Palette + material policy | Palette evolution system |
| G. Observer pass | Score + revision hints | Observer audit loop |
| H. Bake / persist | Recipe + objects + metrics | Checkpoint |

### Key lesson from external research

Grammars produce hierarchy. Hierarchy produces coherence. Do not solve macro structure with noise or random scatter — use rules that decompose a whole into meaningful parts. Reserve stochastic methods for leaf-level variation.

Reference: Parish & Müller 2001, Müller et al. 2006 (CGA Shape).

## System 3: Aspectation Grammar

### What it is

A two-tier layered system for articulating blank structural hulls. Tier 1 (affix) adds architectural structure. Tier 2 (detail) adds weathering, wear, and scatter. These are separate layers with different rules because trims/bands/openings operate on attachment affordances, while grime/cracks/debris operate on surface properties and proximity.

### Tier 1: Affix Layer (architectural articulation)

| Sublayer | Examples | Attach via |
|----------|----------|------------|
| **Trim** | Ribs, edge profiles, ornament bands, braces, cornices | `trim_top`, `trim_bottom`, `trim_edge` affordance slots |
| **Opening** | Windows, doors, arches, vents | `opening_grid` affordance slots |
| **Surface panel** | Panel lines, seams, mortar, plank grain | Trim sheet UV mapping on `attachment_surfaces` |

**Rules:**
- Affix atoms are selected from the same world family as the hull
- Affix atoms must declare `atom_class: "affix"` and a compatible `connectors` set
- Placement is deterministic: affordance slot + theme + seed → specific affix atom(s)
- Affixes are orientation-aware: a `trim_top` strip must match the hull's top-edge length

### Slot channels (compound affixes)

Affordance slots are not single-occupancy. Real articulation often requires compound affixes: an opening needs a frame and a lintel; an edge needs trim and a brace. To support this without uncontrolled stacking, each affordance slot type defines **channels** — ordered sub-positions that can each hold one affix atom:

| Slot type | Channels | Example |
|-----------|----------|---------|
| `opening_grid` | `cutout`, `frame`, `lintel`, `sill` | arch cutout + stone frame + keystone lintel |
| `trim_top` | `primary`, `cap` | cornice strip + cap molding |
| `trim_edge` | `primary`, `brace` | edge profile + structural brace |
| `rib_line` | `primary`, `ornament` | structural rib + decorative band |

- Each channel holds at most one affix atom — no uncontrolled stacking within a channel
- Channels are resolved in order (primary first, then secondary) — later channels can reference earlier ones for alignment
- A slot with only its primary channel filled is valid — secondary channels are optional enrichment
- The affix pass budget counts each occupied channel as one affix instance

### Tier 2: Detail Layer (weathering, wear, scatter)

| Sublayer | Examples | Apply via |
|----------|----------|-----------|
| **Wear** | Edge erosion, chipped corners, scratches | Vertex color masking or decal projection |
| **Deposit** | Moss, rust, staining, waterline marks, soot | Decal projection based on surface normal + world-up |
| **Micro scatter** | Debris, pebbles, vegetation tufts, fallen objects | `scatter_base` zones on floor-type hulls |

**Rules:**
- Detail is applied per-surface-class, not per-object. A "stone wall" surface class gets stone-appropriate wear everywhere it appears.
- Detail density is bounded by a per-layer budget (see Performance Budgets below).
- Detail never alters hull geometry — it is additive only (child meshes, decals, vertex color).
- Detail selection is theme-aware and orientation-aware: moss grows on top/north faces, rust on metal surfaces, staining below openings.

### How both tiers resolve

1. Structural grammar places hull atoms → hull declares affordance slots
2. **Affix pass:** For each hull, walk affordance slots, select affix atoms by theme + seed, attach
3. **Detail pass:** For each surface class present, apply wear/deposit rules by material + orientation, then scatter micro-detail into `scatter_base` zones
4. Both passes read the current palette checkpoint for color coherence

### Three.js implementation approach

- **Trim sheets:** Single shared texture atlas with horizontal detail bands. UV-map hull geometry strips to specific bands. Standard WebGL, draw-call efficient via shared materials.
- **Decals:** `THREE.DecalGeometry` or projected textures for wear/deposit detail.
- **Instancing:** `THREE.InstancedMesh` for repeated trim elements and micro-scatter props.
- **Layering:** Each affix and detail element is an independent child mesh or decal, not baked into the hull geometry. This preserves editability and per-layer regeneration.

### Key lesson from external research

AAA modular kit workflows (Naughty Dog, CD Projekt RED, Ubisoft) separate hull from articulation from weathering as standard practice. A sci-fi corridor hull becomes industrial, medical, or military by changing only the affix layers. Age and wear are then a separate pass on top. This is the "multiplicative visual aspectation" the user described.

## System 4: Palette Evolution

### What it is

A perceptual color system where palette states are first-class generative objects — seedable, transformable, checkpointable, and prescribable to surfaces.

### Why perceptual color space matters

The current `palette-families.json` uses raw hex colors with HSL-style bounds. This is limited:

- HSL is not perceptually uniform — rotating hue 30° from yellow produces a massive brightness shift
- Procedural variation in HSL produces unpredictable visual results
- OKLCH makes equal numerical steps produce equal perceived differences

### Target color space: OKLCH

OKLCH (Lightness, Chroma, Hue) is the cylindrical form of Oklab (Björn Ottosson, 2020):

- Perceptually uniform — arithmetic on coordinates produces perceptually proportional changes
- Now in CSS Color Level 4, supported natively in all major browsers
- Available via `culori` npm package or a ~20 line conversion function

For Three.js materials, convert OKLCH → linear sRGB at palette-generation time and apply as uniform tints to PBR materials.

Reference: Google's Material Color Utilities (`@material/material-color-utilities` on npm) provides HCT tonal palette generation for guaranteed-accessible contrast scales.

### Palette evolution model

A palette is a small set of OKLCH coordinates (seed) plus a chain of deterministic transforms:

```
seed_palette: [
  { role: "dominant", L: 0.55, C: 0.04, H: 250 },
  { role: "accent",   L: 0.65, C: 0.12, H: 45 },
  { role: "neutral",  L: 0.50, C: 0.02, H: 240 },
  { role: "reactive", L: 0.70, C: 0.08, H: 120 },
  { role: "shadow",   L: 0.30, C: 0.03, H: 260 }
]

transforms: [
  { name: "weathered", delta_C: -0.02, delta_L: -0.05 },
  { name: "corrupted", delta_H: +15, delta_C: +0.03 },
  { name: "moonlit",   delta_L: +0.10, delta_C: -0.01, delta_H: +5 }
]
```

Each transform is a deterministic function on OKLCH tuples. The full state is:

```
checkpoint = seed + [applied_transforms] + per_surface_class_bindings
```

### Prescription to surfaces

Palette state is bound to **surface classes**, not to individual objects. A surface class is defined by the combination of:

- `palette_family` (e.g., `cool_stone`, `dark_forest`)
- `palette_role` (e.g., `dominant`, `accent`, `neutral`)
- `material_class` (e.g., `stone`, `metal`, `wood`, `organic`) — optional refinement

Every scene object already has `palette_family` and `palette_role` on the appearance contract. The evolution system resolves these to concrete OKLCH colors based on the current checkpoint state. Changing the checkpoint re-colors all surfaces subscribed to that surface class.

This means:
- All "cool_stone / dominant / stone" surfaces in a scene share one **base resolved color**
- Transforms apply per surface class, not per object — "weather all stone walls" is one operation
- Per-object overrides are possible but explicit (locked color flag)
- Checkpointing captures the full surface-class → OKLCH map, not object-level assignments

### Micro-variance layer

A scene where every stone wall is exactly the same OKLCH value goes dead at scale. To keep coherence without flatness, each surface instance applies a bounded micro-variance on top of the resolved surface-class color:

```json
{
  "micro_variance": {
    "delta_L": [-0.03, +0.03],
    "delta_C": [-0.01, +0.01],
    "delta_H": [-2, +2]
  }
}
```

- Variance is seeded per-instance (object id + surface index + generation seed) — deterministic and reproducible
- Variance bounds are defined per surface class, not globally — rough stone gets more variance than polished metal
- The base checkpoint color is the canonical reference; micro-variance is additive noise, not a separate evolution state
- Variance never pushes a surface outside the palette family's `perceptual_bounds` — if the nudge would exceed bounds, it is clamped

### Checkpoint semantics

- Any palette checkpoint is a fully resolved surface-class → OKLCH color map (not just a delta)
- Any checkpoint can be the seed for a new evolution branch
- Checkpoints are compact JSON — seed array + transform list + surface-class bindings
- Diff between checkpoints = list of transform operations applied/removed + surface-class changes
- Checkpoint keys are `{scene_id}:{checkpoint_index}` — stable across re-generation

### Migration from current system

The existing `palette-families.json` can be preserved as a compatibility layer. New palette evolution operates on OKLCH coordinates and emits hex colors that the existing tint pipeline already consumes. No breaking change to the material application path.

## System 5: Observer Audit Loop

### What it is

A score → diff → revise → re-run cycle that uses the existing theater observer to evaluate generated scenes and produce targeted revision hints.

### How it works

After generation, the observer runs a battery of checks:

| Check | What it evaluates |
|-------|------------------|
| Silhouette clarity | Landmark hierarchy, skyline variation, dead-flat detection |
| Palette coherence | In-family color adherence, accent/dominant balance |
| Density balance | Structural ratio, dressing count, empty-space detection |
| Spatial legibility | Overlaps, offscreen objects, invalid positions |
| Material consistency | Tint application, palette role coverage |
| Water/terrain logic | Strata adherence, water placement appropriateness |
| Repetition | Excessive instancing without variation |

### Scoring output

```json
{
  "checkpoint_id": "harbor_cove_seed42_v3",
  "pass": true,
  "scores": {
    "silhouette": 0.82,
    "palette": 0.91,
    "density": 0.77,
    "legibility": 1.00,
    "material": 0.88,
    "terrain": 0.95,
    "repetition": 0.65
  },
  "issues": ["repetition_high_in_district_market"],
  "revision_hints": [
    { "target": "district_market", "action": "increase_atom_variation", "priority": "medium" }
  ]
}
```

### Revision model

Revision hints are not automatic rewrites. They are structured suggestions that a downstream pass can act on:

- Re-run only the affected district (dirty propagation, PDG-style)
- Swap atom selection within the same role
- Adjust density parameter
- Re-roll affix layer with a different seed

The observer does not modify the scene directly. It produces hints. The generation pipeline consumes hints on the next pass.

### Key lesson from external research

SideFX PDG/TOPs mental model: every stage produces checkpointed outputs, dirty propagation means changing an input only re-runs downstream stages, wedging fans out parameter variations.

Reference: sidefx.com/docs/houdini/tops/intro.html

## Dependency Graph

The five systems form a DAG, not a linear pipeline:

```
[World Family Selection]
        |
[Environmental Scaffold] ──── [Palette Seed]
        |                           |
[District Graph]                    |
        |                           |
[Structural Placement] ◄────── [Palette Evolution]
        |                           |
[Aspectation Pass]  ◄──────── [Palette Checkpoint]
        |                           |
[Observer Audit] ──────────► [Revision Hints]
        |                           |
[Checkpoint / Persist]         [Re-run dirty]
```

Palette evolution runs in parallel with structural placement. Observer audit can trigger re-runs of any upstream stage. Each edge carries typed checkpoint data.

This maps directly to the capsule's existing workflow engine (tool-node DAGs with dependency wiring).

## What Already Exists at `24ace01`

| Infrastructure | Status | Location |
|---------------|--------|----------|
| Object contract (palette_family, palette_role, tint_mode) | Present | `static/main.js:15873` |
| Palette family registry + validation | Present | `static/main.js:16976`, `static/palette-families.json` |
| Substrate rendering (extrude, lathe, tube, composite) | Present | `static/main.js:28001` |
| Tile rendering | Present | `static/main.js:27833` |
| World profiles (12 families) | Present | `static/main.js:24743` |
| Profile kits (curated atom placements) | Present | Already in world profile system |
| Observer system (supercam, probe, material/semantic truth) | Present | Theater vision system |
| Live mirror / shared state | Present | `static/main.js:20730` |
| Rapier physics scaffold | Present | `static/main.js:21477` |
| Asset pipeline (4,771+ GLBs, 64 packs) | Present | Asset registry + MCP tools |
| Workflow DAG engine | Present | Capsule workflow system |

## What Must Be Built

| Gap | Priority | Scope |
|-----|----------|-------|
| Atom metadata schema + tagging tool | High | Tag existing assets with roles, connectors, affordances |
| OKLCH palette conversion | High | ~20 line function or `culori` dependency |
| Palette evolution engine (seed + transforms + checkpoints) | High | New system, ~200 lines |
| Simplified rule evaluator (JSON grammar → scene objects) | High | New system, ~300 lines |
| District graph layout | Medium | Builds on world profile strata |
| WFC constraint solver integration | Medium | Use `ndwfc` or `kchapelier/wfc` |
| Trim sheet / detail atlas support | Medium | UV mapping + shared texture atlases |
| Decal projection | Medium | `THREE.DecalGeometry` integration |
| Generic scoring framework | Medium | Replaces removed cave-specific scoring |
| Revision hint consumer | Low | Consumes observer hints, triggers re-runs |

## Failure Semantics

Every generation stage must define what happens when it cannot satisfy its constraints. Silent failures or empty outputs are not acceptable — the system must downgrade gracefully and report what happened.

### Per-stage fallbacks

| Stage | Failure condition | Fallback behavior |
|-------|------------------|-------------------|
| **Structural placement** | No valid hull atom matches the grammar rule's role + theme | Skip the placement slot, emit a `missing_hull` warning in the observer log. Do not substitute a random atom. |
| **Affix pass** | Hull affordance slot has no valid affix candidate for the current theme | Leave the affordance slot empty. The hull renders cleanly without it. Emit `empty_affordance` warning. |
| **Detail pass** | Surface class has no registered wear/deposit rules | Skip detail for that surface class. Emit `no_detail_rules` warning. |
| **Micro scatter** | Scatter budget is zero or `scatter_base` zone is too small | Skip scatter. No warning needed — this is expected for small hulls. |
| **WFC fill** | Constraint propagation reaches contradiction (no valid tile) | Backtrack once. If second attempt contradicts, fall back to grammar scatter-fill for that region. Emit `wfc_fallback` warning. |
| **Palette transform** | Transform produces OKLCH values outside gamut (C < 0, L outside [0,1]) | Clamp to nearest in-gamut value. Emit `palette_clamp` info. |
| **Palette contrast** | Two surface classes in the same view resolve to indistinguishable colors (deltaE < 2.0) | Nudge the lower-priority role's chroma +0.02. If still indistinguishable, nudge lightness ±0.05. Emit `contrast_nudge` info. |
| **Over-densification** | A district exceeds its draw-call or instance budget | Stop placing. Emit `budget_exceeded` warning with the count that triggered it. Observer audit will flag this for revision. |

### Warning accumulation

Warnings are collected per-generation-pass and included in the observer audit output. A generation with more than N warnings (configurable, default 10) automatically triggers a `needs_review` flag on the checkpoint.

## Authored Override Lanes

Procedural generation must coexist with hand-authored constraints. A fully procedural world is one extreme; a fully hand-authored scene is the other. The system must support the full spectrum.

### Lock semantics

Any scene region, object, affordance slot, or palette binding can be **locked**:

- `locked: true` on a scene object → generation will not move, replace, or delete it
- `locked: true` on an affordance slot → affix pass skips that slot (hand-placed affix preserved)
- `locked: true` on a palette surface-class binding → palette evolution does not re-color that class
- `locked_region: { bounds, rule }` on a district → generation respects the region boundary, fills only unlocked space

### Constraint injection

Authors can inject constraints that override grammar defaults:

- **Force atom:** "This slot must use `wall_slab_rough_01`" — grammar skips selection, uses specified atom
- **Exclude atom:** "Never place `barrel_01` in this district" — grammar filters it from candidates
- **Pin palette:** "This wall uses `#8B7355` regardless of evolution state" — palette pass skips it
- **Density cap:** "This district has max 20 scatter objects" — scatter pass respects the cap

### Precedence

Authored overrides always win over procedural decisions. If a lock conflicts with a grammar rule, the lock takes priority and the grammar skips that placement. This is not negotiable — the generation system serves the author, not the other way around.

## Performance Budgets

Each layer has explicit budgets for the Three.js runtime. These are hard limits, not guidelines. The generation pipeline must track running totals and stop placing when a budget is hit.

### Per-layer budgets (defaults, configurable per world profile)

| Layer | Max instances | Max draw calls | Max materials | Notes |
|-------|--------------|----------------|---------------|-------|
| **Hull** | 200 | 50 | 8 | InstancedMesh batching required for repeated hulls |
| **Affix** | 500 | 30 | 4 | Shared trim-sheet material strongly preferred |
| **Detail (wear/deposit)** | 300 decals | 20 | 2 | Decal atlas, not individual textures |
| **Micro scatter** | 1000 | 10 | 3 | InstancedMesh mandatory, LOD fade at distance |
| **Palette** | n/a | 0 | 0 | Palette is uniform updates, zero draw-call cost |

### Accounting rules

- Each grammar rule and aspectation pass receives a **remaining budget** from the pipeline
- Placement functions check budget before creating geometry — never create then cull
- Budget overruns are reported as `budget_exceeded` warnings, not silent drops
- World profiles can override defaults (e.g., a "sparse desert" profile might halve scatter budget)
- The observer audit includes a budget utilization summary: `{ hull: 145/200, affix: 312/500, ... }`

### Material batching expectations

- Hull atoms sharing the same base material and palette role should merge into one `InstancedMesh`
- Affix trim strips should share a single trim-sheet atlas material per district
- Micro scatter should use at most 3 `InstancedMesh` pools per district (debris, vegetation, props)
- Decals should use a shared decal atlas, not per-decal textures

## What Not To Do

- Do not rebuild the cave generator under a new name
- Do not hardcode any single biome or theme into the system architecture
- Do not create a parallel scene model — emit into the existing object substrate
- Do not fuse silhouette/articulation/detail/color into one pass
- Do not optimize for photorealism first — optimize for compositional clarity
- Do not use RGB/HSL for palette evolution — use OKLCH
- Do not treat WFC as the whole generation system — use it only for local fill (hard scope rule, see System 1)
- Do not fuse affix (architectural articulation) with detail (weathering/wear/scatter) — they are separate layers with separate rules
- Do not allow generation to override authored locks — locks always win
- Do not exceed per-layer performance budgets — stop placing, do not create-then-cull

## Minimal First Milestone (Coquina v1)

This spec does not block v132 (player presence). v132 operates on the existing runtime and does not require procgen.

**Coquina v1 is intentionally small.** It proves the architecture end-to-end with the minimum viable content:

### v1 scope (non-negotiable)

| Component | Scope |
|-----------|-------|
| **Hull family** | 1 family — e.g., "stone wall kit" (3-5 hull atoms: wall slab, floor slab, corner piece, cap piece) |
| **Affix family** | 1 family — e.g., "stone trim kit" (3-5 affix atoms: top trim, bottom trim, edge profile, corbel) |
| **Detail family** | 1 family — e.g., "stone weathering" (edge-wear decal, moss deposit, pebble scatter) |
| **Grammar** | 1 rule tree — e.g., "courtyard" (place walls → place floor → place gate opening → dress) |
| **Palette** | 1 seed palette (5 roles) + 2 transforms (weathered, moonlit) + 1 checkpoint round-trip |
| **Observer** | 3 checks: silhouette clarity, palette coherence, budget utilization |

### v1 success criteria

1. Grammar rule tree produces a courtyard (or equivalent) from tagged hull atoms
2. Affix pass populates trim affordances on placed hulls
3. Detail pass applies wear + scatter to floor surfaces
4. Palette seed → transform → checkpoint → re-color cycle works end-to-end
5. Observer scores the result and produces at least one revision hint
6. The generated scene renders in the existing Three.js theater with no new draw-call regressions
7. All outputs use the existing scene object contract — no parallel model

### v1 does NOT include

- Multiple world families
- WFC integration
- District graph layout
- Full scoring battery
- Authored override UI (overrides work in data, but no panel UI)

### Sequencing beyond v1

After v1 proves the architecture:

1. **v1.1** — Second hull family (different biome), grammar parameterization by world family
2. **v1.2** — WFC integration for local fill within grammar districts
3. **v1.3** — Authored override lanes (lock semantics, constraint injection)
4. **v1.4** — Full observer scoring battery + revision hint consumer
5. **v1.5** — Palette evolution UI in panel (seed editor, transform preview, checkpoint browser)

Each step is independently testable and shippable.

## References

### External

- Parish & Müller 2001 — Procedural Modeling of Cities (ETH Zurich)
- Müller et al. 2006 — CGA Shape: Procedural Buildings
- Wave Function Collapse — github.com/mxgmn/WaveFunctionCollapse
- Model Synthesis — paulmerrell.org/model-synthesis/
- Oklab/OKLCH — bottosson.github.io/posts/oklab/
- Material Color Utilities — github.com/material-foundation/material-color-utilities
- OpenUSD composition — openusd.org/release/glossary.html
- PDG/TOPs — sidefx.com/docs/houdini/tops/intro.html
- Stanford activity-centric scene synthesis — graphics.stanford.edu/projects/actsynth/
- Level Design Book modular kits — book.leveldesignbook.com

### Internal

- `docs/PROCEDURAL_ENVIRONMENT_GENERATION_ARCHITECTURE_2026-03-20.md` — original architecture (retained as historical design reference)
- `docs/COQUINA_DATA_CONTRACTS_2026-03-24.md` — machine-readable contract mapping onto the existing runtime seams
- `docs/archive/rollback-2026-03-24/CODEX_V130A_TUNING_BRIEF.md` — first mention of aggregate coquina surfaces
- `docs/CHAMPION_COUNCIL_ROADMAP_2026-03-24.md` — current roadmap
- `docs/CODEX_V132_SCOPE_BRIEF.md` — current v132 brief (does not depend on this spec)

---

*Spec authored by Opus (advisory architect), 2026-03-24. Synthesized from Codex 5.4 external research, user architectural vision, existing runtime analysis at `24ace01`, and lessons from the removed cave-first branch.*
