# Procedural Environment Generation Architecture

## Purpose

This document defines the target architecture for Champion Council's procedural environment system.

The goal is not "random scene generation." The goal is a deterministic, inspectable world-building pipeline that can:

- build rich scenes from small reusable kit vocabularies
- preserve semantic and structural coherence
- harmonize palette, material, and scale
- expose the result to the existing observer system for critique and correction
- persist and export generated worlds without inventing a second scene model

## Existing Leverage

The current runtime already contains much more of the procedural substrate than a casual reading suggests.

### 1. World Profiles

`_envWorldProfiles` already expresses:

- world family
- render base / fog / bloom
- strata
  - `surfaceLevel`
  - `waterLevel`
  - `seabedLevel`
  - `ceilingLevel`
- ecology hints
  - suggested categories
  - suggested tags
- camera presets

This is already the beginning of a world-family grammar.

### 2. Profile Kits

`_envWorldProfileKits` already expresses curated scene atoms:

- asset pack
- asset id
- world-space placement
- rotation
- height offset
- scale
- label

These are currently static kits, but structurally they are seed vocabularies for a generator.

### 3. Object Contract

The normalized object record already supports the fields a generator needs:

- spatial placement
- `appearance`
- `data`
- `semantics`
- `semantics_observation`
- `profile_kit`
- `asset_pack_id`
- `asset_id`

That means generated worlds can be represented using the same canonical object substrate as hand-authored scenes.

### 4. Procedural Geometry

The runtime already supports constructive geometry through:

- `tile`
- `substrate`

Substrate recipes already support:

- `extrude`
- `lathe`
- `tube`
- `heightmap`
- `composite`

This is already a constructive shape language, not just an asset-placement engine.

### 5. Terrain and Strata

The renderer already has:

- deterministic value-noise terrain
- world water surfaces
- seabed / ceiling / volume indicator support
- world-profile-aware strata resolution

So terrain and environmental layers do not need to be invented from scratch.

### 6. Observer System

The theater vision system already provides:

- whole-scene survey
- local probes
- material truth
- semantic truth
- layout truth
- render truth

This is the missing half of procedural generation in most systems: the generated result can already be evaluated by the same runtime that built it.

## Core Architectural Rule

Do not build a parallel scene model.

The generator must emit normal scene objects into the existing substrate:

- `prop`
- `zone`
- `tile`
- `substrate`
- `marker`
- room-like object variants when appropriate

Generation should be represented as:

1. an input recipe
2. a deterministic expansion into normal scene objects
3. optional observer-scored revisions

The canonical truth remains the object substrate plus the observer path.

## What Is Still Missing

The system has many ingredients, but it does not yet have a coherent generation stack.

### Missing Layer 1: Vocabulary Semantics

Asset packs and kits need a stronger generative vocabulary.

Each reusable atom should eventually carry:

- structural role
  - wall
  - floor
  - cliff
  - ridge
  - tower
  - bridge
  - gate
  - vegetation mass
  - accent
- scale class
  - micro
  - local
  - district
  - landmark
- connection affordances
  - edge-compatible
  - stackable
  - flankable
  - path-adjacent
  - water-adjacent
- palette family
- material response
  - preserve
  - multiply
  - replace
  - none
- semantic defaults

Without this, the generator can place things, but it cannot reason about composition.

### Missing Layer 2: Generation Recipe

There is no explicit deterministic recipe format yet for generated environments.

We need a schema that can express:

- selected world profile
- selected vocabulary packs
- generation seed
- district graph
- terrain recipe
- landmark rules
- scatter density
- palette strategy
- observer targets / quality thresholds

### Missing Layer 3: Structural Grammar

The runtime has static kits, but not yet a grammar for turning them into many coherent variations.

We need placement rules for:

- spine generation
  - path
  - river
  - ridge
  - wall
- district generation
  - gate court
  - basin
  - harbor
  - shrine core
  - market edge
  - ruin cluster
- anchor placement
  - major landmarks first
  - flanking supports second
  - filler and dressing last

### Missing Layer 4: Appearance Grammar

Current scenes can be colored, but palette is still mostly manual.

We need:

- world palette families
- material harmonization rules
- accent allocation rules
- contrast rules
- atmosphere rules

This is the path toward "small packs, huge expressive range."

### Missing Layer 5: Observer-Guided Fitness

The observer exists, but generation is not yet using it as a formal scoring loop.

We need scoring for:

- silhouette clarity
- palette coherence
- landmark hierarchy
- local asymmetry
- density balance
- dead-space detection
- unwanted repetition
- water / terrain logic
- authored vs rendered material mismatch

## Target Generation Stack

The procedural environment system should be layered like this.

### Stage A: World Family Selection

Choose:

- `world_profile`
- `seed`
- target scale
- mood / tone
- structural archetype

Examples:

- `karst_cave` + `ritual_basin`
- `murky_bayou` + `ruined_dock`
- `ancient_ruins` + `hill_sanctuary`
- `moon_surface` + `research_outpost`

