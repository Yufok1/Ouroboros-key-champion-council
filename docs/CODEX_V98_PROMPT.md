Codex Task: v98 — Snap-Grid Tiles, Substrate Recipes, PBR Material Slots

Files:
- F:\End-Game\champion_councl\static\main.js (v97)
- F:\End-Game\champion_councl\static\panel.html (version bump)
- F:\End-Game\champion_councl\static\sw.js (cache bump)

Scope: Frontend only. Do NOT edit agent_compiler.py or capsule code. No new addon script files. No new MCP tools — tiles and substrates use existing env_spawn/mutate/remove. All new kinds render through the existing `_env3DCreateSceneObjectVisual` dispatch.

---
MANDATORY PRE-READ

Read these sections of static/main.js before editing:

1. `_env3DCreateSceneObjectVisual()` at line 20586 — visual dispatch. Currently branches on room, portal, decal, and primitive. You will add `tile` and `substrate` branches here.

2. `_env3DCreateDecalVisual()` at line 20527 — reference implementation for a flat ground-level visual with fill + border children. Tiles follow a similar pattern but with height and snap alignment.

3. `_env3DVisualKeyForObject()` at line 20498 — visual key for mesh identity. Add tile and substrate cases.

4. `_env3DLabelHeightForObject()` at line 20517 — label Y offset per kind. Tiles need a low label (0.3). Substrates need height-dependent labels.

5. `_env3DXYZFromObject()` at line 19550 — coordinate mapping. Tiles snap to grid. Substrates sit on the ground like decals but with height.

6. `_env3DKindColors` at line 19001 — add tile and substrate entries.

7. `_envDefaultKindAssets` at line 15572 — do NOT add tile or substrate (they are procedural geometry, not GLB).

8. `_env3DGeometryForKind()` at line 19919 — add tile and substrate fallback geometries.

9. `_env3DApplyDecalState()` at line 20637 — reference for per-frame state updates on custom visuals.

10. `_env3DBuildTerrain()` at line 21279 — reference for procedural geometry with vertex colors.

11. `_envNormalizeSceneObjectRecord()` at line 15608 — data field flows through deep clone at line 15613.

12. `_env3D` state object at line 18949 — add `tileGrid: {}` here.

13. `_env3DIsAgentKind()` at line 19129 — tiles and substrates are NOT agents.

14. `_env3DSyncObjects()` at line 21533 — full sync loop. Mesh creation at line 21640. The hash at line 21569 does NOT include `data` — trigger and tile data are handled separately.

15. The animate loop spin exemption at line 21823 — decals don't spin. Tiles and substrates should also be exempt.

---
PART 1: Snap-Grid Tile System

Tiles are flat rectangular panels that snap to a world-space grid. Each tile can carry triggers (v96), materials, and visual effects. Think dungeon floor tiles, sci-fi deck plates, pressure pads, lava panels.

A. Tile spawn schema:

```
env_spawn {
    kind: 'tile',
    id: 'floor-a1',
    label: 'Stone Floor',
    x: 30, y: 40,
    color: '#7d8791',
    data: {
        // Grid snapping
        grid_size: 4,         // snap to 4-unit grid (default 4)
        // Tile dimensions (world units)
        width: 4,             // X extent (default = grid_size)
        depth: 4,             // Z extent (default = grid_size)
        height: 0.15,         // Y thickness (default 0.15, range 0.05–1.0)
        // Material
        material: 'stone',    // 'stone', 'sand', 'wood', 'metal', 'glass', 'lava', 'ice', 'energy'
        roughness: 0.85,      // PBR roughness override (0–1)
        metalness: 0.08,      // PBR metalness override (0–1)
        emissive: null,       // hex string for emissive glow (null = none)
        emissive_intensity: 0.3,
        // Reactive surface (optional — uses v96 trigger system)
        trigger: { ... },     // same schema as v96
        effect: { ... }       // same schema as v96
    }
}
```

B. Tile material presets — define `_env3DTileMaterials`:

