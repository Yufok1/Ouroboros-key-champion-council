# World Object Runtime — Implementation Plan

## Status: DRAFT — For review before Codex execution

## Research Basis
- Direct code read of all 4 reference lines + surrounding systems
- Codebase exploration: 35,719 line main.js, all object/render/animate paths
- Web research: Three.js InstancedMesh, ShaderMaterial, DataTexture, TransformControls, LOD, AnimationMixer patterns
- Live MCP tool schema inspection (env_spawn, env_read, env_mutate)

## Goal
Add a behavior layer to the environment system so objects can have reactive mechanics (wind, sprite influence, procedural animation). First visible target: moving grass that reacts when sprites walk through it.

---

## Current Architecture (what exists)

### Object Contract (`_envNormalizeSceneObjectRecord`, main.js:15615)
```
{ kind, id, label, meta, state, category,
  x, y, scale, tilt,
  appearance: { color, geometry, asset_ref, lod_levels, material },
  collision_policy, data, html, items, actions, panelMode, slot, source }
```

### Appearance Pipeline
- `_envNormalizeSceneAppearanceRecord` (line 15541): Normalizes color, geometry, asset_ref, lod_levels, material
- `_env3DPrimitiveMaterialSource` (line 19259): Resolves material from data + appearance
- `_env3DResolveProceduralMaterial` (line 19276): Material lookup from tile material table

### Asset Loading
- `_envLoadAsset` (line 21572): GLB/GLTF loader with cache, clone, animation extraction
- `_envCloneAsset` (line 21558): SkeletonUtils.clone for animated models
- AnimationMixer CREATED at line 21918, initial clip resolved and played at line 21929, crossfade logic in animate loop at line 22714 — **already works, do NOT re-add playback**

### Scene Sync
- `_env3DSyncObjects` (line 22312): Main sync — hash-based change detection, mesh creation/update, nav grid rebuild
- `_env3DAnimate` (line 22620): Per-frame loop — dt/time, rotation, float, pulse, agent animation, mixer updates

### Established Patterns (reusable)
- **InstancedMesh**: Room walls at line 20518 (BoxGeometry + setMatrixAt with dummy Object3D)
- **AnimationMixer**: GLB animations at line 21918
- **Movement**: _moving/walkTo grid routing with walk/idle clip switching

### NOT Present (all new)
- No Raycaster or 3D click-picking
- No TransformControls (gizmo editing)
- No ShaderMaterial or custom GLSL
- No DataTexture (influence field)
- No vegetation/foliage/grass kind
- No `mechanics` or `behavior` block on objects

### Environment
- Three.js r150+ as global `THREE` (UMD bundle: `/static/three.min.js`)
- Addons loaded as globals: OrbitControls, CSS2DRenderer, GLTFLoader, EffectComposer, UnrealBloomPass, SkeletonUtils
- New addons need a `.js` file in `/static/` + a `<script>` tag in panel.html

---

## Implementation Plan — 5 Batches

### BATCH 1: Object Contract Extension (mechanics block)

**Goal:** Add a first-class `mechanics` block to the object contract so objects can declare behavior families and parameters.

**Touch points:**
1. `_envNormalizeSceneObjectRecord` (line 15615) — add `mechanics` field to the normalized record
2. `_envNormalizeSceneAppearanceRecord` (line 15541) — no change needed (appearance stays visual-only)
3. `_envMutateObject` (line 15999) — already merges full record, no change needed
4. `_envSpawnObject` (line ~15982) — already calls normalize, no change needed

**Schema for `mechanics`:**
```javascript
mechanics: {
    family: 'foliage',        // foliage | cloth | water | surface | prop | ambient_fx | null
    wind: {
        enabled: true,
        strength: 0.5,        // 0-1, how much wind affects this object
        frequency: 1.0,       // oscillation speed multiplier
        direction: [1, 0]     // wind direction (x, z) normalized
    },
    reaction: {
        enabled: true,
        radius: 2.0,          // world-space radius for sprite influence
        strength: 0.8,        // how much sprites push this object
        recovery: 3.0         // seconds to spring back
    },
    lod: {
        near: 20,             // full detail distance
        mid: 50,              // simplified distance
        far: 100              // minimal/billboard distance
    }
}
```

