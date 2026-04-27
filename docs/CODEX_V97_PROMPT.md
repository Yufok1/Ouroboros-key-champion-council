Codex Task: v97 — Spawn Race Fix, Procedural Terrain, Ground Decals

Files:
- F:\End-Game\champion_councl\static\main.js (v96)
- F:\End-Game\champion_councl\static\panel.html (version bump)
- F:\End-Game\champion_councl\static\sw.js (cache bump)

Scope: Frontend only. Do NOT edit agent_compiler.py or capsule code. No new addon script files. No new MCP tools — decals use existing env_spawn/mutate/remove.

---
MANDATORY PRE-READ

Read these sections of static/main.js before editing:

1. `_envSceneObjectPool()` at line 8356 — merges `_envScene.objects` (bootstrap) with `_envSpawnedObjects`. Currently gives bootstrap priority: iterates `_envScene.objects` first, marks keys as seen, skips spawned objects whose keys are already seen. THIS IS THE BUG — bootstrap objects may lack the `data` field, causing trigger data loss on env_spawn.

2. `_env3DInit()` at line 21111 — full 3D scene setup. Ground plane at line 21242 (120x80 PlaneGeometry, MeshStandardMaterial, y=-0.1). Grid at line 21258 (GridHelper 100x40). Lights at line 21266. Particles at line 21292.

3. `_env3DApplyTheme()` at line 19442 — theme switcher. Ground color updated at line 19451. Grid disposed/recreated at line 19453. You will need to add terrain rebuild here.

4. `_envThemes` at line 19365 — 8 theme objects. Each has: bg, fog, ground, grid1, grid2, gridOp, amb, hemi, dir, point, particle, css, bloom. You will add terrain-specific fields here.

5. `_env3DXYZFromObject()` at line 19550 — maps 0-100 coords to world XYZ. World X range: -40 to +40. World Z range: -20 to +20. Kind-dependent Y height. Decals should get Y ≈ 0.02 (just above ground).

6. `_env3DKindColors` at line 19001 — color map per kind. Add `decal` entry here.

7. `_envDefaultKindAssets` at line 15572 — GLB model map per kind. Do NOT add decal here (decals are flat geometry, not GLB models).

8. `_env3DIsAgentKind()` at line 19129 — returns true for slot/npc/chatbot/actor. Decals are NOT agents.

9. `_env3DSyncObjects()` at line 21333 — full mesh sync loop. Objects iterate at line 21421. Mesh creation at line 21440. Position at line 21483. Trigger meta at line 21455.

10. `_env3DCreateSceneObjectVisual()` — creates the Three.js mesh for a scene object. You will need to add a `decal` visual type branch here.

11. `_env3D` state object at line 18949 — add `terrain: null` here.

12. `_envNormalizeSceneObjectRecord()` at line 15608 — normalizes spawn/mutate params. The `data` field is deep-cloned at line 15613. This is where decal-specific data (radius, shape) flows through.

---
PART 1: Spawn Race Fix

Bug: `_envSceneObjectPool()` gives `_envScene.objects` (bootstrap-loaded from FelixBag) priority over `_envSpawnedObjects` (from env_spawn/mutate responses). When bootstrap runs after a spawn, the bootstrap version may lack fields like `data.trigger` that the spawned version carries, because bootstrap normalization strips or doesn't carry them.

Fix: When the same key exists in both, prefer the `_envSpawnedObjects` version — it has the freshest client-side state.

Current code at line 8356:
```javascript
function _envSceneObjectPool() {
    var pool = Array.isArray(_envScene.objects) ? _envScene.objects.slice() : [];
    var seen = {};
    pool.forEach(function (obj) {
        var key = _envSceneObjectKey(obj);
        if (key) seen[key] = true;
    });
    (_envSpawnedObjects || []).forEach(function (obj) {
        var key = _envSceneObjectKey(obj);
        if (!key || seen[key]) return;
        seen[key] = true;
        pool.push(obj);
    });
    return pool;
}
```