```javascript
var _env3DTileMaterials = {
    stone:  { color: 0x7d8791, roughness: 0.85, metalness: 0.08, emissive: 0x000000, emissiveIntensity: 0 },
    sand:   { color: 0xb89c67, roughness: 0.92, metalness: 0.04, emissive: 0x000000, emissiveIntensity: 0 },
    wood:   { color: 0x7f5734, roughness: 0.70, metalness: 0.08, emissive: 0x000000, emissiveIntensity: 0 },
    metal:  { color: 0x888898, roughness: 0.30, metalness: 0.80, emissive: 0x000000, emissiveIntensity: 0 },
    glass:  { color: 0xaaddff, roughness: 0.05, metalness: 0.10, emissive: 0x112244, emissiveIntensity: 0.1 },
    lava:   { color: 0xff3300, roughness: 0.60, metalness: 0.20, emissive: 0xff2200, emissiveIntensity: 0.8 },
    ice:    { color: 0xcceeff, roughness: 0.10, metalness: 0.05, emissive: 0x88bbff, emissiveIntensity: 0.15 },
    energy: { color: 0x00ffaa, roughness: 0.20, metalness: 0.60, emissive: 0x00ff88, emissiveIntensity: 0.6 }
};
```

C. Grid snapping — in `_env3DXYZFromObject`, when kind is 'tile':

Tiles snap their world position to the nearest grid intersection. The grid_size comes from `_envObjectData(obj).grid_size || 4`.

```javascript
case 'tile': {
    var tileData = (obj && obj.data && typeof obj.data === 'object') ? obj.data : {};
    var gs = Math.max(1, Number(tileData.grid_size || 4));
    // Map to world coords first
    var rawX = ((Number(obj.x || 50) / 100) * 80) - 40;
    var rawZ = ((Number(obj.y || 50) / 100) * 40) - 20;
    // Snap to grid
    wx = Math.round(rawX / gs) * gs;
    wz = Math.round(rawZ / gs) * gs;
    wy = Number(tileData.height || 0.15) * 0.5;  // center of tile thickness
    break;
}
```

D. Tile visual creation — `_env3DCreateTileVisual(obj, color)`:

- Read data fields: width, depth, height, material, roughness, metalness, emissive, emissive_intensity
- Lookup material preset from `_env3DTileMaterials[data.material]`, with data overrides for roughness/metalness/emissive
- Create `BoxGeometry(width, height, depth)` — NOT a plane, a thin box with visible edges
- Apply `MeshStandardMaterial` with PBR properties from preset + overrides
- Add optional wireframe edge overlay: `EdgesGeometry` + `LineSegments` with `LineBasicMaterial({ color, opacity: 0.3 })`
- `receiveShadow = true`, `castShadow = true` (tiles cast shadow on terrain below)
- Return a Group containing the box mesh + edge overlay

E. Tile visual key:
```javascript
if (kind === 'tile') {
    var td = _envObjectData(obj);
    return 'tile:'
        + String(td.material || 'stone')
        + ':' + Number(td.width || td.grid_size || 4).toFixed(1)
        + ':' + Number(td.depth || td.grid_size || 4).toFixed(1)
        + ':' + Number(td.height || 0.15).toFixed(3)
        + ':' + String(td.emissive || '')
        + ':' + Number(td.roughness || -1).toFixed(2)
        + ':' + Number(td.metalness || -1).toFixed(2);
}
```

F. Tile state updates — `_env3DApplyTileState(mesh, obj, color, isFocused)`:

- On focus: slight emissive boost (intensity + 0.1)
- On state change (running/error/etc): map state to emissive overlay like trigger system

G. Add to `_env3DXYZFromObject` switch, `_env3DKindColors`, `_env3DGeometryForKind`, `_env3DLabelHeightForObject`, and the spin exemption.

H. Tiles participate in the v96 trigger system — `_env3DStoreTriggerMeta` already reads data.trigger from any object. No special handling needed.

---
PART 2: Substrate Recipe System