**Normalization function (new):**
```javascript
function _envNormalizeSceneMechanics(sources) {
    // Merge from: prev.mechanics, data.mechanics, params.mechanics
    // Returns normalized mechanics object or null if no behavior
}
```

**Contract extension in `_envNormalizeSceneObjectRecord`:**
```javascript
// After collision_policy, before return
var mechanics = _envNormalizeSceneMechanics([
    prev ? prev.mechanics : null,
    (rawData || {}).mechanics,
    p.mechanics
]);
// Add to return object:
mechanics: mechanics,
```

5. **Inspector rendering** — the summary metrics are capped at 3 entries (`metrics.slice(0, 3)` at line 17748), so do NOT push mechanics into the summary metrics array. Instead, add a dedicated inspector **section** for mechanics via `_envCollectInspectorView` (line 17756). After the existing section assembly in that function, add a mechanics section:
```javascript
// In _envCollectInspectorView, after existing sections:
var mechanics = obj.mechanics || null;
if (mechanics && mechanics.family) {
    var mechHtml = _envInspectorMetric('Family', String(mechanics.family));
    if (mechanics.wind && mechanics.wind.enabled) {
        mechHtml += _envInspectorMetric('Wind', String(mechanics.wind.strength || 0));
    }
    if (mechanics.reaction && mechanics.reaction.enabled) {
        mechHtml += _envInspectorMetric('Reaction', String(mechanics.reaction.radius || 0) + 'm');
    }
    sections.push(_envInspectorSection('mechanics', 'Mechanics', mechHtml));
}
```
   This uses the existing section infrastructure (`_envInspectorSection` at line 17668) instead of fighting the 3-metric cap.

**Codex scope:** ~65 lines of new code. Data normalization + inspector section.

---

### BATCH 2: Vegetation Patch Renderer (InstancedMesh + ShaderMaterial + wind)

**Goal:** New `vegetation_patch` object kind that renders thousands of grass blades using InstancedMesh + vertex shader wind animation.

**New files needed:**
- `/static/TransformControls.js` — Three.js addon (Batch 4, but download now)

**Touch points in main.js:**

1. **Grass geometry factory** (new function, near line 19259):
```javascript
function _env3DCreateGrassBlade() {
    // PlaneGeometry with 4 vertical segments for smooth bending along height
    // 1 horizontal segment, 4 vertical = 10 vertices per blade
    // At 2500 instances = 25K vertices in a single draw call (60fps on mid-range)
    var geo = new THREE.PlaneGeometry(0.1, 0.8, 1, 4);
    // Shift geometry so base sits at y=0 (PlaneGeometry centers at origin)
    geo.translate(0, 0.4, 0);
    return geo;
}
```