Replace with:
```javascript
function _envSceneObjectPool() {
    var spawnedByKey = {};
    (_envSpawnedObjects || []).forEach(function (obj) {
        var key = _envSceneObjectKey(obj);
        if (key) spawnedByKey[key] = obj;
    });
    var pool = [];
    var seen = {};
    (Array.isArray(_envScene.objects) ? _envScene.objects : []).forEach(function (obj) {
        var key = _envSceneObjectKey(obj);
        if (!key || seen[key]) return;
        seen[key] = true;
        pool.push(spawnedByKey[key] || obj);
    });
    Object.keys(spawnedByKey).forEach(function (key) {
        if (!seen[key]) {
            seen[key] = true;
            pool.push(spawnedByKey[key]);
        }
    });
    return pool;
}
```

Logic: iterate bootstrap objects first (preserving order), but substitute the spawned version when both exist. Then append spawned-only objects. This ensures trigger data, appearance overrides, and any other client-side mutations survive bootstrap re-hydration.

---
PART 2: Procedural Terrain

Replace the flat ground plane with a noise-displaced subdivided mesh. This adds visual depth without affecting gameplay (objects still use `_env3DXYZFromObject` for positioning).

A. Value noise function (place before `_env3DInit`):

Implement a simple 2D value noise with smooth interpolation. No external library needed. Use a seeded pseudo-random hash for determinism — the terrain should look the same every session.

```javascript
function _env3DValueNoise2D(x, z) {
    // Simple hash-based value noise with cosine interpolation
    // Returns 0..1
}
```

Requirements:
- Deterministic (same x,z always returns same value)
- Smooth (cosine or smoothstep interpolation between lattice points)
- Two octaves for natural variation (amplitude 1.0 at scale ~20, amplitude 0.3 at scale ~8)
- Output range 0..1

B. Terrain mesh construction (replace ground plane creation in `_env3DInit` at lines 21242-21256):

```javascript
function _env3DBuildTerrain() {
    var segX = 120, segZ = 80;
    var geo = new THREE.PlaneGeometry(120, 80, segX, segZ);
    geo.rotateX(-Math.PI / 2);
    var positions = geo.attributes.position.array;
    var colors = new Float32Array(positions.length);
    var theme = _envThemes[_envThemeId] || _envThemes['default'];
    var groundColor = new THREE.Color(theme.ground);
    var maxDisplacement = 1.2;  // gentle undulations, not mountains
    for (var i = 0; i < positions.length / 3; i++) {
        var px = positions[i * 3];
        var pz = positions[i * 3 + 2];
        // Edge fade: zero displacement at borders, full in center
        var edgeFadeX = 1.0 - Math.pow(Math.abs(px) / 60, 3);
        var edgeFadeZ = 1.0 - Math.pow(Math.abs(pz) / 40, 3);
        var edgeFade = Math.max(0, Math.min(1, edgeFadeX * edgeFadeZ));
        var n = _env3DValueNoise2D(px, pz);
        var height = (n - 0.5) * 2.0 * maxDisplacement * edgeFade;
        positions[i * 3 + 1] = height - 0.1;  // base at -0.1 like original
        // Vertex color: blend ground color with height-based variation
        var heightFactor = (height + maxDisplacement) / (2 * maxDisplacement);
        var r = groundColor.r * (0.7 + heightFactor * 0.5);
        var g = groundColor.g * (0.7 + heightFactor * 0.5);
        var b = groundColor.b * (0.7 + heightFactor * 0.5);
        colors[i * 3] = Math.min(1, r);
        colors[i * 3 + 1] = Math.min(1, g);
        colors[i * 3 + 2] = Math.min(1, b);
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    var mat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.92,
        metalness: 0.08,
        transparent: true,
        opacity: 0.85
    });
    var terrain = new THREE.Mesh(geo, mat);
    terrain.receiveShadow = true;
    return terrain;
}
```

In `_env3DInit`, replace the ground plane section (lines 21242-21256) with:
```javascript
var terrain = _env3DBuildTerrain();
scene.add(terrain);
_env3D.groundPlane = terrain;
_env3D.terrain = terrain;
```

C. Theme-reactive terrain colors — in `_env3DApplyTheme()` at line 19451:

Replace `_env3D.groundPlane.material.color.setHex(t.ground)` with a full vertex color rebuild:
```javascript
if (_env3D.terrain && _env3D.scene) {
    _env3D.scene.remove(_env3D.terrain);
    _env3D.terrain.geometry.dispose();
    _env3D.terrain.material.dispose();
    var newTerrain = _env3DBuildTerrain();
    _env3D.scene.add(newTerrain);
    _env3D.groundPlane = newTerrain;
    _env3D.terrain = newTerrain;
}
```