Substrates are procedurally generated 3D objects defined by a geometry recipe in their data field. This is the "3D paint" system — Claude can describe any shape as a JSON recipe and the engine builds it.

A. Substrate spawn schema:

```
env_spawn {
    kind: 'substrate',
    id: 'crystal-tower',
    label: 'Crystal Spire',
    x: 60, y: 50,
    color: '#aa44ff',
    data: {
        recipe: {
            type: 'lathe',     // geometry type (see below)
            // ... type-specific params
        },
        material: 'glass',     // preset name from _env3DTileMaterials, or 'custom'
        roughness: 0.1,        // PBR override
        metalness: 0.3,
        emissive: '#8844ff',
        emissive_intensity: 0.4,
        double_sided: false,
        cast_shadow: true,
        receive_shadow: true
    }
}
```

B. Recipe types — `_env3DBuildSubstrateGeometry(recipe)`:

Returns a `BufferGeometry` or null. All recipes produce geometry centered at origin, properly oriented.

1. **extrude** — extrude a 2D polygon along Y axis
   ```
   { type: 'extrude', points: [[x,z], [x,z], ...], height: 3, bevel: 0.1 }
   ```
   - `points`: array of [x,z] pairs defining the 2D cross-section (closed path)
   - `height`: extrusion height in world units
   - `bevel`: bevel radius (0 = sharp edges)
   - Use `THREE.Shape` from points → `THREE.ExtrudeGeometry`

2. **lathe** — spin a profile around the Y axis
   ```
   { type: 'lathe', profile: [[r,y], [r,y], ...], segments: 16 }
   ```
   - `profile`: array of [radius, y] pairs defining the cross-section silhouette
   - `segments`: number of radial segments (default 16, range 6–64)
   - Use `THREE.LatheGeometry`

3. **tube** — tube along a 3D curve
   ```
   { type: 'tube', path: [[x,y,z], [x,y,z], ...], radius: 0.3, segments: 8, radial: 6 }
   ```
   - `path`: array of [x,y,z] control points for a CatmullRom spline
   - Use `THREE.CatmullRomCurve3` → `THREE.TubeGeometry`

4. **heightmap** — noise-displaced plane for landscape panels
   ```
   { type: 'heightmap', width: 10, depth: 10, resolution: 32, amplitude: 2, frequency: 0.3, seed: 42 }
   ```
   - Creates a subdivided PlaneGeometry, displaces Y by seeded noise
   - Use `_env3DValueNoise2D` (existing) with seed offset for variety
   - Add vertex colors based on height (green low, brown mid, white high — or theme-derived)

5. **composite** — combine multiple recipes
   ```
   { type: 'composite', parts: [ { recipe: {...}, offset: [x,y,z], scale: [sx,sy,sz] }, ... ] }
   ```
   - Each part is built independently, positioned by offset, scaled, then merged via `BufferGeometryUtils.mergeGeometries` (if available) or added as children of a Group
   - Max 8 parts per composite (prevent abuse)

C. Recipe validation — `_env3DValidateRecipe(recipe)`:
- Must be a non-null object with a `type` string
- Type must be one of: extrude, lathe, tube, heightmap, composite
- Extrude: points must be array of 3+ [x,z] pairs
- Lathe: profile must be array of 2+ [r,y] pairs
- Tube: path must be array of 2+ [x,y,z] points
- Heightmap: width/depth must be > 0
- Composite: parts must be array of 1–8 objects, each with valid recipe
- Return true if valid, false otherwise

D. Substrate visual creation — `_env3DCreateSubstrateVisual(obj, color)`:
- Read recipe from `_envObjectData(obj).recipe`
- Validate with `_env3DValidateRecipe`
- If invalid: fall back to a simple SphereGeometry(0.7) as error indicator
- Build geometry via `_env3DBuildSubstrateGeometry(recipe)`
- Apply material from preset + overrides (same as tiles)
- Compute vertex normals
- receiveShadow and castShadow from data fields (default true)
- Return mesh or group