2. **Wind ShaderMaterial** (new function):
```javascript
function _env3DCreateGrassMaterial(baseColor) {
    return new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uWindDir: { value: new THREE.Vector2(1.0, 0.3) },
            uWindStrength: { value: 0.5 },
            uInfluenceMap: { value: null },       // DataTexture
            uInfluenceMapSize: { value: 64.0 },   // texels per side
            uWorldBounds: { value: new THREE.Vector4(0, 0, 100, 100) }, // world xz bounds
            uInfluenceFloat: { value: 1.0 },    // 1.0 = FloatType (raw), 0.0 = UnsignedByteType (encoded)
            uBaseColor: { value: new THREE.Color(baseColor || 0x4a7c3f) },
            uTipColor: { value: new THREE.Color(0x8aba6f) }
        },
        vertexShader: `
            uniform float uTime;
            uniform vec2 uWindDir;
            uniform float uWindStrength;
            uniform sampler2D uInfluenceMap;
            uniform float uInfluenceMapSize;
            uniform vec4 uWorldBounds;
            uniform float uInfluenceFloat;

            varying vec2 vUv;
            varying float vHeight;

            void main() {
                vUv = uv;
                vHeight = uv.y; // 0 at base, 1 at tip (PlaneGeometry 4-segment UV)

                // IMPORTANT: instanceMatrix is the LOCAL transform of each instance.
                // modelMatrix is the transform of the InstancedMesh object itself (patch world position).
                // We need both for correct world-space phase + influence lookup.
                vec4 instanceLocal = instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
                vec3 worldPos = (modelMatrix * instanceLocal).xyz;

                // Sample influence map at this blade's world XZ position
                vec2 mapUV = (worldPos.xz - uWorldBounds.xy) / (uWorldBounds.zw - uWorldBounds.xy);
                mapUV = clamp(mapUV, 0.0, 1.0);
                vec4 rawInfluence = texture2D(uInfluenceMap, mapUV);
                // Decode: if UnsignedByteType fallback, values are encoded as val*0.5+0.5
                // so decode with tex*2.0-1.0. For FloatType raw values pass through unchanged.
                vec4 influence = uInfluenceFloat > 0.5
                    ? rawInfluence
                    : vec4(rawInfluence.rg * 2.0 - 1.0, rawInfluence.b, rawInfluence.a);

                // Wind: quadratic falloff (root anchored, tip sways)
                float phase = dot(worldPos.xz, vec2(0.1, 0.17));
                float sway = sin(uTime * 2.5 + phase * 0.8)
                           * cos(uTime * 1.75 + phase * 1.3);
                float bendAmount = vHeight * vHeight * uWindStrength;
                vec3 windOffset = vec3(uWindDir.x * sway * bendAmount, 0.0, uWindDir.y * sway * bendAmount);

                // Sprite influence: R=pushX, G=pushZ, B=strength
                vec3 pushOffset = vec3(influence.r, 0.0, influence.g) * influence.b * vHeight * vHeight * 2.0;

                // Apply wind + influence in local space, then full transform chain
                vec3 displaced = position + windOffset + pushOffset;
                vec4 worldFinal = modelMatrix * (instanceMatrix * vec4(displaced, 1.0));
                gl_Position = projectionMatrix * viewMatrix * worldFinal;
            }
        `,
        fragmentShader: `
            uniform vec3 uBaseColor;
            uniform vec3 uTipColor;
            varying vec2 vUv;
            varying float vHeight;

            void main() {
                vec3 color = mix(uBaseColor, uTipColor, vHeight);
                // Slight variation based on vUv
                color += (vHeight * 0.1 - 0.05);
                gl_FragColor = vec4(color, 1.0);
            }
        `,
        side: THREE.DoubleSide,
        transparent: false
    });
}
```

3. **Vegetation patch builder** (new function in mesh creation area, near line 21850):
```javascript
function _env3DCreateVegetationPatch(obj, appearance, mechanics) {
    // Creates an InstancedMesh of grass blades within the object's footprint
    var count = 500; // configurable via mechanics or data
    var patchRadius = (obj.scale || 1) * 5;

    var bladeGeo = _env3DCreateGrassBlade();
    var grassMat = _env3DCreateGrassMaterial(appearance.color);

    var mesh = new THREE.InstancedMesh(bladeGeo, grassMat, count);
    var dummy = new THREE.Object3D();
    for (var i = 0; i < count; i++) {
        // Random position within circular patch
        var angle = Math.random() * Math.PI * 2;
        var r = Math.sqrt(Math.random()) * patchRadius;
        dummy.position.set(Math.cos(angle) * r, 0, Math.sin(angle) * r);
        // Random rotation + scale variation
        dummy.rotation.y = Math.random() * Math.PI;
        var bladeScale = 0.6 + Math.random() * 0.8;
        dummy.scale.set(1, bladeScale, 1);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.frustumCulled = false;
    return mesh;
}
```