This rebuilds the entire terrain mesh on theme switch (same pattern as the grid at line 19453).

D. Add `terrain: null` to `_env3D` state object at line 18949.

---
PART 3: Ground Decals

A new scene object kind `decal` that renders as a flat colored disc or rectangle projected onto the ground. Spawnable via MCP:

```
env_spawn { kind: 'decal', id: 'zone-a', label: 'Danger Zone', x: 40, y: 60,
            color: '#ff2200', data: { radius: 5, shape: 'circle' } }
env_spawn { kind: 'decal', id: 'landing-pad', label: 'Pad 1', x: 70, y: 30,
            color: '#00ff88', data: { width: 8, depth: 6, shape: 'rect' } }
```

A. Decal data schema (read from `_envObjectData(obj)`):
- shape: 'circle' (default) or 'rect'
- radius: world units for circle (default 3)
- width: world units for rect (default 4)
- depth: world units for rect (default 4)
- opacity: 0..1 (default 0.5)
- border: boolean (default true) — adds a ring/rect-outline wireframe

B. Add to `_env3DXYZFromObject` switch at line 19556:
```javascript
case 'decal':     wy = 0.02; break;
```

C. Add to `_env3DKindColors` at line 19001:
```javascript
decal: 0xff4444,
```

D. Add decal visual creation in `_env3DCreateSceneObjectVisual` (or wherever primitives are constructed):

When `obj.kind === 'decal'`:
- Read data fields for shape, radius, width, depth, opacity, border
- Circle: `CircleGeometry(radius, 32)` rotated -PI/2 on X
- Rect: `PlaneGeometry(width, depth)` rotated -PI/2 on X
- Material: `MeshStandardMaterial({ color, transparent: true, opacity, depthWrite: false, side: THREE.DoubleSide })`
- If border: add a child wireframe ring/rect with `LineBasicMaterial({ color, opacity: 0.8 })`
- receiveShadow = true, castShadow = false

E. Decals should NOT be agents, should NOT have locomotion, should NOT activate triggers (they are static ground markings).

F. Decal meshes should respect theme: on theme switch, their color intensity can stay as-is (they use explicit color from spawn params).

---
PART 4: Version Bump

v96 → v97:
- panel.html: main.js?v=96 → main.js?v=97
- sw.js: CACHE_NAME = 'champion-council-v97', cached asset main.js?v=97

---
Testing

1. node --check static/main.js passes
2. node --check static/sw.js passes
3. Spawn race fix: env_spawn with data.trigger should register trigger_count immediately without needing env_mutate workaround
4. Terrain: ground shows gentle undulations, not flat. Vertex colors vary with height.
5. Theme switch ([ and ] keys): terrain rebuilds with new theme colors, no artifacts
6. Decal circle: env_spawn kind=decal, shape=circle renders flat disc on ground
7. Decal rect: env_spawn kind=decal, shape=rect renders flat rectangle on ground
8. Decal border: wireframe outline visible on decals with border=true
9. Decals receive shadows from objects above them
10. Decals do NOT block agents, do NOT activate triggers, do NOT locomote
11. Decals are removable via env_remove
12. Existing scene objects (rooms, portals, NPCs, props) render unchanged
13. Ground grid still renders on top of terrain (grid Y=0 is above terrain valleys)
14. Particles still drift correctly above terrain
15. Bloom post-processing still works
16. Camera orbit/pan/zoom unchanged

---
Constraints

- Only edit frontend files (main.js, panel.html, sw.js)
- Use var and function declarations (existing code style)
- No new addon script files
- No new MCP tools — decals use existing env_spawn/mutate/remove
- Value noise must be deterministic (no Math.random at runtime)
- Edge fade on terrain: zero displacement at world borders to meet grid edge cleanly
- Max terrain displacement 1.2 units — gentle, not mountainous
- Decal Y = 0.02 (above ground, below everything else)
- Decal depthWrite: false to prevent z-fighting with terrain
- Do NOT modify existing animation, locomotion, bloom, shadow, trigger, or room code
- Do NOT modify _env3DApplyAssetState, _env3DStoreTriggerMeta, or _env3DTriggerFire
- Do NOT change the world coordinate mapping in _env3DXYZFromObject for existing kinds