E. Substrate visual key:
```javascript
if (kind === 'substrate') {
    var sd = _envObjectData(obj);
    return 'substrate:' + JSON.stringify(sd.recipe || '') + ':' + String(sd.material || '');
}
```

F. Substrate Y position — in `_env3DXYZFromObject`:
```javascript
case 'substrate': wy = 0; break;
```
Substrates sit at ground level. Their recipe defines their own height.

G. Add to all the same registries as tiles: `_env3DKindColors`, `_env3DGeometryForKind`, `_env3DLabelHeightForObject`, spin exemption, visual dispatch.

---
PART 3: Version Bump

v97 → v98:
- panel.html: main.js?v=97 → main.js?v=98
- sw.js: CACHE_NAME = 'champion-council-v98', cached asset main.js?v=98

---
Testing

1. node --check static/main.js passes
2. node --check static/sw.js passes
3. Tile spawn: `env_spawn { kind: 'tile', id: 'test-stone', x: 50, y: 50, data: { material: 'stone', grid_size: 4 } }` renders a thin stone-colored box at grid-snapped position
4. Tile with lava material: `data: { material: 'lava' }` glows with emissive red under bloom
5. Tile with trigger: `data: { material: 'energy', trigger: { shape: 'box', width: 4, depth: 4, height: 2, events: ['enter'] }, effect: { type: 'pulse', color: '#00ff88', duration: 0.5 } }` — functions as a reactive floor panel
6. Tile grid snapping: two tiles at nearby coordinates snap to distinct grid positions, not overlapping
7. Multiple tile materials render with distinct PBR properties (metal is shiny, glass is transparent-ish, wood is rough)
8. Substrate extrude: `data: { recipe: { type: 'extrude', points: [[-1,0],[1,0],[1,1],[-1,1]], height: 3 } }` renders a rectangular column
9. Substrate lathe: `data: { recipe: { type: 'lathe', profile: [[0.5,0],[1,1],[0.8,2],[0.3,3],[0,3.5]], segments: 16 } }` renders a vase/spire shape
10. Substrate tube: `data: { recipe: { type: 'tube', path: [[0,0,0],[2,3,0],[4,1,2]], radius: 0.3 } }` renders a curved tube
11. Substrate heightmap: `data: { recipe: { type: 'heightmap', width: 10, depth: 10, amplitude: 2 } }` renders a mini terrain panel with vertex colors
12. Substrate composite: `data: { recipe: { type: 'composite', parts: [{ recipe: { type: 'extrude', points: [[-2,0],[2,0],[2,2],[-2,2]], height: 0.3 }, offset: [0,0,0] }, { recipe: { type: 'lathe', profile: [[0.2,0],[0.5,1],[0.3,2],[0,2.5]], segments: 12 }, offset: [0,0.3,0] }] } }` renders a pedestal with a spire on top
13. Invalid recipe falls back to error sphere
14. Existing scene objects (rooms, portals, NPCs, props, decals) render unchanged
15. Tiles and substrates do NOT locomote, do NOT spin, are NOT agents
16. Tiles cast and receive shadows
17. Bloom enhances emissive tiles (lava, energy, glass)
18. Tiles participate in v96 trigger system when data.trigger is present

---
Constraints

- Only edit frontend files (main.js, panel.html, sw.js)
- Use var and function declarations (existing code style)
- No new addon script files
- No new MCP tools — uses existing env_spawn/mutate/remove
- Tile grid_size minimum 1, maximum 20
- Tile height range 0.05–1.0
- Substrate recipe max 8 composite parts
- Substrate extrude min 3 points, max 64 points
- Substrate lathe min 2 profile points, max 64 points
- Substrate tube min 2 path points, max 32 points
- All procedural geometry calls computeVertexNormals() before returning
- Do NOT modify existing animation, locomotion, bloom, shadow, trigger, room, decal, or terrain code
- Do NOT modify _env3DApplyAssetState, _env3DStoreTriggerMeta, or _env3DTriggerFire
- Do NOT change coordinate mapping for existing kinds in _env3DXYZFromObject
- Tiles and substrates are exempt from the idle spin in the animate loop