4. **Influence field** (new, managed in `_env3D` state):
```javascript
// In _env3DInit or lazy-init:
_env3D.influenceMap = null;      // DataTexture (128x128 RGBA Float, 256KB)
_env3D.influenceData = null;     // Float32Array backing the texture
_env3D.influenceMapSize = 128;

function _env3DInitInfluenceMap() {
    var size = 128;
    // WebGL 1 needs OES_texture_float + OES_texture_float_linear for FloatType + LinearFilter.
    // Probe for support and fall back to UnsignedByteType (encode signed as val*0.5+0.5, decode in shader as tex*2.0-1.0).
    var gl = _env3D.renderer.getContext();
    var hasFloat = !!gl.getExtension('OES_texture_float');
    var hasFloatLinear = !!gl.getExtension('OES_texture_float_linear');
    var useFloat = hasFloat && hasFloatLinear;
    var dataType = useFloat ? THREE.FloatType : THREE.UnsignedByteType;
    var data = useFloat ? new Float32Array(size * size * 4) : new Uint8Array(size * size * 4);
    var tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat, dataType);
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.magFilter = THREE.LinearFilter;
    tex.minFilter = THREE.LinearFilter;  // safe for UnsignedByte; for Float needs OES_texture_float_linear (checked above)
    tex.needsUpdate = true;
    _env3D.influenceMap = tex;
    _env3D.influenceData = data;
    _env3D.influenceMapSize = size;
    _env3D.influenceUseFloat = useFloat;
}

function _env3DStampInfluence(worldX, worldZ, dirX, dirZ, strength) {
    // Stamp a sprite's influence into the DataTexture
    // Convert world position to texel coordinates
    // Write push direction + strength into nearby texels (Gaussian falloff)
    // IMPORTANT: if _env3D.influenceUseFloat is false (UnsignedByteType),
    // encode signed values as Math.round((val * 0.5 + 0.5) * 255) for R/G channels,
    // and unsigned strength as Math.round(val * 255) for B channel.
}

function _env3DDecayInfluence(dt) {
    // Decay all influence values toward zero each frame (spring recovery)
    // influence *= max(0, 1 - dt * decayRate)
}
```

5. **Hook into `_env3DSyncObjects`** (line 22312): When kind === 'vegetation_patch', create the InstancedMesh group instead of a normal primitive mesh.

6. **Hook into `_env3DAnimate`** (line 22620):
   - Update `uTime` uniform on all vegetation materials
   - Stamp sprite/agent positions into influence map
   - Decay influence map
   - Upload influence map: `_env3D.influenceMap.needsUpdate = true`

**Codex scope:** ~300 lines of new code. Largest batch.

---

### BATCH 3: Mesh Creation Routing + vegetation_patch Kind

**Goal:** Wire the vegetation patch renderer into the existing mesh creation pipeline in `_env3DSyncObjects`.

**Touch points:**

1. **`_env3DSyncObjects`** (line 22312): In the mesh creation block (around line 22400-22500 where new meshes are built for objects), add a branch:
```javascript
if (kind === 'vegetation_patch') {
    mesh = _env3DCreateVegetationPatch(obj, appearance, mechanics);
} else if (/* existing GLB/primitive path */) { ... }
```