### Stage B: Environmental Scaffold

Build the macroform:

- strata
- terrain field
- major water planes / channels
- ridges / cliffs / basins
- route spines

This stage should prefer:

- world profile strata
- terrain noise
- substrate recipes
- large tiles / decals

### Stage C: District Graph

Lay down semantic districts.

Examples:

- gate court
- core sanctum
- worker district
- harbor edge
- market ring
- ruins field
- cliff path

Each district should know:

- role
- density
- anchor expectations
- allowed vocabularies

### Stage D: Structural Placement

Place major structural atoms:

- walls
- gates
- towers
- bridges
- lodges
- docks
- temples
- ruins

This stage should be grammar-driven, not pure random scatter.

### Stage E: Dressing Pass

Place medium and small detail:

- rocks
- logs
- debris
- trees
- props
- banners
- fires
- stools
- crates

This is where richness comes from, but it must stay subordinate to the larger structure.

### Stage F: Appearance Pass

Apply a palette and material policy:

- dominant stone / wood / soil family
- water palette
- accent allocation
- emissive policy
- tint policy for asset-backed clones
- palette families loaded from data, not hardcoded into the runtime
- per-object `palette_role` and `palette_group` metadata on the normal appearance lane
- deterministic palette variation constrained by perceptual bounds instead of RGB jitter

### Stage G: Observer Pass

Run:

- `capture_supercam`
- `capture_probe`
- focus checks on landmarks

Extract:

- structural and visual metrics
- mismatch flags
- target revision suggestions

### Stage H: Bake / Persist

Store:

- source recipe
- generated object set
- snapshot
- observer metrics

This makes the world replayable and exportable.

## Recommended Data Model

### 1. Procedural Vocabulary Entry

Each atom should eventually be describable as:

```json
{
  "id": "tower_square_stone",
  "source": "asset",
  "asset_pack_id": "kenney-castle-kit",
  "asset_id": "tower-square-base-color",
  "roles": ["tower", "landmark", "vertical_anchor"],
  "families": ["historical", "sanctuary"],
  "scale_class": "landmark",
  "connectors": ["gate_flank", "wall_adjacent", "bridge_adjacent"],
  "palette_family": "cool_stone",
  "tint_mode": "multiply",
  "placement_hints": {
    "min_spacing": 6,
    "avoid_water": false,
    "prefer_edge": true
  }
}
```

### 2. Generation Recipe

```json
{
  "recipe_id": "moon_abbey_v1",
  "seed": 42,
  "world_profile": "moon_surface",
  "archetype": "basin_sanctuary",
  "vocabularies": ["moonfall_kit_v1"],
  "districts": [
    { "id": "gate_court", "role": "entry", "density": "medium" },
    { "id": "sanctum", "role": "core", "density": "high" }
  ],
  "palette": {
    "dominant": "cool_stone",
    "water": "deep_blue",
    "accent": "indigo_gold"
  }
}
```

### 3. Evaluation Record

```json
{
  "recipe_id": "moon_abbey_v1",
  "snapshot": "moonfall_abbey_generated_20260320",
  "observer": {
    "silhouette_score": 0.82,
    "palette_score": 0.76,
    "landmark_score": 0.88,
    "repetition_score": 0.41,
    "issues": ["water_perimeter_too_broad"]
  }
}
```

## What To Optimize For

Do not optimize for brute-force photorealism first.

Optimize for:

- strong macro silhouette
- spatial legibility
- landmark hierarchy
- local asymmetry
- palette coherence
- material consistency
- believable environmental logic
- exportable determinism

If those are right, the system will already feel much more powerful than a conventional hand-scattered demo.

## What Not To Do

- Do not create a second scene representation.
- Do not treat procedural generation as pure random placement.
- Do not start with micro-granular photoreal fragments.
- Do not solve richness by simply adding more asset packs.
- Do not separate generated metadata from the main object substrate.

## First Implementation Phases

### Phase 1: Vocabulary Registry

Create a canonical procedural vocabulary registry that maps packs/assets/recipes into role-aware atoms.

### Phase 2: Deterministic Recipe Schema

Create a generator input schema that can emit a normal scene object list.

### Phase 3: Structural Grammar

Implement a first archetype family:

- sanctuary basin
- cave chamber
- harbor cove
- swamp dock

One family is enough to prove the stack.

### Phase 4: Palette Grammar

Formalize material families and accent allocation.

### Phase 5: Observer Fitness Loop

Use the existing theater observer to critique generated scenes and produce revision hints.

## Immediate Recommendation

The best next engineering move is not to keep hand-building one-off scenes.

The best next move is:

1. define the vocabulary registry
2. define the recipe schema
3. implement one archetype generator end to end
4. run the observer against it
5. iterate on the scoring loop

That will give the project a real procedural core instead of a sequence of increasingly elaborate manual compositions.