2. **`_env3DAnimate`** (line 22620): Add vegetation update section after existing agent animation:
```javascript
// === VEGETATION WIND + INFLUENCE ===
if (_env3D.influenceMap) {
    _env3DDecayInfluence(dt);
    // Stamp all moving agent positions
    Object.keys(_env3D.meshes).forEach(function (key) {
        var m = _env3D.meshes[key];
        if (m && m.userData._moving && _env3DIsAgentKind(m.userData.kind || '')) {
            _env3DStampInfluence(m.position.x, m.position.z, /* velocity dir */ 0, 0, 1.0);
        }
    });
    _env3D.influenceMap.needsUpdate = true;
}
// Update vegetation uniforms
Object.keys(_env3D.meshes).forEach(function (key) {
    var m = _env3D.meshes[key];
    if (m && m.userData.kind === 'vegetation_patch' && m.material && m.material.uniforms) {
        m.material.uniforms.uTime.value = time;
        if (_env3D.influenceMap) {
            m.material.uniforms.uInfluenceMap.value = _env3D.influenceMap;
        }
    }
});
```

3. **`_env3DKindColors`** or equivalent: Add vegetation_patch to the kind→color mapping so it gets a default color chip.

4. **Kind-specific defaults** in `_envDefaultKindAssets` or similar: Give vegetation_patch a default green color and appropriate scale.

**Codex scope:** ~80 lines. Wiring and routing only.

---

### BATCH 4: TransformControls + Raycaster (Object Editing)

**Goal:** Click any object in the 3D view to select it, then translate/rotate/scale with gizmos.

**New files:**
- `/static/TransformControls.js` — from Three.js `examples/js/controls/` (NOT `examples/jsm/`), pinned to same revision as `three.min.js`. The `examples/js/` version registers on the global `THREE` object automatically.

**Touch points in panel.html:**
- Add `<script src="/static/TransformControls.js"></script>` after OrbitControls.js (line 11675)

**Touch points in main.js:**

1. **Raycaster + click handler** (new, near _env3DInit):

**IMPORTANT:** Only custom/spawned objects can be edited (checked via `_envIsCustomSceneKind(kind)` at line 15519). System objects (workflow, actor, node, etc.) must be excluded from picking — `_envMutateObject` (line 15999) only searches `_envSpawnedObjects`, so editing system meshes would silently no-op.

**IMPORTANT:** Mesh userData fields are `kind`, `id`, `label`, `state`, `visualKey` (set at line 22443). There is NO `envObjectKey` field — walk up using `userData.kind` to find the root mesh.

```javascript
_env3D.raycaster = new THREE.Raycaster();
_env3D.mouse = new THREE.Vector2();
_env3D.selectedMesh = null;
_env3D.transformControls = null;

function _env3DOnPointerDown(event) {
    // Don't pick if transform controls are being dragged
    if (_env3D.transformControls && _env3D.transformControls.dragging) return;
    // Compute NDC mouse coordinates from event
    var rect = _env3D.renderer.domElement.getBoundingClientRect();
    _env3D.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    _env3D.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    _env3D.raycaster.setFromCamera(_env3D.mouse, _env3D.camera);
    // Only pick custom/spawned objects — system kinds cannot be persisted
    var pickable = [];
    Object.keys(_env3D.meshes).forEach(function (key) {
        var m = _env3D.meshes[key];
        if (m && m.userData.kind && _envIsCustomSceneKind(m.userData.kind)) pickable.push(m);
    });
    var hits = _env3D.raycaster.intersectObjects(pickable, true);
    if (hits.length > 0) {
        // Walk up to find the root mesh (has userData.kind set)
        var hit = hits[0].object;
        while (hit.parent && !hit.userData.kind) hit = hit.parent;
        _env3DSelectMesh(hit);
    } else {
        _env3DDeselectMesh();
    }
}
```

2. **TransformControls setup** (new, in _env3DInit or lazy):
```javascript
function _env3DInitTransformControls() {
    var tc = new THREE.TransformControls(_env3D.camera, _env3D.renderer.domElement);
    tc.addEventListener('dragging-changed', function (event) {
        _env3D.controls.enabled = !event.value; // disable OrbitControls while dragging
        // IMPORTANT: persist on drag END only, not on every objectChange.
        // objectChange fires every frame during drag which would trigger
        // _envMutateObject → scene refresh → jitter fight with the sync loop.
        if (!event.value && _env3D.selectedMesh) {
            _env3DSyncTransformToObject(_env3D.selectedMesh);
        }
    });
    // Do NOT listen to 'objectChange' for persistence — visual feedback is
    // immediate (the mesh moves), persistence happens when drag ends above.
    _env3D.scene.add(tc);
    _env3D.transformControls = tc;
}

function _env3DSelectMesh(mesh) {
    if (!_env3D.transformControls) _env3DInitTransformControls();
    _env3D.selectedMesh = mesh;
    _env3D.transformControls.attach(mesh);
}

function _env3DDeselectMesh() {
    if (_env3D.transformControls) _env3D.transformControls.detach();
    _env3D.selectedMesh = null;
}
```

3. **Keyboard mode switching** — add a NEW keydown listener on the **renderer canvas element only** (NOT `document`). Binding G/R/S globally would conflict with text inputs, chat, workflow editor, etc. Guard with `if (!_env3D.selectedMesh) return`:
   - `G` key: set transformControls.mode = 'translate'
   - `R` key: set transformControls.mode = 'rotate'
   - `S` key: set transformControls.mode = 'scale'
   - `Escape`: deselect
   - The canvas needs `tabindex="0"` to receive keyboard events

4. **Position sync back to object contract** — must invert `_env3DXYZFromObject` (line 20016). The forward mapping is:
   - `worldX = (x/100 * 80) - 40` → inverse: `x = (worldX + 40) / 80 * 100`
   - `worldZ = (y/100 * 40) - 20` → inverse: `y = (worldZ + 20) / 40 * 100`
   - `worldY` is kind-based height (fixed per kind, not user-editable)
   - `scale` maps to `obj.scale` directly (scene sync uses it as a multiplier)
   - `tilt` maps to Y-axis rotation in radians (the object contract `tilt` field)
```javascript
function _env3DSyncTransformToObject(mesh) {
    if (!mesh || !mesh.userData.kind || !mesh.userData.id) return;
    var newX = Math.round(((mesh.position.x + 40) / 80) * 100 * 10) / 10;
    var newY = Math.round(((mesh.position.z + 20) / 40) * 100 * 10) / 10;
    newX = Math.max(0, Math.min(100, newX));
    newY = Math.max(0, Math.min(100, newY));
    var newScale = Math.round(mesh.scale.x * 100) / 100;
    var newTilt = Math.round(mesh.rotation.y * 1000) / 1000; // radians
    _envMutateObject({
        kind: mesh.userData.kind,
        id: mesh.userData.id,
        x: newX,
        y: newY,
        scale: newScale,
        tilt: newTilt
    });
}
```

**Codex scope:** ~150 lines + TransformControls.js addon file.

---

### BATCH 5: Hero Object Animation + LOD

**Goal:** Add wind-driven procedural animation to foliage hero objects and distance-based LOD.

**NOTE:** AnimationMixer playback already works. The loader at line 21929 resolves an initial clip and plays it, and the animate loop at line 22710 already updates mixers and crossfades walk/run/idle. Do NOT re-add clip playback — it would double-start actions and break the existing transition logic.

**Touch points:**

1. **Clamp mixer dt** (line 22711): Change `mesh.userData._mixer.update(dt)` to `mesh.userData._mixer.update(Math.min(dt, 0.1))` to prevent tab-hidden spikes.

2. **Wind-driven procedural animation** on foliage hero objects:
   - After `mixer.update(dt)`, overlay procedural bone rotation for wind sway
   - For objects without embedded animations, apply procedural rotation in animate loop
   - Modulate timeScale based on wind strength from mechanics block

3. **LOD for hero objects** (standard THREE.LOD with hysteresis):
```javascript
function _env3DCreateLODWrapper(obj, nearMesh, midMesh, farMesh, mechanics) {
    var lod = new THREE.LOD();
    var distances = mechanics && mechanics.lod
        ? mechanics.lod
        : { near: 20, mid: 50, far: 100 };
    if (nearMesh) lod.addLevel(nearMesh, 0, 0.1);  // 10% hysteresis (r150+)
    if (midMesh) lod.addLevel(midMesh, distances.near, 0.1);
    if (farMesh) lod.addLevel(farMesh, distances.mid, 0.1);
    return lod;
}
```

4. **LOD for vegetation patches** — ring-based multi-InstancedMesh (NOT per-blade LOD):
```javascript
// Near ring: PlaneGeometry(0.1, 0.8, 1, 4) — full 4-segment bending
// Mid ring: PlaneGeometry(0.1, 0.6, 1, 2) — 2-segment simplified
// Far ring: PlaneGeometry(0.1, 0.4, 1, 1) — flat billboard, wind-only
// Redistribute instances when camera moves >5 units
// Set mesh.count to actual used instances (r138+)
```

5. **LOD update in `_env3DAnimate`**: `lod.autoUpdate = true` handles it (default in r150+).

**Codex scope:** ~120 lines. Additive to existing GLB path + vegetation system.

---

## Execution Order

| Batch | Dependency | Lines | What it delivers |
|-------|-----------|-------|-----------------|
| 1 | None | ~65 | mechanics block in object contract + inspector surface |
| 2 | None (parallel with 1) | ~300 | Grass geometry, wind shader, influence field, vegetation patch builder |
| 3 | 1 + 2 | ~80 | Wiring: vegetation_patch kind renders grass, animate loop drives wind + influence |
| 4 | None (parallel with 1-3) | ~150 + addon | Click-to-select + translate/rotate/scale gizmos |
| 5 | 1 + 3 | ~120 | Clamp mixer dt + wind procedural + ring-based vegetation LOD |

**Recommended Codex order:** Batch 1+2 together (or 1+2+4 in parallel), then Batch 3, then Batch 5.

---

## Testing

After each batch, verify:

1. **Batch 1:** `env_spawn({kind: 'prop', id: 'test', mechanics: {family: 'foliage', wind: {enabled: true, strength: 0.5}}})` — object appears, click to inspect: inspector shows a "Mechanics" section with Family=foliage, Wind=0.5.

2. **Batch 3 (after 1+2):** `env_spawn({kind: 'vegetation_patch', id: 'grass1', x: 50, y: 50, scale: 1.5, appearance: {color: '#4a7c3f'}, mechanics: {family: 'foliage', wind: {enabled: true, strength: 0.6}}})` — green grass patch appears with wind sway. Walk a sprite through it — grass bends.

3. **Batch 4:** Click any object in the 3D view — gizmo appears. Drag to move. Press R for rotate, S for scale. Position persists.

4. **Batch 5:** Load a GLB bush with animations. It sways in wind. Walk far away — it switches to simplified LOD.

---

## Cleanup / Disposal

New resources MUST be wired into the existing `_env3DDispose()` (line 22854):

```javascript
// In _env3DDispose, after existing cleanup:
if (_env3D.transformControls) {
    _env3D.transformControls.detach();
    _env3D.transformControls.dispose();
    _env3D.scene.remove(_env3D.transformControls);
    _env3D.transformControls = null;
}
if (_env3D.influenceMap) {
    _env3D.influenceMap.dispose();
    _env3D.influenceMap = null;
    _env3D.influenceData = null;
}
_env3D.selectedMesh = null;
// Vegetation InstancedMesh materials + geometries are already cleaned
// by _env3DRemoveSceneObjectMesh iterating _env3D.meshes above.
```

Also in `_env3DRemoveSceneObjectMesh`: if the mesh is a vegetation InstancedMesh, dispose its ShaderMaterial and blade geometry explicitly (they are not shared/cached like MeshStandardMaterial).

## Version Bump

After all changes, bump the main.js cache tag in `panel.html` line 11683:
```html
<script src="/static/main.js?v=100"></script>
```

## TransformControls.js Source

Pin to the **same Three.js revision as `three.min.js`** in `/static/`. Check the version:
```javascript
console.log(THREE.REVISION); // e.g. "150" or "163"
```
Then download `TransformControls.js` from the matching tag at `https://github.com/mrdoob/three.js/blob/r{REVISION}/examples/js/controls/TransformControls.js` (the non-module `examples/js/` version, NOT `examples/jsm/`). The `examples/js/` version registers on the global `THREE` object automatically.

---

## Files Modified

- `static/main.js` — all runtime code (bump `?v=100` in panel.html)
- `static/panel.html` — script tag for TransformControls.js + version bump
- `static/TransformControls.js` — new addon file (pinned to same Three.js revision)

---

## Constraints

- All code uses global `THREE` object (no ES module imports)
- No new npm dependencies — everything is vanilla Three.js
- Keep the existing env_spawn/env_mutate MCP contract backwards compatible (mechanics is optional, null by default)
- The vegetation shader must work on WebGL 1 (no WebGL 2 required features)
- Performance target: 60fps with 5 vegetation patches of 500 blades each on mid-range hardware
- Do NOT modify agent_compiler.py or capsule code — this is frontend only

---

## Critical Gotchas (from research)

1. **InstancedMesh frustumCulled**: MUST set `frustumCulled = false` — default bounding box is from base geometry only, not instance spread. Blades will pop in/out incorrectly without this.
2. **instanceMatrix is LOCAL, not world**: Three.js auto-injects `instanceMatrix` as an attribute for InstancedMesh + ShaderMaterial. Do NOT declare it manually. `instanceMatrix` is the local transform per-instance. For world-space calculations (influence map lookup, wind phase), multiply through `modelMatrix` first: `vec3 worldPos = (modelMatrix * instanceMatrix * vec4(0,0,0,1)).xyz`. For final projection: `gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(displaced, 1.0)`.
3. **DataTexture needsUpdate**: Auto-resets to `false` after GPU upload. Must set `true` every frame you modify data.
4. **DataTexture texel origin**: (0,0) is bottom-left. Map world coordinates accordingly.
5. **TransformControls + OrbitControls**: Without `dragging-changed` listener, they fight for pointer input. Always check `transform.dragging` before processing clicks.
6. **AnimationMixer dt clamping**: Call `clock.getDelta()` exactly once per frame. Clamp: `mixer.update(Math.min(dt, 0.1))` to prevent tab-hidden spikes.
7. **Procedural bone modification**: Must happen AFTER `mixer.update()` — the mixer overwrites bone transforms each frame.
8. **LOD + InstancedMesh**: They don't compose directly. Use ring-based multi-InstancedMesh approach instead.
9. **WebGL 1 compatibility**: `texture2D()` (not `texture()`) in shaders. FloatType + LinearFilter needs `OES_texture_float` + `OES_texture_float_linear` extensions — probe at init and fall back to UnsignedByteType (encode signed values as `val*0.5+0.5`, decode in shader as `tex*2.0-1.0`).

---

## Source References

- Three.js InstancedMesh: https://threejs.org/docs/#api/en/objects/InstancedMesh
- Three.js ShaderMaterial: https://threejs.org/docs/#api/en/materials/ShaderMaterial
- Three.js DataTexture: https://threejs.org/docs/#api/en/textures/DataTexture
- Three.js AnimationMixer: https://threejs.org/docs/#api/en/animation/AnimationMixer
- Three.js TransformControls: https://threejs.org/docs/#examples/en/controls/TransformControls
- Three.js Raycaster: https://threejs.org/docs/#api/en/core/Raycaster
- Three.js LOD: https://threejs.org/docs/#api/en/objects/LOD
- Existing InstancedMesh pattern: main.js:20518 (room walls)
- Existing AnimationMixer pattern: main.js:21918 (GLB playback)
- Animate loop hook point: main.js:22620 (_env3DAnimate)
